"""
image_storage.py — загрузка изображений в Yandex Object Storage (S3-совместимый).

Ключи читаются из .env (S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET). Используется
для публикации обработанных изображений (remove_background) в тот же bucket,
откуда фронтенд уже берёт image_url.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
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


_DATA_URL_RE = re.compile(r"^data:(image/(?:jpeg|jpg|png|webp));base64,(.+)$", re.S | re.I)
_EXTENSIONS = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}
_MAX_IMAGE_BYTES = 12 * 1024 * 1024


def upload_product_source_image(data_url: str, key_hint: str = "product") -> str:
    """Загружает исходное фото продукта (data URL) в постоянное хранилище.

    В карточку нельзя записывать временный base64/локальный путь: возвращаем
    публичный URL S3. Ключ детерминирован по содержимому, поэтому повторная
    загрузка того же фото не создаёт мусорных объектов.
    """
    match = _DATA_URL_RE.match((data_url or "").strip())
    if not match:
        raise ValueError("Ожидается изображение в формате data:image/...;base64,...")
    mime = match.group(1).lower()
    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Некорректный base64 изображения") from exc
    if not payload:
        raise ValueError("Пустое изображение")
    if len(payload) > _MAX_IMAGE_BYTES:
        raise ValueError("Изображение больше 12 МБ")

    digest = hashlib.sha1(payload).hexdigest()[:16]
    hint = re.sub(r"[^a-zA-Z0-9_-]+", "-", (key_hint or "product").strip()).strip("-")[:48] or "product"
    key = f"product_source/{hint}-{digest}.{_EXTENSIONS[mime]}"
    return upload_image(key, payload, content_type=mime)


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
