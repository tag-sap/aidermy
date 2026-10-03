"""
image_storage.py — загрузка изображений в Yandex Object Storage (S3-совместимый).

Ключи читаются из .env (S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET). Используется
для публикации обработанных изображений (remove_background) в тот же bucket,
откуда фронтенд уже берёт image_url.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

S3_ENDPOINT = "https://storage.yandexcloud.net"
S3_BUCKET = os.getenv("S3_BUCKET", "aidermy-images")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")

_client = None


def get_s3():
    """Возвращает (лениво созданный) boto3-клиент Object Storage."""
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name="ru-central1",
            config=Config(s3={"addressing_style": "path"}),
        )
    return _client


def public_url(key: str) -> str:
    return f"https://storage.yandexcloud.net/{S3_BUCKET}/{key}"


def upload_image(key: str, data: bytes, content_type: str = "image/png") -> str:
    """Загружает изображение в bucket и возвращает публичный URL."""
    get_s3().put_object(Bucket=S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    return public_url(key)


def processed_key(slug: str) -> str:
    """Ключ обработанного изображения (подпрефикс processed/ в том же bucket)."""
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in slug)
    return f"processed/{safe}.png"
