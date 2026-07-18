from pydantic import BaseModel, Field
from typing import Optional, List

class Profile(BaseModel):
    name: Optional[str] = Field(default="", description="Имя пользователя")
    age: str = Field(..., description="Возрастная группа")
    concerns: List[str] = Field(default=[], description="Проблемы кожи")
    allergies: List[str] = Field(default=[], description="Аллергии")
    custom_text: Optional[str] = Field(default="", description="Дополнительный комментарий")

class CheckRequest(BaseModel):
    product_name: str = Field(..., description="Название косметического продукта")
    skin_type: str = Field(..., description="Тип кожи пользователя")
    profile: Profile = Field(..., description="Анкета пользователя")

class CheckResponse(BaseModel):
    score: int
    verdict: str
    summary: str
    safe_ingredients: List[str] = []
    caution_ingredients: List[str] = []
    cached: bool = False
    slug: Optional[str] = None

class CheckWithIngredientsRequest(BaseModel):
    product_name: str
    skin_type: str
    profile: Profile
    ingredients: str