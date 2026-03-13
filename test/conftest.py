import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.lists = {}

    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value):
        self.kv[key] = value

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        if end == -1:
            return values[start:]
        return values[start : end + 1]


class FakeJobMessage:
    def __init__(self, job_id):
        self.job_id = job_id


@pytest.fixture
def app_module():
    fake_redis = FakeRedis()
    enqueued_jobs = []

    # ---- fake worker.queue ----
    fake_queue_mod = ModuleType("worker.queue")

    def fake_get_redis_client(_url):
        return fake_redis

    def fake_enqueue_job(_redis, _queue_name, msg):
        enqueued_jobs.append(msg.job_id)

    fake_queue_mod.JobMessage = FakeJobMessage
    fake_queue_mod.get_redis_client = fake_get_redis_client
    fake_queue_mod.enqueue_job = fake_enqueue_job

    # ---- fake app.storage ----
    fake_storage_mod = ModuleType("app.storage")

    def fake_load_s3_config():
        return SimpleNamespace(
            uploads_bucket="transcript-uploads",
            results_bucket="transcript-results",
        )

    def fake_get_s3_client(_cfg):
        return object()

    def fake_ensure_bucket(_s3, _bucket):
        return None

    def fake_upload_fileobj(_s3, _bucket, _key, _fileobj, content_type=None):
        return None

    def fake_stream_object(_s3, _bucket, _key):
        yield b"fake-zip-content"

    fake_storage_mod.load_s3_config = fake_load_s3_config
    fake_storage_mod.get_s3_client = fake_get_s3_client
    fake_storage_mod.ensure_bucket = fake_ensure_bucket
    fake_storage_mod.upload_fileobj = fake_upload_fileobj
    fake_storage_mod.stream_object = fake_stream_object

    # inject fakes BEFORE importing app.main
    sys.modules["worker.queue"] = fake_queue_mod
    sys.modules["app.storage"] = fake_storage_mod

    # reload app.main fresh for each test
    if "app.main" in sys.modules:
        del sys.modules["app.main"]

    module = importlib.import_module("app.main")
    module._fake_redis = fake_redis
    module._enqueued_jobs = enqueued_jobs
    return module


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)