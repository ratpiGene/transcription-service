from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
import redis as redis_py  # for ConnectionError typing

from pipeline.packaging import build_manifest, create_results_zip
from pipeline.processor import OutputType, ProcessOptions, process_media
from worker.queue import get_redis_client, dequeue_job_blocking

from app.storage import (
    load_s3_config,
    get_s3_client,
    ensure_bucket,
    download_file,
    upload_fileobj,
)

from worker.metrics import (
    JOB_DURATION,
    JOB_SUCCESS,
    JOB_FAILURE,
    JOBS_QUEUED,
    JOBS_RUNNING,
    update_gpu_metrics,
    start_metrics_server,
)

# =========================
# JOB STATUS MODEL (local)
# =========================

@dataclass
class JobStatus:
    job_id: str
    status: str  # queued | running | succeeded | failed
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error: dict[str, Any] | None = None
    result_zip: str | None = None
    metrics: dict[str, Any] | None = None


# =========================
# HELPERS
# =========================

def _parse_outputs(values: list[str]) -> list[OutputType]:
    out: list[OutputType] = []
    for v in values:
        try:
            out.append(OutputType(v))
        except ValueError as e:
            raise ValueError(f"unknown_output_type: {v}") from e
    return out


def status_key(job_id: str) -> str:
    return f"job:{job_id}"


def get_status(r, job_id: str) -> dict[str, Any] | None:
    raw = r.get(status_key(job_id))
    return json.loads(raw) if raw else None


def set_status(r, job_id: str, data: dict[str, Any]) -> None:
    r.set(status_key(job_id), json.dumps(data))


def patch_status(r, job_id: str, **updates: Any) -> dict[str, Any]:
    """
    Read-modify-write helper to avoid repeating boilerplate.
    Returns the updated status dict.
    """
    st = get_status(r, job_id) or {"job_id": job_id, "created_at": time.time()}
    st.update(updates)
    set_status(r, job_id, st)
    return st


def wait_for_redis_ready(r, *, max_seconds: int = 30) -> None:
    """
    Avoid crash on startup when redis isn't ready yet.
    """
    deadline = time.time() + max_seconds
    last_err: Exception | None = None

    while time.time() < deadline:
        try:
            r.ping()
            return
        except (redis_py.exceptions.ConnectionError, OSError) as e:
            last_err = e
            time.sleep(1)

    raise RuntimeError(f"redis_not_ready_after_{max_seconds}s: {last_err}")


# =========================
# CORE JOB RUNNER (local processing + zip)
# =========================

