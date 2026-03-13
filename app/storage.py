from __future__ import annotations

import os
from dataclasses import dataclass
from typing import BinaryIO

import boto3
from botocore.client import Config


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    access_key: str
    secret_key: str
    uploads_bucket: str
    results_bucket: str


def load_s3_config() -> S3Config:
    return S3Config(
        endpoint=os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        uploads_bucket=os.environ["MINIO_UPLOADS_BUCKET"],
        results_bucket=os.environ["MINIO_RESULTS_BUCKET"],
    )


def get_s3_client(cfg: S3Config):
    # signature v4 + path-style addressing for MinIO
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def upload_fileobj(client, bucket: str, key: str, fileobj: BinaryIO, content_type: str | None = None) -> None:
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    client.upload_fileobj(fileobj, bucket, key, ExtraArgs=extra)


def download_file(client, bucket: str, key: str, dest_path: str) -> None:
    client.download_file(bucket, key, dest_path)


def stream_object(client, bucket: str, key: str):
    return client.get_object(Bucket=bucket, Key=key)["Body"]