# research_queue.py
# Фаза 9 — Batch Research Engine + request-level waiting.
#
# Принцип: анализ дожидается Research (а не пересчитывает уже показанный score).
# Одинаковые задачи дедуплицируются; множество задач → ОДИН AI-запрос (batch).

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .axes import AXES
from .ingredient_normalizer import normalize_ingredient_name
from .ingredient_repository import IngredientRepository
from .instrumentation import METRICS

INGREDIENT_RESEARCH = "INGREDIENT_RESEARCH"
INTERACTION_RESEARCH = "INTERACTION_RESEARCH"

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Конфигурация (Фаза 9).
RESEARCH_BATCH_SIZE = 25
RESEARCH_MAX_ATTEMPTS = 3
RESEARCH_WAIT_TIMEOUT = 90.0
RESEARCH_POLL_INTERVAL = 0.5

_RESEARCH_MODEL_FALLBACKS = ["deepseek-chat"]
_RESEARCH_MAX_TOKENS = 8000
_EFFECT_MAGNITUDE = {"weak": 0.3, "moderate": 0.6, "strong": 1.0}

_batch_lock = threading.Lock()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ingredient_dedup_key(name: str) -> str:
    return f"ingredient:{normalize_ingredient_name(name)}"


def _interaction_dedup_key(a: str, b: str) -> str:
    a_c, b_c = sorted([normalize_ingredient_name(a), normalize_ingredient_name(b)])
    return f"interaction:{a_c}|{b_c}"


