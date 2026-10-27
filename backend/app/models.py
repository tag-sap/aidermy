from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any

class Profile(BaseModel):
    name: Optional[str] = Field(default="", description="Имя пользователя")
    age: str = Field(..., description="Возрастная группа")
    concerns: List[str] = Field(default=[], description="Проблемы кожи")
    allergies: List[str] = Field(default=[], description="Аллергии")
    intolerances: List[str] = Field(default=[], description="Непереносимости")
    custom_text: Optional[str] = Field(default="", description="Дополнительный комментарий")
    
    quiz_answers: Optional[Dict[str, str]] = Field(
        default=None, 
        description="Ответы на опросник о коже"
    )
    skin_type_determined: Optional[str] = Field(
        default=None, 
        description="Тип кожи, определенный автоматически"
    )
    structured: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Структурированный профиль (canonical IDs -> PROFILE_MATRIX)",
    )

class CheckRequest(BaseModel):
    product_name: str = Field(..., description="Название косметического продукта")
    skin_type: str = Field(..., description="Тип кожи пользователя")
    profile: Profile = Field(..., description="Анкета пользователя")
    # Пользовательское фото (URL из /api/uploads/product-image), необязательное.
    image_url: Optional[str] = None
    # Гостевой контекст: обязателен для запроса без авторизации (одна проверка).
    guest_token: Optional[str] = None

# НОВЫЕ МОДЕЛИ ДЛЯ ОТВЕТА
class ActiveIngredient(BaseModel):
    name: str
    position: int
    concentration: str  # "высокая" (позиция 1 в INCI = максимальная концентрация)
    effectiveness: Optional[str] = None  # удалено: не оцениваем «эффективность» через AI

class HowToUse(BaseModel):
    application: Optional[str] = None
    time: Optional[str] = None
    note: Optional[str] = None

class Expectations(BaseModel):
    when: Optional[str] = None
    normal: Optional[str] = None
    danger: Optional[str] = None

class CheckResponse(BaseModel):
    score: Optional[int] = None
    verdict: str
    summary: str
    pending: Optional[bool] = None
    phase1_status: Optional[str] = None
    recommendation_status: Optional[str] = None
    stats: Optional[Dict[str, int]] = Field(default_factory=dict)
    skin_type_recommendation: Optional[str] = None
    safe_ingredients: List[str] = []
    caution_ingredients: List[str] = []
    cached: bool = False
    slug: Optional[str] = None
    image_url: Optional[str] = None
    # НОВЫЕ ПОЛЯ
    active_ingredients: Optional[ActiveIngredient] = None
    how_to_use: Optional[HowToUse] = None
    expectations: Optional[Expectations] = None
    report: Optional[str] = None
    analysis_id: Optional[int] = None
    goal_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    # Трассировка замещения взаимодействий (None, если interactions не применялись).
    interaction_replacement: Optional[Dict[str, Any]] = None
    # Применим ли кожный скоринг к категории (макияж/парфюм — нет).
    score_scope: Optional[Dict[str, Any]] = None

class CheckWithIngredientsRequest(BaseModel):
    product_name: str
    skin_type: str
    profile: Profile
    ingredients: str
    brand: Optional[str] = None
    # Пользовательское фото (URL из /api/uploads/product-image), необязательное.
    image_url: Optional[str] = None
    # Гостевой контекст: обязателен для запроса без авторизации (одна проверка).
    guest_token: Optional[str] = None


class ImportUrlRequest(BaseModel):
    url: str = Field(..., min_length=1, description="URL страницы товара")


class RecognizeCompositionRequest(BaseModel):
    images: List[str] = Field(..., description="Base64 data URL фотографий одной серии")


class ProductIdentifyRequest(BaseModel):
    images: List[str] = Field(..., description="Base64 data URL фотографий продукта/упаковки")


class ProductScanRequest(BaseModel):
    front_image: str = Field(..., min_length=20, description="Фото лицевой стороны (data URL)")
    back_image: Optional[str] = Field(default=None, min_length=20, description="Фото задней стороны (старый клиент)")
    back_images: List[str] = Field(default_factory=list, description="Фото задней стороны (одно или несколько)")

    @model_validator(mode="after")
    def _normalize_back_images(self):
        # A front photo is enough to identify a product and start web search.
        # Back photos are optional and are requested later if INCI is missing.
        if self.back_image and self.back_image not in self.back_images:
            self.back_images.insert(0, self.back_image)
        return self


class ProductWebSearchRequest(BaseModel):
    brand: str = Field(default="", description="Бренд продукта")
    name: str = Field(default="", description="Название продукта")
    variant: Optional[str] = Field(default=None, description="Вариант продукта")


class AnalyzeCompositionRequest(BaseModel):
    product_name: str = Field(..., min_length=1, description="Название продукта")
    brand: str = Field(default="", description="Бренд продукта")
    slug: str = Field(default="", description="Slug продукта (опционально)")
    ingredients: List[str] = Field(default=[], description="Распознанный список INCI")
    skin_type: str = Field(default="Нормальная", description="Тип кожи")
    profile: Profile = Field(..., description="Анкета пользователя")


class CreateProductRequest(BaseModel):
    brand: str = Field(default="", description="Бренд продукта")
    name: str = Field(..., min_length=1, description="Название продукта")
    ingredients: List[str] = Field(default=[], description="Распознанный список INCI")
    slug: str = Field(default="", description="Slug продукта (опционально)")
    # Данные единого сканирования: лицевое фото хранится в постоянном S3,
    # source_url — найденная карточка товара, volume/barcode — с упаковки.
    image_data_url: Optional[str] = Field(default=None, description="Лицевое фото (data URL) для постоянного хранения")
    source_url: Optional[str] = Field(default=None, description="URL найденной карточки товара")
    volume: Optional[str] = Field(default=None, description="Объём/вес с упаковки")
    variant: Optional[str] = Field(default=None, description="Вариант/линейка с упаковки")
    barcode: Optional[str] = Field(default=None, description="Штрихкод с упаковки")
    category: Optional[str] = Field(default=None, description="Тип/категория продукта")
    source_type: Optional[str] = Field(default=None, description="Источник данных: scan/retailer/url")