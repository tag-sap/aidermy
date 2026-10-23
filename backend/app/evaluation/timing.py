"""Small, secret-free stage timer for Evaluation V2.

All durations use ``time.perf_counter`` (monotonic). The timer is deliberately
independent of the database/network layers so it can be used in pure tests and
in the worker thread without changing the scoring contracts.

Only names, counts and durations are emitted. Profiles, tokens, quotes and
provider payloads must never be passed to this module.
"""
from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from time import perf_counter
from typing import Iterator, Mapping


class StageTimer:
    def __init__(self, **fields: object) -> None:
        self._fields = {str(key): value for key, value in fields.items()}
        self._started = perf_counter()
        self._stages: dict[str, float] = {}
        self._lock = threading.Lock()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.add(name, perf_counter() - started)

    def add(self, name: str, seconds: float) -> None:
        with self._lock:
            self._stages[name] = self._stages.get(name, 0.0) + max(0.0, seconds)

    def as_dict(self, **extra: object) -> dict:
        with self._lock:
            stages = {
                name: round(seconds * 1000, 3)
                for name, seconds in sorted(self._stages.items())
            }
        return {
            **self._fields,
            **extra,
            "stages_ms": stages,
            "total_ms": round((perf_counter() - self._started) * 1000, 3),
        }

    def log(self, logger: logging.Logger, *, event: str = "EVALUATION PERF", **extra: object) -> dict:
        payload = self.as_dict(**extra)
        logger.info("[%s] %s", event, json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return payload
