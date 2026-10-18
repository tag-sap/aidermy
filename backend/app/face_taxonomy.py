"""Единая каноническая таксономия средств ухода за лицом Aidermy.

10 категорий и их подкатегории. Единственный источник истины для:
  - навигации каталога;
  - карточки продукта (категория -> подкатегория);
  - «Моей полки» и автоподбора;
  - допустимых категорий для Score Engine и калибровки.

Значения совпадают с колонками products.catalog_category / catalog_subcategory.
"""

from __future__ import annotations

from typing import Dict, List

FACE_TAXONOMY: List[Dict[str, object]] = [
    {"key": "cleansing", "title": "Очищение", "subcategories": [
        "Гели и пенки", "Молочко", "Бальзамы и масла", "Мицеллярная вода", "Энзимные средства",
    ]},
    {"key": "toning", "title": "Тонизация", "subcategories": [
        "Тонеры", "Лосьоны", "Эссенции",
    ]},
    {"key": "serums", "title": "Сыворотки и концентраты", "subcategories": [
        "Увлажняющие", "От акне и воспалений", "Осветляющие", "Антивозрастные", "Для восстановления барьера",
    ]},
    {"key": "moisturizing", "title": "Увлажнение", "subcategories": [
        "Кремы", "Гели", "Флюиды", "Эмульсии",
    ]},
    {"key": "barrier", "title": "Восстановление кожного барьера", "subcategories": [
        "Кремы с церамидами", "Восстанавливающие бальзамы", "Средства для чувствительной кожи",
    ]},
    {"key": "masks", "title": "Маски", "subcategories": [
        "Увлажняющие", "Очищающие", "Успокаивающие", "Питательные", "Ночные",
    ]},
    {"key": "exfoliation", "title": "Эксфолиация", "subcategories": [
        "Кислотные средства", "Энзимные пудры", "Пилинги", "Скрабы",
    ]},
    {"key": "sun", "title": "Защита от солнца", "subcategories": [
        "SPF 30", "SPF 50", "Для лица", "Для чувствительной кожи", "Тонированные SPF",
    ]},
    {"key": "eyes", "title": "Уход за областью вокруг глаз", "subcategories": [
        "Кремы", "Сыворотки", "Патчи",
    ]},
    {"key": "lips", "title": "Уход за губами", "subcategories": [
        "Бальзамы", "Маски", "Скрабы", "SPF для губ",
    ]},
]


def face_category_titles() -> List[str]:
    """Заголовки 10 канонических категорий (для SQL-фильтра допустимости)."""
    return [str(c["title"]) for c in FACE_TAXONOMY]


def face_category_title_to_key() -> Dict[str, str]:
    return {str(c["title"]): str(c["key"]) for c in FACE_TAXONOMY}
