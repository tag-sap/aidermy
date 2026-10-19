"""Метаданные юридических документов и реквизиты исполнителя.

ВАЖНО: документы находятся в статусе "draft" — это проекты, подготовленные к
согласованию. ИНН не заполнен, цены не утверждены. Публикация документов и
приём платежей разрешаются владельцем отдельным решением после юридической
проверки. Версия документа сохраняется вместе с каждым согласием пользователя,
поэтому при утверждении текста версию нужно поднять.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

LEGAL_DOCUMENTS: Dict[str, Dict[str, Any]] = {
    "requisites": {
        "slug": "requisites",
        "title": "Реквизиты",
        "version": "draft-1",
        "status": "draft",
    },
    "offer": {
        "slug": "offer",
        "title": "Публичная оферта",
        "version": "draft-1",
        "status": "draft",
    },
    "privacy": {
        "slug": "privacy",
        "title": "Политика обработки персональных данных",
        "version": "draft-1",
        "status": "draft",
    },
    "payment": {
        "slug": "payment",
        "title": "Оплата и возвраты",
        "version": "draft-1",
        "status": "draft",
    },
    "delete-account": {
        "slug": "delete-account",
        "title": "Удаление аккаунта",
        "version": "draft-1",
        "status": "draft",
    },
}

# Реквизиты исполнителя. ИНН и телефон НЕ заполняются в коде: их вносит владелец
# после проверки. Пустые значения не должны отображаться как подтверждённые.
EXECUTOR: Dict[str, str] = {
    "service": "айдерми (Aidermy)",
    "name": "Сапаров Тагир Бауржанович",
    "status": "Плательщик налога на профессиональный доход (самозанятый), Россия",
    "inn": "",
    "email": "aidermy@yandex.com",
    "phone": "",
    "activity": (
        "Предоставление доступа к цифровому сервису анализа составов косметических "
        "средств и оценки их совместимости с профилем кожи пользователя."
    ),
}

# Типы согласий, которые сервер принимает и хранит.
CONSENT_TYPES = ("offer", "privacy", "payment_terms")


def document_version(slug: str) -> Optional[str]:
    doc = LEGAL_DOCUMENTS.get((slug or "").strip())
    return doc["version"] if doc else None


def require_document_version(slug: str) -> str:
    version = document_version(slug)
    if not version:
        raise ValueError(f"Неизвестный документ: {slug}")
    return version


def legal_meta() -> Dict[str, Any]:
    """Метаданные для фронтенда: версии документов и статус реквизитов."""
    return {
        "documents": LEGAL_DOCUMENTS,
        "executor": {
            "service": EXECUTOR["service"],
            "name": EXECUTOR["name"],
            "status": EXECUTOR["status"],
            "email": EXECUTOR["email"],
            "inn_filled": bool(EXECUTOR["inn"].strip()),
            "phone_filled": bool(EXECUTOR["phone"].strip()),
        },
    }
