from __future__ import annotations

import uuid

from worker.queue import JobMessage, enqueue_job, get_redis_client


if __name__ == "__main__":
    r = get_redis_client("redis://localhost:6379/0")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    msg = JobMessage(
        job_id=job_id,
        input_path="data/inputs/sample.mp4",
        requested_outputs=["subtitles_srt", "transcript_text"],
        options={"language": "en", "model": "openai/whisper-medium.en"},
    )

    enqueue_job(r, "transcription:jobs", msg)
    print("Enqueued:", job_id)