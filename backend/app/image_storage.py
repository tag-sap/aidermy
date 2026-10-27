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


def _validate_public_image_url(value: str) -> str:
    """Validate scheme/host/DNS and reject private or metadata targets."""
    from .scraper.service import ProductImportError, validate_public_url

    if not (value or "").strip():
        raise ValueError("Пустой URL изображения")
    try:
        return validate_public_url(value)
    except ProductImportError as exc:
        raise ValueError(str(exc)) from exc


def download_public_image(value: str, *, max_bytes: int = _MAX_IMAGE_BYTES) -> tuple[bytes, str]:
    """Download an image with SSRF-safe redirects and content validation.

    Redirects are followed manually so every hop is checked, not just the first
    URL. HTML, SVG/scripts, non-image MIME types and oversized bodies are
    rejected before Pillow sees them.
    """
    import io

    import httpx
    from urllib.parse import urljoin

    from PIL import Image

    current = _validate_public_image_url(value)
    headers = {"User-Agent": "aidermy-image-pipeline/1.0", "Accept": "image/*"}
    for _ in range(4):
        with httpx.Client(
            timeout=20.0,
            follow_redirects=False,
            headers=headers,
        ) as client:
            response = client.get(current)
        if response.status_code in {301, 302, 303, 307, 308}:
            location = (response.headers.get("location") or "").strip()
            if not location:
                raise ValueError("Редирект изображения без адреса")
            current = _validate_public_image_url(urljoin(current, location))
            continue
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not content_type.startswith("image/") or content_type in {
            "image/svg+xml",
            "image/gif",
        }:
            raise ValueError(f"URL вернул не поддерживаемое изображение: {content_type or 'unknown'}")
        data = response.content
        if not data:
            raise ValueError("Пустое изображение")
        if len(data) > max_bytes:
            raise ValueError("Изображение больше 12 МБ")
        try:
            probe = Image.open(io.BytesIO(data))
            probe.verify()
            probe = Image.open(io.BytesIO(data))
            if probe.width < 32 or probe.height < 32:
                raise ValueError("Слишком маленькое изображение")
        except Exception as exc:
            raise ValueError("Содержимое не является корректным изображением") from exc
        return data, content_type

    raise ValueError("Слишком много редиректов изображения")


def process_product_image_sync(pid: int, slug: str, image_url: str) -> str:
    """Скачивает оригинал, удаляет белый фон, загружает в S3 и обновляет image_url.

    Никогда не бросает исключение — pipeline изображений не ломает импорт.
    Если URL не прошёл SSRF/формат/размер, карточка не сохраняет временный или
    подозрительный URL: возвращаем пустую строку, и UI покажет нейтральную
    заглушку «нет фото».
    """
    try:
        if not pid or not slug or not image_url:
            return ""
        data, content_type = download_public_image(image_url)
        from .remove_background import remove_background
        processed = remove_background(data, output_format="PNG")
        if not processed:
            # A validated source image is still better than a broken placeholder;
            # keep it, but never keep an invalid/unchecked URL.
            return image_url
        url = upload_image(processed_key(slug), processed)
        from .database import get_connection, PRODUCTS_DB
        conn = get_connection(PRODUCTS_DB)
        conn.execute("UPDATE products SET image_url = ? WHERE id = ?", (url, pid))
        conn.commit()
        conn.close()
        return url
    except Exception:
        # Clear only the bad URL. Do not overwrite an existing valid canonical
        # image: the UPDATE is conditional on the exact URL that failed.
        try:
            from .database import get_connection, PRODUCTS_DB
            conn = get_connection(PRODUCTS_DB)
            conn.execute(
                "UPDATE products SET image_url = '' WHERE id = ? AND image_url = ?",
                (pid, image_url),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
        return ""
