from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class Profile(BaseModel):
    name: Optional[str] = Field(default="", description="Имя пользователя")
    age: str = Field(..., description="Возрастная группа")
    concerns: List[str] = Field(default=[], description="Проблемы кожи")
    allergies: List[str] = Field(default=[], description="Аллергии")
    custom_text: Optional[str] = Field(default="", description="Дополнительный комментарий")
    
    quiz_answers: Optional[Dict[str, str]] = Field(
        default=None, 
        description="Ответы на опросник о коже"
    )
    skin_type_determined: Optional[str] = Field(
        default=None, 
        description="Тип кожи, определенный автоматически"
    )

class CheckRequest(BaseModel):
    product_name: str = Field(..., description="Название косметического продукта")
    skin_type: str = Field(..., description="Тип кожи пользователя")
    profile: Profile = Field(..., description="Анкета пользователя")

# НОВЫЕ МОДЕЛИ ДЛЯ ОТВЕТА
class ActiveIngredient(BaseModel):
    name: str
    position: int
    concentration: str  # "высокая", "средняя", "низкая"
    effectiveness: str  # "рабочая", "средняя", "минимальная"

class HowToUse(BaseModel):
    application: str
    time: str
    note: Optional[str] = None

class Expectations(BaseModel):
    when: str
    normal: str
    danger: str

class CheckResponse(BaseModel):
    score: int
    verdict: str
    summary: str
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

class CheckWithIngredientsRequest(BaseModel):
    product_name: str
    skin_type: str
    profile: Profile
    ingredients: str