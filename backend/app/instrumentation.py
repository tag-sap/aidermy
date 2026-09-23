# instrumentation.py
# Фаза 0 — лёгкая инструментация пайплайна (без изменения бизнес-логики).
#
# Реестр счётчиков/таймеров/gauges. Позволяет измерять:
#   db_query_count, ai_call_count, ingredient_count, interaction_candidate_count,
#   pipeline_duration и т.д. — для реальных Before/After бенчмарков.
#
# НЕ влияет на scoring и поведение API: только накапливает числа.

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Dict


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        self._timers: Dict[str, float] = {}
        self._gauges: Dict[str, int] = {}

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount

    def add_time(self, name: str, seconds: float) -> None:
        with self._lock:
            self._timers[name] = self._timers.get(name, 0.0) + seconds

    def set_gauge(self, name: str, value: int) -> None:
        with self._lock:
            self._gauges[name] = value

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "timers": {k: round(v, 4) for k, v in self._timers.items()},
                "gauges": dict(self._gauges),
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._timers.clear()
            self._gauges.clear()

    @contextmanager
    def timer(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add_time(name, time.perf_counter() - t0)


METRICS = MetricsRegistry()
