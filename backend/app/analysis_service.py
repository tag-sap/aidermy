from __future__ import annotations

from typing import Any, Dict, List

from .ingredient_normalizer import canonicalize_ingredient_name, normalize_ingredient_name
from .ingredient_repository import IngredientRepository
from .scoring_engine import apply_hard_filters, score_product_against_profile


class AnalysisService:
    def __init__(self, ingredient_repository: IngredientRepository | None = None):
        self.repository = ingredient_repository or IngredientRepository()
        self.repository.ensure_ingredient_tables()

    def prepare_product_ingredients(self, raw_ingredients: str | List[str]) -> List[str]:
        if isinstance(raw_ingredients, str):
            cleaned = raw_ingredients.split(',') if ',' in raw_ingredients else raw_ingredients.split('\n')
            items = [canonicalize_ingredient_name(item) for item in cleaned]
        else:
            items = [canonicalize_ingredient_name(item) for item in raw_ingredients]
        return [item for item in items if item]

    def find_unknown_ingredients(self, ingredients: str | List[str]) -> List[str]:
        """Ингредиенты, которых нет в Ingredient DB (для AI #2 Enrichment)."""
        from .ingredient_enrichment import find_unknown_ingredients

        normalized = self.prepare_product_ingredients(ingredients)
        return find_unknown_ingredients(normalized, self.repository)

    def analyze(
        self,
        product_name: str,
        ingredients: str | List[str],
        user_profile: Dict[str, Any],
        priorities: Dict[str, float],
        knowledge: Dict[str, Dict[str, Dict[str, float]]] | None = None,
    ):
        normalized_ingredients = self.prepare_product_ingredients(ingredients)
        if knowledge is None:
            knowledge = self.repository.get_knowledge_map()

        # Hard filters выполняются ДО скоринга: если есть нарушения — товар исключён.
        hard_filters = apply_hard_filters(user_profile, normalized_ingredients)

        result = score_product_against_profile(
            ingredients=normalized_ingredients,
            knowledge=knowledge,
            user_profile=user_profile,
            priority_weights=priorities,
        )
        result['product_name'] = product_name
        result['normalized_ingredients'] = normalized_ingredients
        result['hard_filters'] = hard_filters
        result['excluded'] = bool(hard_filters)
        return result
