# ingredient_graph.py
# Фаза 2 — Ingredient Graph access layer (cache-first, канонические 6 осей, unknown != 0).
#
# Это точка чтения ингредиентного знания для будущих слоёв. НЕ меняет scoring:
#   - get_knowledge_map()         — legacy-карта (для совместимости со scoring);
#   - get_canonical_knowledge_map() — каноническая 6-осевая карта (для новых слоёв);
#   - lookup_effect() / lookup_interaction() — состояния known / insufficient / unknown.
#
# Кэш — in-memory, инвалидируется явно после enrichment (GRAPH.invalidate()).

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from .axes import AXES
from .ingredient_normalizer import normalize_ingredient_name
from .ingredient_repository import IngredientRepository
from .instrumentation import METRICS

# Порог достаточности знания (конфигурируемый, а не захардкоженный в lookup'ах).
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


class EffectState:
    KNOWN = "known"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class IngredientGraph:
    """Кэширующий access layer над IngredientRepository.

    Отсутствие знания (нет записи) ≠ нулевой эффект: unknown не превращается
    в direction/strength. Низкая confidence ≠ unknown: insufficient сохраняет
    факт, что запись есть, но доказательства слабые.
    """

    def __init__(
        self,
        repository: Optional[IngredientRepository] = None,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._repo = repository or IngredientRepository()
        self._threshold = confidence_threshold
        self._lock = threading.Lock()
        self._legacy_cache: Optional[Dict[str, Any]] = None
        self._canonical_cache: Optional[Dict[str, Any]] = None

    @property
    def confidence_threshold(self) -> float:
        return self._threshold

    def invalidate(self) -> None:
        """Сброс кэша (после enrichment/записи новых знаний)."""
        with self._lock:
            self._legacy_cache = None
            self._canonical_cache = None

    # ------------------------------------------------------------------
    # Cache-first чтение карт
    # ------------------------------------------------------------------
    def get_knowledge_map(self) -> Dict[str, Any]:
        """Legacy knowledge map (для scoring-совместимости). Cache-first."""
        with self._lock:
            if self._legacy_cache is None:
                METRICS.increment("cache_miss")
                self._legacy_cache = self._repo.get_knowledge_map()
            else:
                METRICS.increment("cache_hit")
            return self._legacy_cache

    def get_canonical_knowledge_map(self) -> Dict[str, Any]:
        """Каноническая 6-осевая карта. Cache-first."""
        with self._lock:
            if self._canonical_cache is None:
                METRICS.increment("cache_miss")
                self._canonical_cache = self._repo.get_canonical_knowledge_map()
            else:
                METRICS.increment("cache_hit")
            return self._canonical_cache

    # ------------------------------------------------------------------
    # Effects lookup
    # ------------------------------------------------------------------
    def lookup_effect(self, ingredient: str, axis: str) -> Dict[str, Any]:
        """Состояние эффекта ингредиента по одной канонической оси."""
        key = normalize_ingredient_name(ingredient)
        if axis not in AXES:
            return {"ingredient": key, "axis": axis, "state": EffectState.UNKNOWN, "reason": "invalid_axis"}
        entry = self.get_canonical_knowledge_map().get(key, {}).get(axis)
        if entry is None:
            return {"ingredient": key, "axis": axis, "state": EffectState.UNKNOWN}
        confidence = float(entry.get("confidence") or 0.0)
        state = EffectState.KNOWN if confidence >= self._threshold else EffectState.INSUFFICIENT
        return {
            "ingredient": key,
            "axis": axis,
            "state": state,
            "direction": entry.get("direction"),
            "strength": entry.get("strength"),
            "confidence": confidence,
        }

    def lookup_effects(self, ingredient: str) -> Dict[str, Dict[str, Any]]:
        """Все 6 канонических осей ингредиента с состояниями (unknown != 0)."""
        return {axis: self.lookup_effect(ingredient, axis) for axis in AXES}

    # ------------------------------------------------------------------
    # Interaction lookup (интерфейс для будущего ingredient_interactions)
    # ------------------------------------------------------------------
    def lookup_interaction(self, ingredient_a: str, ingredient_b: str) -> Dict[str, Any]:
        """Interaction A×B: known / unknown.

        Таблицы ingredient_interactions ещё нет (Фаза 3), поэтому состояние всегда
        unknown. Здесь НЕ создаётся временная логика поверх CONFLICT_RULES.
        """
        return {
            "a": normalize_ingredient_name(ingredient_a),
            "b": normalize_ingredient_name(ingredient_b),
            "state": EffectState.UNKNOWN,
            "reason": "no_interaction_table",
        }


# Глобальный (per-process) экземпляр для совместного кэша.
GRAPH = IngredientGraph()
