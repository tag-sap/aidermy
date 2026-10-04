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


def process_product_image_sync(pid: int, slug: str, image_url: str) -> str:
    """Скачивает оригинал, удаляет белый фон, загружает в S3 и обновляет image_url.

    Возвращает итоговый URL (processed/…, либо исходный при любой ошибке).
    Никогда не бросает исключение — pipeline изображений не ломает импорт.
    """
    try:
        if not pid or not slug or not image_url:
            return image_url
        import httpx
        with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "aidermy-image-pipeline/1.0"}) as client:
            resp = client.get(image_url)
            resp.raise_for_status()
            data = resp.content
        from .remove_background import remove_background
        processed = remove_background(data, output_format="PNG")
        if not processed:
            return image_url
        url = upload_image(processed_key(slug), processed)
        from .database import get_connection, PRODUCTS_DB
        conn = get_connection(PRODUCTS_DB)
        conn.execute("UPDATE products SET image_url = ? WHERE id = ?", (url, pid))
        conn.commit()
        conn.close()
        return url
    except Exception:
        return image_url