def enqueue_research(
    repository: Optional[IngredientRepository] = None,
    unknown_ingredients: Optional[List[str]] = None,
    interaction_pairs: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[List[int], int]:
    """Ставит задачи в очередь с дедупликацией. Возвращает (task_ids, created_count)."""
    repo = repository or IngredientRepository()
    task_ids: List[int] = []
    created = 0
    for raw in (unknown_ingredients or []):
        key = normalize_ingredient_name(raw)
        if not key or key in {"water", "aqua"}:
            continue
        tid, was_created = repo.enqueue_research_task(
            INGREDIENT_RESEARCH, _ingredient_dedup_key(key), {"ingredient": key}
        )
        task_ids.append(tid)
        if was_created:
            created += 1
            METRICS.increment("research_task_created")
        else:
            METRICS.increment("research_task_deduplicated")
    for a, b in (interaction_pairs or []):
        a_c, b_c = sorted([normalize_ingredient_name(a), normalize_ingredient_name(b)])
        tid, was_created = repo.enqueue_research_task(
            INTERACTION_RESEARCH, _interaction_dedup_key(a_c, b_c), {"ingredient_a": a_c, "ingredient_b": b_c}
        )
        task_ids.append(tid)
        if was_created:
            created += 1
            METRICS.increment("research_task_created")
        else:
            METRICS.increment("research_task_deduplicated")
    return task_ids, created


def _aggregate_status(tasks: List[Dict[str, Any]]) -> str:
    statuses = {t.get("status") for t in tasks}
    if not statuses:
        return STATUS_COMPLETED
    if any(s in (STATUS_PENDING, STATUS_PROCESSING) for s in statuses):
        return STATUS_PENDING
    if STATUS_FAILED in statuses:
        return STATUS_FAILED
    return STATUS_COMPLETED


async def run_research(
    repository: Optional[IngredientRepository] = None,
    unknown_ingredients: Optional[List[str]] = None,
    interaction_pairs: Optional[List[Tuple[str, str]]] = None,
    timeout: Optional[float] = None,
) -> str:
    """Enqueue → dedup → batch → wait. Возвращает 'completed' | 'failed' | 'timeout'."""
    repo = repository or IngredientRepository()
    task_ids, _created = enqueue_research(repo, unknown_ingredients, interaction_pairs)
    if not task_ids:
        return STATUS_COMPLETED

    timeout = timeout if timeout is not None else RESEARCH_WAIT_TIMEOUT
    t0 = time.perf_counter()
    while True:
        await _process_batch(repo)
        tasks = repo.get_research_tasks(task_ids)
        status = _aggregate_status(tasks)
        if status in (STATUS_COMPLETED, STATUS_FAILED):
            METRICS.add_time("research_wait_duration", time.perf_counter() - t0)
            if status == STATUS_COMPLETED:
                METRICS.increment("research_success")
            else:
                METRICS.increment("research_failure")
            invalidate_knowledge_caches()
            return status
        if time.perf_counter() - t0 > timeout:
            METRICS.increment("research_wait_timeout")
            METRICS.add_time("research_wait_duration", time.perf_counter() - t0)
            return "timeout"
        METRICS.increment("research_waiters")
        await asyncio.sleep(RESEARCH_POLL_INTERVAL)


async def _process_batch(repo: IngredientRepository) -> int:
    """Забирает pending-задачи и обрабатывает их batch'ом. Возвращает число обработанных."""
    with _batch_lock:
        tasks = repo.claim_pending_research_tasks(RESEARCH_BATCH_SIZE)
    if not tasks:
        return 0
    METRICS.increment("research_batch_created")
    METRICS.set_gauge("research_batch_size", len(tasks))
    ingredient_tasks = [t for t in tasks if t["task_type"] == INGREDIENT_RESEARCH]
    interaction_tasks = [t for t in tasks if t["task_type"] == INTERACTION_RESEARCH]
    if ingredient_tasks:
        await _process_ingredient_tasks(repo, ingredient_tasks)
    if interaction_tasks:
        await _process_interaction_tasks(repo, interaction_tasks)
    return len(tasks)


# ---------------------------------------------------------------------------
# Ingredient research (canonical 6 axes)
# ---------------------------------------------------------------------------
_INGREDIENT_RESEARCH_PROMPT = (
    "Ты — косметический химик. Для каждого INCI-ингредиента из списка составь "
    "запись, используя ТОЛЬКО канонические оси эффектов.\n\n"
    "Ингредиенты:\n{names}\n\n"
    "Канонические оси: hydration, barrier, irritation, sensitization, sebum, pigmentation.\n"
    "Верни ТОЛЬКО JSON-массив объектов:\n"
    '[{{"inci_name": "...", "canonical_name": "...", "aliases": ["..."], '
    '"effects": [{{"axis": "hydration|barrier|irritation|sensitization|sebum|pigmentation", '
    '"direction": "positive|negative", "effect_magnitude": "weak|moderate|strong", '
    '"confidence": 0..1, "evidence": "...", "source": "..."}}]}}]\n\n'
    "ВАЖНО: не выводи hydration из barrier и наоборот; stinging/burning → irritation, "
    "аллерген/сенсибилизация → sensitization; sebum — только прямое влияние на себум; "
    "pigmentation — только прямое влияние на пигментацию; механизмы (humectant, exfoliant, "
    "antioxidant, occlusive) сами по себе НЕ создают эффект; если данных недостаточно — "
    "НЕ включай ось (отсутствие ≠ neutral). Верни ТОЛЬКО JSON."
)


async def _call_ingredient_research(names: List[str]) -> Optional[List[dict]]:
    from .services import DEEPSEEK_API_KEY, DEEPSEEK_API_URL

    if not DEEPSEEK_API_KEY:
        return None
    import httpx

    prompt = _INGREDIENT_RESEARCH_PROMPT.format(names="\n".join(f"- {n}" for n in names))
    for model in _RESEARCH_MODEL_FALLBACKS:
        try:
            METRICS.increment("research_ai_calls")
            METRICS.increment("ai_call_count")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": _RESEARCH_MAX_TOKENS,
                    },
                    timeout=60,
                )
            if response.status_code != 200:
                continue
            content = response.json()["choices"][0]["message"]["content"]
            records = _parse_json_records(content)
            if records is not None:
                return records
        except Exception:
            continue
    return None


