from __future__ import annotations

import json
import os
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from worker.queue import JobMessage, enqueue_job, get_redis_client

from app.storage import (
    ensure_bucket,
    get_s3_client,
    load_s3_config,
    stream_object,
    upload_fileobj,
)

# =========================
# Lightweight types (API side)
# =========================

class InputType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class OutputType(str, Enum):
    VIDEO_EMBEDDED = "video_embedded"
    VIDEO_WITH_SUBTITLE_TRACK = "video_with_subtitle_track"
    SUBTITLES_SRT = "subtitles_srt"
    TRANSCRIPT_TEXT = "transcript_text"


VIDEO_EXTENSIONS = {".mp4"}            # spec
AUDIO_EXTENSIONS = {".wav", ".mp3"}    # mp3 support already on API side


def detect_input_type_from_suffix(suffix: str) -> InputType:
    s = suffix.lower()
    if s in VIDEO_EXTENSIONS:
        return InputType.VIDEO
    if s in AUDIO_EXTENSIONS:
        return InputType.AUDIO
    raise ValueError(f"unsupported_file_type: {s}")


def available_outputs_for(input_type: InputType) -> list[str]:
    if input_type == InputType.VIDEO:
        return [
            OutputType.VIDEO_EMBEDDED.value,
            OutputType.VIDEO_WITH_SUBTITLE_TRACK.value,
            OutputType.SUBTITLES_SRT.value,
            OutputType.TRANSCRIPT_TEXT.value,
        ]
    # audio
    return [
        OutputType.SUBTITLES_SRT.value,
        OutputType.TRANSCRIPT_TEXT.value,
    ]


# =========================
# App init
# =========================

app = FastAPI(title="Transcript Service")
app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "transcription:jobs")

r = get_redis_client(REDIS_URL)

s3cfg = load_s3_config()
s3 = get_s3_client(s3cfg)

ensure_bucket(s3, s3cfg.uploads_bucket)
ensure_bucket(s3, s3cfg.results_bucket)


def status_key(job_id: str) -> str:
    return f"job:{job_id}"

def client_jobs_key(client_id: str) -> str:
    return f"client:{client_id}:jobs"


def add_job_to_client(client_id: str, job_id: str) -> None:
    r.rpush(client_jobs_key(client_id), job_id)


def get_client_job_ids(client_id: str) -> list[str]:
    raw_ids = r.lrange(client_jobs_key(client_id), 0, -1)
    result: list[str] = []
    for x in raw_ids:
        if isinstance(x, bytes):
            result.append(x.decode("utf-8"))
        else:
            result.append(str(x))
    return result

def set_status(job_id: str, data: dict[str, Any]) -> None:
    r.set(status_key(job_id), json.dumps(data))


def get_status(job_id: str) -> dict[str, Any] | None:
    raw = r.get(status_key(job_id))
    return json.loads(raw) if raw else None


# =========================
# Endpoints
# =========================

@app.post("/uploads")
async def upload(file: UploadFile = File(...),
                 client_id: str | None = Form(default=None),
                 ):
    suffix = Path(file.filename).suffix.lower()

    # Create job_id at upload time (stable object keys)
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    # Validate type (fast) using suffix
    try:
        input_type = detect_input_type_from_suffix(suffix)
    except Exception:
        raise HTTPException(status_code=400, detail="unsupported_file_type")

    # Upload to MinIO
    input_key = f"{job_id}/input{suffix}"
    upload_fileobj(
        s3,
        s3cfg.uploads_bucket,
        input_key,
        file.file,
        content_type=file.content_type,
    )

    avail = available_outputs_for(input_type)

    # Write initial status in Redis
    set_status(
        job_id,
        {
            "job_id": job_id,
            "client_id": client_id,
            "status": "uploaded",
            "created_at": time.time(),
            "input": {
                "bucket": s3cfg.uploads_bucket, 
                "key": input_key, 
                "type": input_type.value
            },
            "available_outputs": avail,
        },
    )

    return {"job_id": job_id, "input_type": input_type.value, "available_outputs": avail}


@app.post("/jobs")
async def create_job(payload: dict[str, Any]):
    job_id = payload.get("job_id")
    requested_outputs = payload.get("requested_outputs")
    language = payload.get("language", "en")
    model = payload.get("model", "openai/whisper-small.en")
    client_id = payload.get("client_id")

    if not job_id or not isinstance(job_id, str):
        raise HTTPException(status_code=422, detail="job_id required")
    if not requested_outputs or not isinstance(requested_outputs, list):
        raise HTTPException(status_code=422, detail="requested_outputs must be a list")

    st = get_status(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="job_not_found")

    # Idempotence
    if st.get("status") in {"queued", "running"}:
        return {"job_id": job_id, "status": st["status"]}
    if st.get("status") == "succeeded":
        return {"job_id": job_id, "status": "succeeded", "result": st.get("result")}

    # Validate output names exist
    try:
        _ = [OutputType(o).value for o in requested_outputs]
    except Exception:
        raise HTTPException(status_code=422, detail="unknown_output_type")

    # Validate outputs allowed for this input type
    try:
        input_type = InputType(st["input"]["type"])
    except Exception:
        raise HTTPException(status_code=500, detail="invalid_input_type_in_status")

    allowed = set(available_outputs_for(input_type))
    invalid = [o for o in requested_outputs if o not in allowed]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={"invalid_outputs": invalid, "allowed": sorted(list(allowed))},
        )

    # Write job config into Redis status (worker will read it)
    st["status"] = "queued"
    st["queued_at"] = time.time()
    st["requested_outputs"] = requested_outputs
    st["options"] = {"language": language, "model": model}

    if client_id and isinstance(client_id, str):
        st["client_id"] = client_id

    set_status(job_id, st)

    if client_id and isinstance(client_id, str):
        add_job_to_client(client_id, job_id)

    # Enqueue only job_id
    msg = JobMessage(job_id=job_id)
    enqueue_job(r, QUEUE_NAME, msg)

    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs")
async def list_jobs(client_id: str = Query(...)):
    job_ids = get_client_job_ids(client_id)

    jobs: list[dict[str, Any]] = []
    for job_id in reversed(job_ids):
        st = get_status(job_id)
        if st:
            jobs.append(st)

    return {
        "client_id": client_id,
        "count": len(jobs),
        "jobs": jobs,
    }

@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    st = get_status(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="job_not_found")
    return st


@app.get("/jobs/{job_id}/result")
async def job_result(job_id: str):
    st = get_status(job_id)
    if not st:
        raise HTTPException(status_code=404, detail="job_not_found")

    if st.get("status") != "succeeded":
        raise HTTPException(status_code=409, detail="result_not_ready")

    result_key = st.get("result", {}).get("key")
    if not result_key:
        raise HTTPException(status_code=500, detail="result_key_missing")

    body = stream_object(s3, s3cfg.results_bucket, result_key)

    return StreamingResponse(
        body,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="results_{job_id}.zip"'},
    )