"""
remove_background.py — переиспользуемый модуль удаления белого/почти белого фона
у изображений товаров.

Принцип (по ТЗ):
  * удаляется ТОЛЬКО белая/почти белая область, СВЯЗАННАЯ С ГРАНИЦАМИ изображения
    (flood-fill от краёв). Белые элементы самого товара, не касающиеся краёв,
    остаются нетронутыми;
  * результат сохраняется в RGBA (прозрачность) в PNG или WebP;
  * при любой ошибке возвращается оригинальное изображение — pipeline не ломается.

Не трогает Score Engine / Match / рекомендации / API / products.db — это чисто
утилита обработки изображений.
"""

from __future__ import annotations

import io
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter


# Порог «почти белого»: все каналы >= WHITE_THRESHOLD и низкая цветность.
WHITE_THRESHOLD = 238
CHROMA_THRESHOLD = 22  # max(R,G,B) - min(R,G,B) ниже этого -> почти белый


def _load_image(data: bytes) -> Image.Image:
    """Загружает изображение из байтов, нормализует в RGBA."""
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode == "P":
        img = img.convert("RGBA")
    elif img.mode != "RGBA":
        img = img.convert("RGBA")
    return img


def _is_background(rgb: np.ndarray) -> np.ndarray:
    """Маска пикселей, которые похожи на белый фон.

    rgb: (H, W, 3) uint8. Возвращает (H, W) bool.
    """
    mn = rgb.min(axis=2)
    mx = rgb.max(axis=2)
    bright_enough = mn >= WHITE_THRESHOLD
    low_chroma = (mx - mn) <= CHROMA_THRESHOLD
    return bright_enough & low_chroma


def _flood_fill_from_edges(mask: np.ndarray) -> np.ndarray:
    """Возвращает связную с границами область из mask (8-связность, BFS)."""
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    # очередь = пиксели границ, которые являются фоном
    queue = []
    for x in range(w):
        for y in (0, h - 1):
            if mask[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if mask[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))

    idx = 0
    while idx < len(queue):
        y, x = queue[idx]
        idx += 1
        for dy in (-1, 0, 1):
            ny = y + dy
            if ny < 0 or ny >= h:
                continue
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = x + dx
                if nx < 0 or nx >= w:
                    continue
                if mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
    return visited


def remove_background(
    data: bytes,
    output_format: str = "PNG",
    feather: bool = True,
) -> Optional[bytes]:
    """Удаляет белый фон у изображения и возвращает результат в заданном формате.

    Параметры:
      data          — байты исходного изображения (JPEG/PNG/WebP).
      output_format — "PNG" или "WEBP" (PNG предпочтителен — гарантированная
                      прозрачность).
      feather       — лёгкое сглаживание края (размытие альфы на 1px).

    Возвращает байты обработанного изображения или None, если не удалось
    (тогда вызывающий код должен оставить оригинал).
    """
    try:
        img = _load_image(data)
    except Exception:
        return None

    if img.width < 2 or img.height < 2:
        return None

    arr = np.asarray(img).astype(np.uint8)  # (H, W, 4)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3].copy()

    bg = _is_background(rgb)
    connected = _flood_fill_from_edges(bg)

    # Делаем связанную с краями белую область прозрачной.
    alpha[connected] = 0

    if feather:
        # Небольшое сглаживание края, чтобы не было зубчатой границы.
        alpha_img = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(0.6))
        alpha = np.asarray(alpha_img)

    out = arr.copy()
    out[:, :, 3] = alpha

    try:
        result = Image.fromarray(out, mode="RGBA")
        buf = io.BytesIO()
        fmt = output_format.upper()
        if fmt == "WEBP":
            result.save(buf, format="WEBP", lossless=True, quality=95)
        else:
            result.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return None