async def _process_ingredient_tasks(repo: IngredientRepository, tasks: List[Dict[str, Any]]) -> None:
    names = [json.loads(t["payload"])["ingredient"] for t in tasks]
    results = await _call_ingredient_research(names)
    if results is None:
        _fail_tasks(repo, tasks, "AI research unavailable")
        return
    result_map: Dict[str, dict] = {}
    for r in results:
        if isinstance(r, dict):
            key = normalize_ingredient_name(r.get("inci_name") or r.get("canonical_name") or "")
            if key:
                result_map[key] = r
    for t in tasks:
        name = json.loads(t["payload"])["ingredient"]
        record = result_map.get(name)
        if record is not None and _save_ingredient_result(repo, name, record):
            repo.complete_research_task(t["id"])
            METRICS.increment("research_items_completed")
        else:
            _fail_task(repo, t, "invalid or missing ingredient result")


def _save_ingredient_result(repo: IngredientRepository, name: str, record: Dict[str, Any]) -> bool:
    claims: List[Dict[str, Any]] = []
    for eff in record.get("effects") or []:
        if not isinstance(eff, dict):
            continue
        axis = str(eff.get("axis") or "")
        direction = str(eff.get("direction") or "").strip().lower()
        if axis not in AXES or direction not in ("positive", "negative"):
            continue
        claims.append({
            "property_name": axis,
            "direction": direction,
            "strength": _EFFECT_MAGNITUDE.get(str(eff.get("effect_magnitude") or "").strip().lower(), 0.5),
            "confidence": _num(eff.get("confidence")),
            "evidence_level": eff.get("evidence") or eff.get("source") or "moderate",
        })
    data = {
        "inci_name": record.get("inci_name") or name,
        "canonical_name": record.get("canonical_name") or name,
        "normalized_name": normalize_ingredient_name(record.get("inci_name") or name),
        "synonyms": record.get("aliases") or [],
        "claims": claims,
        "confidence": _num(record.get("confidence")),
        "allergen": record.get("allergen") or {},
    }
    try:
        return bool(repo.save_enriched_ingredient(data))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Interaction research (canonical 6 axes, только совместное A+B)
# ---------------------------------------------------------------------------
_INTERACTION_RESEARCH_PROMPT = (
    "Ты — косметический химик. Оцени ВЗАИМОДЕЙСТВИЕ пар ингредиентов (совместное "
    "воздействие), а НЕ сумму индивидуальных эффектов.\n\n"
    "Пары:\n{pairs}\n\n"
    "Канонические оси: hydration, barrier, irritation, sensitization, sebum, pigmentation.\n"
    "Верни ТОЛЬКО JSON-массив объектов:\n"
    '[{{"ingredient_a": "...", "ingredient_b": "...", "interactions": [{{"axis": "...", '
    '"direction": "positive|negative", "effect_magnitude": "weak|moderate|strong", '
    '"confidence": 0..1, "evidence": "...", "source": "..."}}]}}]\n\n'
    "ВАЖНО: создавай interaction только если evidence описывает СОВМЕСТНОЕ воздействие A+B; "
    "суммирование индивидуальных эффектов выполняет Scoring Engine. Верни ТОЛЬКО JSON."
)


async def _call_interaction_research(pairs: List[Tuple[str, str]]) -> Optional[List[dict]]:
    from .services import DEEPSEEK_API_KEY, DEEPSEEK_API_URL

    if not DEEPSEEK_API_KEY:
        return None
    import httpx

    prompt = _INTERACTION_RESEARCH_PROMPT.format(pairs="\n".join(f"- {a} + {b}" for a, b in pairs))
    for model in _RESEARCH_MODEL_FALLBACKS:
        try:
            METRICS.increment("research_ai_calls")
            METRICS.increment("ai_call_count")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    DEEPSEEK_API_URL,
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": _RESEARCH_MAX_TOKENS,
                    },
                    timeout=60,
                )
            if response.status_code != 200:
                continue
            content = response.json()["choices"][0]["message"]["content"]
            records = _parse_json_records(content)
            if records is not None:
                return records
        except Exception:
            continue
    return None


