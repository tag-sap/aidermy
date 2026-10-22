"""Единый сценарий «Скан по фото»: лицевая + задняя стороны упаковки.

Переиспользует существующие механизмы:
- DeepSeek Vision: identify_product (обе стороны) и recognize_composition (задняя);
- product_identification: локальный матчер кандидатов и web_search_product;
- scraper.import_product (внутри web_search_product);
- product_dedup.find_or_create_canonical_product — уже в /api/products/create.

Сервис ничего не пишет в БД: он возвращает карточку/черновик, а сохранение
выполняет существующий endpoint создания продукта после подтверждения.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from .ingredient_normalizer import split_inci_tokens
from .product_identification import (
    find_product_candidates,
    has_reliable_inci,
    web_search_product,
)
from .product_dedup import find_product_by_barcode
from .vision_service import identify_product, recognized_normalized_list, recognize_composition


class ProductScanError(RuntimeError):
    """Контролируемая ошибка единого сканирования."""


def _missing_fields(identified: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for key in ("brand", "product_name", "variant", "type", "volume", "barcode"):
        if not str(identified.get(key) or "").strip():
            missing.append(key)
    return missing


def _ingredients_text(items: List[str]) -> str:
    return ", ".join(item.strip() for item in items if item and item.strip())


def _clean_scraped_inci(value: Any) -> List[str]:
    """Убирает служебные маркеры страниц-агрегаторов из INCI со scraper."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = re.sub(r"\[(?:more|less)\]", ",", str(value or ""), flags=re.I)
    text = re.split(
        r"Read more|Highlights|Key Ingredients|Compare Report|Show all ingredients|"
        r"DETAILS|HOW TO USE|BENEFITS|TARGETS|•",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    return [
        part.strip(" .\u200b\u200c\ufeff")
        for part in split_inci_tokens(text)
        if part.strip(" .\u200b\u200c\ufeff")
    ]


def _base_draft(
    identified: Dict[str, Any],
    *,
    ingredients: List[str],
    ingredients_source: str,
    source_url: str = "",
    image_url: str = "",
    slug: str = "",
    product_id: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "id": product_id,
        "slug": slug,
        "brand": str(identified.get("brand") or "").strip(),
        "name": str(identified.get("product_name") or identified.get("name") or "").strip(),
        "variant": identified.get("variant"),
        "type": identified.get("type") or identified.get("category"),
        "volume": identified.get("volume"),
        "barcode": identified.get("barcode"),
        "ingredients": _ingredients_text(ingredients),
        "ingredients_list": ingredients,
        "ingredients_source": ingredients_source,
        "source_url": source_url,
        "image_url": image_url,
    }


def _can_analyze(ingredients: List[str]) -> bool:
    return len(ingredients) >= 2


def _recognized_ingredients(recognition: Dict[str, Any]) -> List[str]:
    """Возвращает INCI с задней стороны, если он пригоден для проверки."""
    if not recognition:
        return []
    return recognized_normalized_list(recognition)


async def scan_product_package(front_image: str, back_image: str | List[str]) -> Dict[str, Any]:
    """Распознаёт продукт и состав по обязательному front + одному/нескольким back.

    Несколько снимков задней стороны нужны для цилиндрических упаковок, где INCI
    не помещается в один кадр. Они передаются в существующий Vision как один набор.
    """
    if not (front_image or "").strip():
        raise ProductScanError("Загрузите фото лицевой стороны упаковки.")
    if isinstance(back_image, str):
        back_images = [back_image] if back_image.strip() else []
    else:
        back_images = [str(item).strip() for item in (back_image or []) if str(item).strip()]
    if not back_images:
        raise ProductScanError("Загрузите фото задней стороны упаковки (состав INCI).")

    warnings: List[str] = []

    # Обе стороны передаём в идентификацию: на задней может быть бренд/объём/
    # штрихкод. INCI читаем отдельно только с задних сторон, чтобы не смешивать
    # маркетинговый текст лицевой стороны с составом.
    identified_result, composition_result = await asyncio.gather(
        identify_product([front_image, *back_images]),
        recognize_composition(back_images),
        return_exceptions=True,
    )

    if isinstance(identified_result, Exception):
        # Ошибки конфигурации/недоступности Vision отдаём как 502, а не как
        # «пользователь плохо сфотографировал».
        if isinstance(identified_result, RuntimeError):
            raise identified_result
        raise ProductScanError(
            "Не удалось распознать бренд и название на лицевой стороне. "
            "Сфотографируйте этикетку ближе и повторите."
        ) from identified_result

    identified = dict(identified_result)
    identified["missing_fields"] = _missing_fields(identified)

    if isinstance(composition_result, Exception):
        recognition: Dict[str, Any] = {
            "is_inci": False,
            "ingredients": [],
            "raw_text": "",
            "uncertain_items": [],
            "overall_confidence": None,
        }
        warnings.append(
            "Не удалось прочитать состав на задней стороне. "
            "Проверьте фото или введите INCI вручную."
        )
    else:
        recognition = dict(composition_result)

    normalized = _recognized_ingredients(recognition)
    back_inci_reliable = len(normalized) >= 2 and bool(recognition.get("is_inci", True))
    if not back_inci_reliable:
        warnings.append("Состав на задней фотографии не распознан надёжно.")
    elif (recognition.get("uncertain_items") or []) or (
        recognition.get("overall_confidence") is not None
        and float(recognition.get("overall_confidence") or 0) < 0.7
    ):
        warnings.append("Часть состава распознана неуверенно — проверьте INCI перед анализом.")

    brand = str(identified.get("brand") or "").strip()
    name = str(identified.get("product_name") or identified.get("name") or "").strip()

    if not name or len(name) > 160 or (name.count(",") >= 8 and not brand):
        return {
            "status": "not_found",
            "message": "Не удалось прочитать бренд и название продукта. Сфотографируйте лицевую сторону ближе.",
            "identified": identified,
            "recognition": recognition,
            "warnings": warnings,
            "candidates": [],
            "draft": None,
        }

    # Штрихкод — сильнее нечёткого совпадения названия. Если он уже есть в
    # каталоге, повторное сканирование обязано вернуть ту же карточку, а не
    # создавать дубликат и не выбирать случайного кандидата.
    barcode_product = find_product_by_barcode(identified.get("barcode"))
    if barcode_product:
        if has_reliable_inci(barcode_product):
            return {
                "status": "ready",
                "message": "Продукт найден по штрихкоду.",
                "identified": identified,
                "recognition": recognition,
                "product": {
                    "id": barcode_product.get("id"),
                    "name": barcode_product.get("name") or name,
                    "slug": barcode_product.get("slug") or "",
                    "brand": barcode_product.get("brand") or brand,
                    "image_url": barcode_product.get("image_url") or "",
                    "category": barcode_product.get("category") or "",
                    "ingredients": barcode_product.get("ingredients") or "",
                    "barcode": barcode_product.get("barcode") or "",
                    "variant": barcode_product.get("variant") or "",
                    "ingredients_source": "local",
                    "source_url": "",
                    "has_inci": True,
                },
                "candidates": [],
                "draft": None,
                "can_analyze": True,
                "warnings": warnings,
            }

        draft = _base_draft(
            identified,
            ingredients=normalized,
            ingredients_source="back_photo" if back_inci_reliable else "none",
            image_url=barcode_product.get("image_url") or "",
            slug=barcode_product.get("slug") or "",
            product_id=barcode_product.get("id"),
        )
        draft["barcode"] = barcode_product.get("barcode") or identified.get("barcode")
        draft["variant"] = barcode_product.get("variant") or identified.get("variant")
        local_warnings = list(warnings)
        local_warnings.append(
            "Карточка найдена по штрихкоду, но в ней нет полного состава. Проверьте распознанный INCI."
        )
        return {
            "status": "needs_confirmation",
            "message": "Продукт найден по штрихкоду. Подтвердите состав.",
            "identified": identified,
            "recognition": recognition,
            "candidates": [],
            "draft": draft,
            "can_analyze": _can_analyze(normalized),
            "warnings": local_warnings,
        }

    candidates = find_product_candidates(brand, name, limit=5)
    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "message": "Найдено несколько похожих карточек. Выберите подходящую.",
            "identified": identified,
            "recognition": recognition,
            "candidates": candidates,
            "draft": _base_draft(
                identified,
                ingredients=normalized,
                ingredients_source="back_photo" if back_inci_reliable else "none",
            ),
            "warnings": warnings,
        }

    if len(candidates) == 1:
        candidate = candidates[0]
        if has_reliable_inci(candidate):
            return {
                "status": "ready",
                "message": "Продукт найден в каталоге Aidermy.",
                "identified": identified,
                "recognition": recognition,
                "product": {
                    "id": candidate.get("id"),
                    "slug": candidate.get("slug") or "",
                    "name": candidate.get("name") or name,
                    "brand": candidate.get("brand") or brand,
                    "image_url": candidate.get("image_url") or "",
                    "category": candidate.get("category") or "",
                    "ingredients": candidate.get("ingredients") or "",
                    "barcode": candidate.get("barcode") or "",
                    "variant": candidate.get("variant") or "",
                    "ingredients_source": "local",
                    "source_url": "",
                    "has_inci": True,
                },
                "candidates": [],
                "draft": None,
                "warnings": warnings,
            }

        local_warnings = list(warnings)
        local_warnings.append(
            "В карточке каталога нет полного состава. Используется состав с задней фотографии — проверьте его."
        )
        draft = _base_draft(
            identified,
            ingredients=normalized,
            ingredients_source="back_photo" if back_inci_reliable else "none",
            image_url=candidate.get("image_url") or "",
            slug=candidate.get("slug") or "",
            product_id=candidate.get("id"),
        )
        return {
            "status": "needs_confirmation",
            "message": "Карточка найдена, но состав нужно подтвердить.",
            "identified": identified,
            "recognition": recognition,
            "candidates": [],
            "draft": draft,
            "can_analyze": _can_analyze(normalized),
            "warnings": local_warnings,
        }


    # В локальной БД нет подходящего продукта — используем существующий Web Search
    # + scraper. Разрешаем вернуть карточку без полного INCI, чтобы дополнить её
    # распознанным составом с задней фотографии.
    web_product = await web_search_product(
        brand,
        name,
        identified.get("variant"),
        allow_unreliable_inci=True,
    )

    if web_product:
        scraped_ingredients = _clean_scraped_inci(web_product.get("ingredients"))
        scraped_reliable = len(scraped_ingredients) >= 2
        if scraped_reliable:
            ingredients = scraped_ingredients
            source = "scraped"
            source_url = str(web_product.get("source_url") or "")
            warnings_for_draft = [
                warning for warning in warnings
                if "задней" not in warning and "Часть состава" not in warning
            ]
        elif back_inci_reliable:
            ingredients = normalized
            source = "back_photo"
            source_url = str(web_product.get("source_url") or "")
            warnings_for_draft = list(warnings)
            warnings_for_draft.append(
                "На найденной странице состав неполный. Используется состав с задней фотографии — проверьте его."
            )
        else:
            ingredients = []
            source = "none"
            source_url = str(web_product.get("source_url") or "")
            warnings_for_draft = list(warnings)
            warnings_for_draft.append(
                "Найденная страница не содержит надёжного состава. Введите INCI вручную."
            )

        identified_for_draft = dict(identified)
        identified_for_draft["brand"] = web_product.get("brand") or identified.get("brand")
        identified_for_draft["product_name"] = web_product.get("name") or identified.get("product_name")
        identified_for_draft["name"] = identified_for_draft["product_name"]
        identified_for_draft["category"] = web_product.get("category") or identified.get("category")
        identified_for_draft["type"] = web_product.get("category") or identified.get("type")
        identified_for_draft["volume"] = web_product.get("volume") or identified.get("volume")
        identified_for_draft["missing_fields"] = _missing_fields(identified_for_draft)

        draft = _base_draft(
            identified_for_draft,
            ingredients=ingredients,
            ingredients_source=source,
            source_url=source_url,
            image_url=str(web_product.get("image_url") or ""),
        )
        return {
            "status": "needs_confirmation",
            "message": "Продукт найден в интернете. Проверьте данные и сохраните карточку.",
            "identified": identified_for_draft,
            "recognition": recognition,
            "candidates": [],
            "draft": draft,
            "can_analyze": _can_analyze(ingredients),
            "warnings": warnings_for_draft,
        }

    # Внешний поиск не дал результата. Не выдумываем URL; если состав с задней
    # стороны пригоден, отдаём черновик для ручного подтверждения.
    if back_inci_reliable:
        warnings_for_draft = list(warnings)
        warnings_for_draft.append(
            "Внешний поиск не нашёл подходящую карточку. Состав взят с задней фотографии — проверьте его."
        )
        draft = _base_draft(
            identified,
            ingredients=normalized,
            ingredients_source="back_photo",
            source_url="",
        )
        return {
            "status": "needs_confirmation",
            "message": "Продукт не найден во внешнем поиске. Можно сохранить карточку с составом с фото.",
            "identified": identified,
            "recognition": recognition,
            "candidates": [],
            "draft": draft,
            "can_analyze": True,
            "warnings": warnings_for_draft,
        }

    warnings_for_draft = list(warnings)
    warnings_for_draft.append(
        "Внешний поиск не нашёл карточку, а состав не распознан. Введите INCI вручную."
    )
    draft = _base_draft(
        identified,
        ingredients=[],
        ingredients_source="none",
        source_url="",
    )
    return {
        "status": "needs_confirmation",
        "message": "Не удалось получить состав автоматически. Проверьте данные и введите INCI.",
        "identified": identified,
        "recognition": recognition,
        "candidates": [],
        "draft": draft,
        "can_analyze": False,
        "warnings": warnings_for_draft,
    }

