from pydantic import BaseModel, Field
from typing import List, Optional

class Profile(BaseModel):
    name: Optional[str] = Field(default="", description="Имя пользователя")
    age: str = Field(..., description="Возрастная группа")
    concerns: List[str] = Field(default=[], description="Проблемы кожи")
    allergies: List[str] = Field(default=[], description="Аллергии")
    custom_text: Optional[str] = Field(default="", description="Дополнительный комментарий")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Оля",
                "skin_type": "Сухая",
                "age": "25–35",
                "concerns": ["Акне", "Пигментация"],
                "allergies": ["Отдушки"],
                "custom_text": "кожа стягивается после умывания"
            }
        }

class CheckRequest(BaseModel):
    product_name: str = Field(..., description="Название косметического продукта")
    skin_type: str = Field(..., description="Тип кожи пользователя")
    profile: Profile = Field(..., description="Анкета пользователя")

    class Config:
        json_schema_extra = {
            "example": {
                "product_name": "Erborian BB крем",
                "skin_type": "Сухая",
                "profile": {
                    "name": "Оля",
                    "age": "25–35",
                    "concerns": ["Акне"],
                    "allergies": ["Отдушки"],
                    "custom_text": ""
                }
            }
        }

class CheckResponse(BaseModel):
    score: int
    verdict: str
    summary: str
    safe_ingredients: List[str] = []
    caution_ingredients: List[str] = []
    cached: bool = False
    slug: Optional[str] = None  # <- ДОБАВИТЬ
    class Config:
        json_schema_extra = {
            "example": {
                "score": 87,
                "verdict": "Подходит",
                "summary": "Продукт хорошо подходит для сухой кожи.",
                "safe_ingredients": ["Глицерин", "Вода"],
                "caution_ingredients": ["Парабены"],
                "cached": False
            }
        }
class CheckWithIngredientsRequest(BaseModel):
    product_name: str
    skin_type: str
    profile: Profile
    ingredients: str