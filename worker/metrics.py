import os
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import torch

_METRICS_STARTED = False

# JOB METRICS
JOB_DURATION = Histogram(
    "transcription_job_duration_seconds",
    "Duration of transcription jobs"
)

JOB_SUCCESS = Counter(
    "transcription_job_success_total",
    "Successful jobs"
)

JOB_FAILURE = Counter(
    "transcription_job_failure_total",
    "Failed jobs"
)

JOBS_RUNNING = Gauge(
    "transcription_jobs_running",
    "Currently running jobs"
)

JOBS_QUEUED = Gauge(
    "transcription_jobs_queued",
    "Jobs waiting in redis queue",
    ["queue"],
)

GPU_MEMORY_USED = Gauge(
    "gpu_memory_used_mb",
    "GPU memory usage"
)

def update_gpu_metrics():
    if torch.cuda.is_available():
        GPU_MEMORY_USED.set(torch.cuda.memory_allocated() / 1024 / 1024)

def start_metrics_server(port: int | None = None) -> None:
    global _METRICS_STARTED
    if _METRICS_STARTED:
        return
    if port is None:
        port = int(os.getenv("METRICS_PORT", "8001"))
    start_http_server(port)
    _METRICS_STARTED = True