def run_job(
    *,
    input_path: Path,
    requested_outputs: list[OutputType],
    job_root_dir: Path,
    options: ProcessOptions | None = None,
    job_id: str | None = None,
) -> JobStatus:
    """
    Minimal worker runner (local filesystem):
    - creates a job folder
    - runs process_media (engine)
    - packages results zip + manifest.json
    - writes status.json in the job folder
    """
    if options is None:
        options = ProcessOptions()

    if job_id is None:
        job_id = f"job_{uuid.uuid4().hex[:12]}"

    job_dir = Path(job_root_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    status_path = job_dir / "status.json"

    status = JobStatus(
        job_id=job_id,
        status="queued",
        created_at=time.time(),
    )
    status_path.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")

    try:
        status.status = "running"
        status.started_at = time.time()
        status_path.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")

        output_dir = job_dir / "outputs"

        t0 = time.time()
        result = process_media(
            input_path=input_path,
            requested_outputs=requested_outputs,
            output_dir=output_dir,
            options=options,
        )
        processing_seconds = time.time() - t0

        manifest = build_manifest(
            job_id=job_id,
            input_path=result.input_path,
            input_type=result.input_type,
            requested_outputs=result.requested_outputs,
            artifacts=result.artifacts,
            model=options.model,
            language=options.language,
            metrics={"processing_seconds": round(processing_seconds, 3)},
        )

        zip_path = create_results_zip(
            output_dir=job_dir,
            job_id=job_id,
            artifacts=result.artifacts,
            manifest=manifest,
        )

        status.status = "succeeded"
        status.finished_at = time.time()
        status.result_zip = str(zip_path)
        status.metrics = manifest.metrics

        status_path.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")
        return status

    except Exception as e:
        status.status = "failed"
        status.finished_at = time.time()
        status.error = {"message": str(e), "type": e.__class__.__name__}
        status_path.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")
        raise


# =========================
# ENTRYPOINT
# =========================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Transcription worker")

    # Local execution
    parser.add_argument("--input", help="Path to input file (.mp4 or .wav)")
    parser.add_argument("--outputs", nargs="+", help="Requested outputs")

    # Worker config
    parser.add_argument("--jobs-dir", default="data/jobs")
    parser.add_argument("--language", default="en")
    parser.add_argument("--model", default="openai/whisper-small.en")

    # Daemon mode
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        )
    parser.add_argument(
        "--queue",
        default=os.environ.get("QUEUE_NAME", "transcription:jobs"),
        )

    args = parser.parse_args()

    # =========================
    # DAEMON MODE (QUEUE WORKER)
    # =========================
    if args.daemon:
        r = get_redis_client(args.redis_url)
        wait_for_redis_ready(r, max_seconds=30)

        # Start Prometheus GPU metrics server
        start_metrics_server()
        print("Prometheus metrics on :8001/metrics")

        print(f"Worker listening on queue '{args.queue}' (redis={args.redis_url})")

        # GPU info (daemon only)
        print("CUDA available:", torch.cuda.is_available())
        if torch.cuda.is_available():
            try:
                print("GPU:", torch.cuda.get_device_name(0))
            except Exception:
                pass
            
        # Prometheus metrics endpoint (daemon only)
        start_metrics_server()
        print("Prometheus metrics on :8001/metrics")

        # MinIO client
        s3cfg = load_s3_config()
        s3 = get_s3_client(s3cfg)

        # Ensure buckets exist (ensure_bucket must be idempotent in storage.py)
        ensure_bucket(s3, s3cfg.uploads_bucket)
        ensure_bucket(s3, s3cfg.results_bucket)

        while True:
            try :
                JOBS_QUEUED.labels(queue=args.queue).set(r.llen(args.queue))
            except Exception:
                pass

            msg = dequeue_job_blocking(r, args.queue, timeout_s=0)
            if msg is None:
                continue

            job_id = msg.job_id

            st = get_status(r, job_id)
            if not st:
                # Don't leave "phantom jobs": mark failed explicitly
                patch_status(
                    r,
                    job_id,
                    status="failed",
                    finished_at=time.time(),
                    error={"type": "StatusNotFound", "message": "status_not_found_in_redis"},
                )
                print(f"[JOB] {job_id} failed: status not found in Redis")
                continue

            # Mark running
            patch_status(r, job_id, status="running", started_at=time.time(), stage="starting")

            JOBS_RUNNING.inc()
            t0 = time.time()

            try:
                # 1) locate input in MinIO
                upload_info = st.get("input", {})
                in_bucket = upload_info.get("bucket")
                in_key = upload_info.get("key")
                if not in_bucket or not in_key:
                    raise RuntimeError("missing_input_location_in_status")

                # 2) outputs to generate (stored in Redis by API /jobs)
                requested_outputs_raw = st.get("requested_outputs")
                if not requested_outputs_raw:
                    raise RuntimeError("missing_requested_outputs_in_status")

                print(f"[JOB] {job_id} input=s3://{in_bucket}/{in_key} outputs={requested_outputs_raw}")

                # 3) download input locally into job folder
                patch_status(r, job_id, stage="downloading")
                job_dir = Path(args.jobs_dir) / job_id
                job_dir.mkdir(parents=True, exist_ok=True)

                ext = Path(in_key).suffix.lower()  # .mp4 or .wav
                local_input = job_dir / f"input{ext}"
                download_file(s3, in_bucket, in_key, str(local_input))

                # 4) run local processing
                patch_status(r, job_id, stage="processing")
                parsed_outputs = _parse_outputs(list(requested_outputs_raw))
                options = ProcessOptions(
                    language=st.get("options", {}).get("language", "en"),
                    model=st.get("options", {}).get("model", "openai/whisper-small.en"),
                )

                local_status = run_job(
                    input_path=local_input,
                    requested_outputs=parsed_outputs,
                    job_root_dir=Path(args.jobs_dir),
                    options=options,
                    job_id=job_id,
                )

                # 5) upload zip to MinIO results bucket
                patch_status(r, job_id, stage="uploading_results")
                zip_path = Path(local_status.result_zip) if local_status.result_zip else None
                if not zip_path or not zip_path.exists():
                    raise RuntimeError("zip_missing_after_processing")

                result_key = f"{job_id}/{zip_path.name}"
                with zip_path.open("rb") as f:
                    upload_fileobj(
                        s3,
                        s3cfg.results_bucket,
                        result_key,
                        f,
                        content_type="application/zip",
                    )

                # 6) mark succeeded in Redis
                patch_status(
                    r,
                    job_id,
                    status="succeeded",
                    finished_at=time.time(),
                    stage="done",
                    result={"bucket": s3cfg.results_bucket, "key": result_key},
                    metrics=local_status.metrics or st.get("metrics", {}),
                )

                JOB_SUCCESS.inc()
                JOB_DURATION.observe(time.time() - t0)
                JOBS_RUNNING.dec()

                print(f"[JOB] {job_id} succeeded -> s3://{s3cfg.results_bucket}/{result_key}")

            except Exception as e:
                JOB_FAILURE.inc()
                JOBS_RUNNING.dec()
                
                patch_status(
                    r,
                    job_id,
                    status="failed",
                    finished_at=time.time(),
                    stage="failed",
                    error={"type": e.__class__.__name__, "message": str(e)},
                )
                print(f"[JOB] {job_id} failed: {e}")

    # =========================
    # LOCAL CLI MODE
    # =========================
    else:
        if not args.input or not args.outputs:
            parser.error("--input and --outputs required unless --daemon")

        input_path = Path(args.input)
        requested_outputs = _parse_outputs(args.outputs)
        options = ProcessOptions(language=args.language, model=args.model)

        status = run_job(
            input_path=input_path,
            requested_outputs=requested_outputs,
            job_root_dir=Path(args.jobs_dir),
            options=options,
        )

        print("DONE:", status.job_id)
        print("ZIP :", status.result_zip)