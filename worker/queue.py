from __future__ import annotations

import json
from dataclasses import dataclass

import redis


@dataclass(frozen=True)
class JobMessage:
    job_id: str


def get_redis_client(url: str = "redis://localhost:6379/0") -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


def enqueue_job(r: redis.Redis, queue_name: str, msg: JobMessage) -> None:
    r.lpush(queue_name, json.dumps(msg.__dict__))


def dequeue_job_blocking(r: redis.Redis, queue_name: str, timeout_s: int = 0) -> JobMessage | None:
    item = r.blpop(queue_name, timeout=timeout_s)
    if not item:
        return None
    _, payload = item
    data = json.loads(payload)
    return JobMessage(**data)