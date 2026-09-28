# vector_index.py — in-memory retrieval index поверх product_vectors.
#
# SQLite = source of truth (product_vectors), здесь — in-memory retrieval index.
# Для ~5k товаров pure-Python clamped dot достаточно (микросекунды). Интерфейс
# `search` оставляет возможность позже заменить backend (NumPy/FAISS) без
# изменения scoring layer.
#
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from .product_vector import clamped_dot
from .scoring_config import AXES

_VECTOR_COLS = ("v_hydration", "v_barrier", "v_irritation", "v_sensitization", "v_sebum", "v_pigmentation")


class VectorIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids: List[int] = []
        self._vectors: List[Dict[str, float]] = []
        self._meta: Dict[int, Dict[str, Any]] = {}

    def rebuild(self, rows: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._ids = [int(r["product_id"]) for r in rows]
            self._vectors = [
                {axis: float(r.get(col) or 0.0) for axis, col in zip(AXES, _VECTOR_COLS)}
                for r in rows
            ]
            self._meta = {
                int(r["product_id"]): {
                    "representation_type": r.get("representation_type"),
                    "coverage": r.get("coverage"),
                    "unknown_count": r.get("unknown_count"),
                    "composition_hash": r.get("composition_hash"),
                }
                for r in rows
            }

    def is_loaded(self) -> bool:
        return bool(self._ids)

    def size(self) -> int:
        return len(self._ids)

    def get_meta(self, product_id: int) -> Optional[Dict[str, Any]]:
        return self._meta.get(product_id)

    def search(
        self,
        weights: Dict[str, float],
        top_k: int,
        predicate=None,
    ) -> List[Tuple[int, float]]:
        """Clamped Dot retrieval. predicate(pid)->bool — hard filter (вне блокировки)."""
        with self._lock:
            ids = list(self._ids)
            vectors = list(self._vectors)

        scored: List[Tuple[int, float]] = []
        for pid, vec in zip(ids, vectors):
            if predicate is not None and not predicate(pid):
                continue
            scored.append((pid, clamped_dot(vec, weights)))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:top_k]


VECTOR_INDEX = VectorIndex()


def get_vector_index() -> VectorIndex:
    return VECTOR_INDEX


def load_vector_index(repository=None) -> VectorIndex:
    from .ingredient_repository import IngredientRepository

    repo = repository or IngredientRepository()
    repo.ensure_ppm_tables()
    VECTOR_INDEX.rebuild(repo.get_all_product_vectors())
    return VECTOR_INDEX
