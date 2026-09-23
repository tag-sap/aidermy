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

import re
import threading
from typing import Any, Dict, List, Optional

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
        self._interaction_map_cache: Optional[Dict[tuple, list]] = None
        self._class_map_cache: Optional[Dict[str, List[str]]] = None

    @property
    def confidence_threshold(self) -> float:
        return self._threshold

    def invalidate(self) -> None:
        """Сброс кэша (после enrichment/записи новых знаний)."""
        with self._lock:
            self._legacy_cache = None
            self._canonical_cache = None
            self._interaction_map_cache = None
            self._class_map_cache = None

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
    # Interaction lookup (Фаза 3A: реальный lookup, cache-first)
    # ------------------------------------------------------------------
    def _interaction_map(self) -> Dict[tuple, list]:
        """Cache-first карта (a,b) -> список interaction-записей."""
        with self._lock:
            if self._interaction_map_cache is None:
                METRICS.increment("cache_miss")
                self._repo.ensure_interaction_tables()
                m: Dict[tuple, list] = {}
                for r in self._repo.get_all_interactions():
                    key = (r["ingredient_a"], r["ingredient_b"])
                    m.setdefault(key, []).append(r)
                self._interaction_map_cache = m
            else:
                METRICS.increment("cache_hit")
            return self._interaction_map_cache

    def lookup_interaction(self, ingredient_a: str, ingredient_b: str) -> Dict[str, Any]:
        """Interaction A×B: known / insufficient / unknown (unknown ≠ no interaction).

        Пара канонизируется (сортировка), A×B == B×A. Возвращает состояние по
        порогу confidence и список записей по осям (с source/evidence).
        """
        METRICS.increment("interaction_lookup_count")
        a_c, b_c = sorted([normalize_ingredient_name(ingredient_a), normalize_ingredient_name(ingredient_b)])
        records = self._interaction_map().get((a_c, b_c), [])
        if not records:
            METRICS.increment("interaction_unknown_count")
            return {"a": a_c, "b": b_c, "state": EffectState.UNKNOWN, "records": []}

        out = []
        has_known = False
        for r in records:
            conf = float(r.get("confidence") or 0.0)
            state = EffectState.KNOWN if conf >= self._threshold else EffectState.INSUFFICIENT
            if state == EffectState.KNOWN:
                has_known = True
            out.append({
                "interaction_id": r.get("id"),
                "axis": r.get("axis"),
                "direction": r.get("direction"),
                "strength": r.get("strength"),
                "confidence": conf,
                "state": state,
                "source": r.get("source"),
                "evidence": r.get("evidence"),
            })
        agg = EffectState.KNOWN if has_known else EffectState.INSUFFICIENT
        if agg == EffectState.KNOWN:
            METRICS.increment("interaction_known_count")
        else:
            METRICS.increment("interaction_insufficient_count")
        return {"a": a_c, "b": b_c, "state": agg, "records": out}

    # ------------------------------------------------------------------
    # Фаза 4 — Taxonomy / Class layer (routing/index, НЕ доказательство)
    # ------------------------------------------------------------------
    def _class_map(self) -> Dict[str, List[str]]:
        with self._lock:
            if self._class_map_cache is None:
                METRICS.increment("cache_miss")
                self._repo.ensure_taxonomy_tables()
                self._class_map_cache = self._repo.get_ingredient_class_map()
            else:
                METRICS.increment("cache_hit")
            return self._class_map_cache

    def lookup_classes(self, ingredient: str) -> List[str]:
        """Классы ингредиента (листья + предки). Пусто = класс неизвестен."""
        METRICS.increment("class_lookup_count")
        return list(self._class_map().get(normalize_ingredient_name(ingredient), []))

    @staticmethod
    def _split_ingredients(raw: Any) -> List[str]:
        out: List[str] = []
        for part in re.split(r"[,;\n]+", str(raw or "")):
            n = normalize_ingredient_name(part)
            if n:
                out.append(n)
        return out

    def class_route(self, shelf_products: List[Dict[str, Any]], candidate_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Классовый routing: релевантные (candidate, shelf) пары по классам.

        Это ИНДЕКС/фильтр, а не доказательство interaction: релевантность по классам
        лишь сокращает пространство поиска; итог решает exact ingredient lookup.
        """
        routes = self._repo.get_class_routes()

        shelf_classes: List[set] = []
        for p in shelf_products:
            s = set()
            for ing in self._split_ingredients(p.get("ingredients")):
                s.update(self.lookup_classes(ing))
            shelf_classes.append(s)

        cand_classes: List[set] = []
        for p in candidate_products:
            s = set()
            for ing in self._split_ingredients(p.get("ingredients")):
                s.update(self.lookup_classes(ing))
            cand_classes.append(s)

        before = len(candidate_products) * len(shelf_products)
        relevant = 0
        class_pairs: set = set()
        pairs: List[tuple] = []
        for i, cc in enumerate(cand_classes):
            for j, sc in enumerate(shelf_classes):
                if not cc or not sc:
                    continue
                if self._classes_relevant(cc, sc, routes):
                    relevant += 1
                    pairs.append((candidate_products[i], shelf_products[j]))
                self._collect_class_pairs(cc, sc, routes, class_pairs)

        METRICS.set_gauge("interaction_candidate_count_before", before)
        METRICS.set_gauge("interaction_candidate_count_after", relevant)
        METRICS.set_gauge("class_filtered_count", before - relevant)
        METRICS.set_gauge("class_pair_count", len(class_pairs))
        return {"before": before, "after": relevant, "pairs": pairs}

    @staticmethod
    def _classes_relevant(cc: set, sc: set, routes) -> bool:
        for route_a, route_b in routes:
            a, b = set(route_a), set(route_b)
            if (cc & a) and (sc & b):
                return True
            if (cc & b) and (sc & a):
                return True
        return False

    @staticmethod
    def _collect_class_pairs(cc: set, sc: set, routes, class_pairs: set) -> None:
        for route_a, route_b in routes:
            a, b = set(route_a), set(route_b)
            for ca in (cc & a):
                for cb in (sc & b):
                    class_pairs.add((ca, cb))
            for ca in (cc & b):
                for cb in (sc & a):
                    class_pairs.add((ca, cb))


# Глобальный (per-process) экземпляр для совместного кэша.
GRAPH = IngredientGraph()