async def _process_interaction_tasks(repo: IngredientRepository, tasks: List[Dict[str, Any]]) -> None:
    pairs = [(json.loads(t["payload"])["ingredient_a"], json.loads(t["payload"])["ingredient_b"]) for t in tasks]
    results = await _call_interaction_research(pairs)
    if results is None:
        _fail_tasks(repo, tasks, "AI research unavailable")
        return
    result_map: Dict[Tuple[str, str], dict] = {}
    for r in results:
        if isinstance(r, dict):
            a = normalize_ingredient_name(r.get("ingredient_a") or "")
            b = normalize_ingredient_name(r.get("ingredient_b") or "")
            if a and b:
                result_map[tuple(sorted([a, b]))] = r
    for t in tasks:
        payload = json.loads(t["payload"])
        a, b = payload["ingredient_a"], payload["ingredient_b"]
        record = result_map.get(tuple(sorted([a, b])))
        if record is not None and _save_interaction_result(repo, record):
            repo.complete_research_task(t["id"])
            METRICS.increment("research_items_completed")
        else:
            _fail_task(repo, t, "invalid or missing interaction result")


def _save_interaction_result(repo: IngredientRepository, record: Dict[str, Any]) -> bool:
    saved_any = False
    for inter in record.get("interactions") or []:
        if not isinstance(inter, dict):
            continue
        axis = str(inter.get("axis") or "")
        direction = str(inter.get("direction") or "").strip().lower()
        if axis not in AXES or direction not in ("positive", "negative"):
            continue
        try:
            repo.save_interaction(
                ingredient_a=record.get("ingredient_a"),
                ingredient_b=record.get("ingredient_b"),
                axis=axis,
                direction=direction,
                strength=_EFFECT_MAGNITUDE.get(str(inter.get("effect_magnitude") or "").strip().lower(), 0.5),
                confidence=_num(inter.get("confidence")),
                evidence=inter.get("evidence") or "",
                source=inter.get("source") or "research",
                source_type="research",
                interaction_type="conflict",
            )
            saved_any = True
        except Exception:
            continue
    return saved_any


def _fail_tasks(repo: IngredientRepository, tasks: List[Dict[str, Any]], error: str) -> None:
    for t in tasks:
        _fail_task(repo, t, error)


def _fail_task(repo: IngredientRepository, task: Dict[str, Any], error: str) -> None:
    status = repo.fail_research_task(task["id"], error, RESEARCH_MAX_ATTEMPTS)
    if status == STATUS_FAILED:
        METRICS.increment("research_items_failed")
    else:
        METRICS.increment("research_retry")


def _parse_json_records(content: str) -> Optional[List[dict]]:
    """Парсит ответ AI: JSON-массив либо объект с полем ingredients/data/interactions."""
    s = str(content or "").strip()
    if not s:
        return None
    start_arr, end_arr = s.find("["), s.rfind("]")
    start_obj, end_obj = s.find("{"), s.rfind("}")
    try:
        if start_arr != -1 and end_arr != -1 and (start_arr < start_obj or start_obj == -1):
            obj = json.loads(s[start_arr:end_arr + 1])
        elif start_obj != -1 and end_obj != -1:
            obj = json.loads(s[start_obj:end_obj + 1])
        else:
            obj = json.loads(s)
    except Exception:
        return None
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return obj.get("ingredients") or obj.get("data") or obj.get("interactions") or []
    return None


def invalidate_knowledge_caches() -> None:
    """Инвалидирует Knowledge Graph + Static Product Model после Research."""
    try:
        from .ingredient_graph import GRAPH
        GRAPH.invalidate()
    except Exception:
        pass
    try:
        import app.product_model as pm
        pm._cache.clear()
        pm._context_cache.clear()
    except Exception:
        pass

