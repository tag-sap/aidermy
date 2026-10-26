from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ProductImportResult:
    name: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    image_url: str | None = None
    price: float | None = None
    currency: str | None = None
    volume: str | None = None
    category: str | None = None
    description: str | None = None
    ingredients_raw: str | None = None
    source_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def has_product_data(self) -> bool:
        if not self.name:
            return False
        # A site title such as "COSRX | EXPECTING TOMORROW" is not a product,
        # but "Brand | Product Name" is a valid product title on many stores.
        if "|" in self.name:
            title_markers = (
                "official site", "official store", "official shop",
                "expecting tomorrow", "shop all", "онлайн-магазин", "интернет-магазин",
            )
            parts = [part.strip().lower() for part in self.name.split("|") if part.strip()]
            if any(part == "home" or any(marker in part for marker in title_markers) for part in parts):
                return False
        # «Состав» = весь текст страницы (не INCI) — не валидные данные товара.
        if self.ingredients_raw and len(self.ingredients_raw) > 15000:
            return False
        blocked_markers = (
            "включен javascript", "checking device", "just a moment",
            "captcha", "access denied", "проверка устройства",
        )
        haystack = " ".join(filter(None, (self.name, self.description))).lower()
        if any(marker in haystack for marker in blocked_markers):
            return False
        return bool(self.description or self.ingredients_raw or self.image_url)
