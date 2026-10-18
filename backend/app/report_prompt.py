# report_prompt.py
# Управляемая конфигурация AI Report prompt (admin AI/Report tab).
#
# Prompt хранится в БД (report_prompt_versions), версии immutable после создания.
# Production prompt — ровно одна строка с is_production=1. Это ОТДЕЛЬНАЯ версия,
# независимая от score_engine_version: Score Engine считает score/verdict, а Report
# prompt лишь определяет, КАК LLM объясняет уже готовый deterministic result.
#
# НЕ содержит знание о скоринге и НЕ меняет score/verdict/factors/weights.

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .postgres_connection import get_postgres_connection

# ---------------------------------------------------------------------------
# Первичный production prompt (v1) — текущий prompt, вынесенный из services.py
# generate_report_once(). Сохраняется как первая DB-версия при первом обращении.
# ---------------------------------------------------------------------------
REPORT_PROMPT_V1_SYSTEM = """Ты объясняешь уже рассчитанный персональный результат проверки косметического продукта.

ВАЖНО:
- Score и verdict уже рассчитаны deterministic Score Engine.
- Никогда не пересчитывай процент.
- Никогда не меняй verdict.
- Не придумывай свойства ингредиентов.
- Не придумывай связь ингредиент → цель пользователя.
- Используй только сохранённые goal_evidence и deterministic factors, переданные ниже.
- Полный INCI дан только для проверки названий ингредиентов.
- Если для ингредиента нет подтверждённой связи с целью пользователя, не приписывай ему такую связь.

ЗАДАЧА:
Напиши одно короткое человеческое объяснение, почему средство получило именно такой результат для этого пользователя.

При наличии подтверждённых данных обязательно старайся назвать 1–2 наиболее значимых конкретных ингредиента или фактора, которые действительно объясняют результат.

Логика текста:
1. Что важно именно для профиля пользователя.
2. Какой конкретный ингредиент или фактор из сохранённых данных работает в пользу или против этого профиля.
3. Как совокупность этих факторов объясняет итоговый результат.

Не перечисляй весь состав.
Не перечисляй Score Engine axes, веса, contribution, проценты вкладов или внутренние технические термины.
Не используй структуры «Что улучшает результат», «Что снижает результат», «Плюсы», «Минусы».
Не ставь медицинские диагнозы и не обещай лечение или гарантированный эффект.
Не давай самостоятельных медицинских назначений.
Не выдумывай ограничения или преимущества, которых нет в переданных данных.
Если подтверждённых ingredient × concern данных недостаточно, лучше написать более общий короткий текст, чем придумать связь.

Верни ТОЛЬКО JSON:
{
  "summary": "короткое персональное объяснение",
  "expectations": "короткое реалистичное ожидание" | null
}

Если безопасного ожидания нет — используй null.
Не возвращай score или verdict: они показываются отдельно из deterministic результата.
"""

REPORT_PROMPT_V1_USER_TEMPLATE = """Продукт: {{product_name}}
Тип продукта (категория): {{product_type}}
Инструкция по категории (что можно/нельзя заключать для этого типа средства):
{{category_knowledge}}
Тип кожи: {{skin_type}}

Данные о целях пользователя и сохранённые связи ингредиент × цель (если применимы):
{{goal_evidence}}
Если результат заблокирован на первой фазе, не обсуждай цели пользователя и не оценивай
потенциальную пользу продукта: объясни только подтверждённые отрицательные факторы.

ЕДИНЫЙ НАБОР ФАКТОВ (источник истины — НЕ переопределяй):
{{deterministic_input}}

Полный состав (только для справки о названиях ингредиентов, НЕ для самостоятельного анализа):
{{inci}}"""

# Доступные placeholders в user_prompt_template (для Admin UI).
REPORT_PROMPT_PLACEHOLDERS: List[str] = [
    "product_name",
    "product_type",
    "category_knowledge",
    "skin_type",
    "goal_evidence",
    "deterministic_input",
    "inci",
]


def _now() -> str:
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")



def ensure_report_prompt_tables() -> None:
    """Проверяет наличие таблицы промптов в Supabase."""
    with get_postgres_connection() as conn:
        row = conn.execute("""
            SELECT to_regclass('public.report_prompt_versions') AS table_name
        """).fetchone()
        if not row or not row["table_name"]:
            raise RuntimeError(
                "В Supabase отсутствует public.report_prompt_versions"
            )


def _row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    d = dict(row)
    return {
        "id": d.get("id"),
        "version": d.get("version"),
        "name": d.get("name") or "",
        "system_prompt": d.get("system_prompt") or "",
        "user_prompt_template": d.get("user_prompt_template") or "",
        "description": d.get("description"),
        "is_production": bool(d.get("is_production")),
        "created_at": d.get("created_at"),
        "created_by": d.get("created_by") or "",
    }


def seed_report_prompt() -> Optional[Dict[str, Any]]:
    """Создаёт v1 только если таблица Supabase действительно пуста."""
    ensure_report_prompt_tables()
    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "LOCK TABLE public.report_prompt_versions IN EXCLUSIVE MODE"
            )
            cur.execute(
                "SELECT COUNT(*) AS n FROM public.report_prompt_versions"
            )
            if cur.fetchone()["n"] > 0:
                return None

            cur.execute("""
                INSERT INTO public.report_prompt_versions
                    (id, version, name, system_prompt, user_prompt_template,
                     description, is_production, created_at, created_by)
                VALUES (
                    (SELECT COALESCE(MAX(id), 0) + 1
                     FROM public.report_prompt_versions),
                    1, %s, %s, %s, %s, 1, %s, %s
                )
                RETURNING *
            """, (
                "Report Prompt v1",
                REPORT_PROMPT_V1_SYSTEM,
                REPORT_PROMPT_V1_USER_TEMPLATE,
                "Первичный production prompt (перенесён из services.generate_report_once)",
                _now(),
                "system",
            ))
            row = cur.fetchone()
        conn.commit()
        return _row_to_dict(row) if row else None


def list_report_prompts() -> List[Dict[str, Any]]:
    ensure_report_prompt_tables()
    seed_report_prompt()
    with get_postgres_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM public.report_prompt_versions
            ORDER BY version DESC
        """).fetchall()
        return [_row_to_dict(row) for row in rows]


def get_report_prompt_by_id(prompt_id: int) -> Optional[Dict[str, Any]]:
    ensure_report_prompt_tables()
    with get_postgres_connection() as conn:
        row = conn.execute("""
            SELECT * FROM public.report_prompt_versions WHERE id = %s
        """, (prompt_id,)).fetchone()
        return _row_to_dict(row) if row else None


def get_report_prompt_by_version(version: int) -> Optional[Dict[str, Any]]:
    ensure_report_prompt_tables()
    with get_postgres_connection() as conn:
        row = conn.execute("""
            SELECT * FROM public.report_prompt_versions WHERE version = %s
        """, (version,)).fetchone()
        return _row_to_dict(row) if row else None


def get_production_report_prompt() -> Dict[str, Any]:
    """Возвращает активную production-версию из Supabase."""
    ensure_report_prompt_tables()
    seed_report_prompt()
    with get_postgres_connection() as conn:
        row = conn.execute("""
            SELECT * FROM public.report_prompt_versions
            WHERE is_production = 1
            ORDER BY version DESC
            LIMIT 1
        """).fetchone()
        if row:
            return _row_to_dict(row)

    v1 = get_report_prompt_by_version(1)
    return v1 or {}


def create_report_prompt(
    name: str,
    system_prompt: str,
    user_prompt_template: str,
    description: str = "",
    created_by: str = "",
) -> Dict[str, Any]:
    """Создаёт новую immutable-версию в Supabase."""
    ensure_report_prompt_tables()
    seed_report_prompt()

    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "LOCK TABLE public.report_prompt_versions IN EXCLUSIVE MODE"
            )
            cur.execute("""
                SELECT COALESCE(MAX(version), 0) AS max_version,
                       COALESCE(MAX(id), 0) AS max_id
                FROM public.report_prompt_versions
            """)
            current = cur.fetchone()
            new_version = int(current["max_version"]) + 1
            new_id = int(current["max_id"]) + 1

            cur.execute("""
                INSERT INTO public.report_prompt_versions
                    (id, version, name, system_prompt, user_prompt_template,
                     description, is_production, created_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s)
                RETURNING *
            """, (
                new_id,
                new_version,
                (name or "").strip() or f"Report Prompt v{new_version}",
                system_prompt or "",
                user_prompt_template or "",
                description or None,
                _now(),
                created_by or "",
            ))
            row = cur.fetchone()
        conn.commit()
        return _row_to_dict(row) if row else {}


def publish_report_prompt(prompt_id: int) -> Optional[Dict[str, Any]]:
    """Атомарно переключает production-флаг на выбранную версию."""
    ensure_report_prompt_tables()

    with get_postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "LOCK TABLE public.report_prompt_versions IN EXCLUSIVE MODE"
            )
            cur.execute("""
                SELECT * FROM public.report_prompt_versions WHERE id = %s
            """, (prompt_id,))
            if not cur.fetchone():
                return None

            cur.execute("""
                UPDATE public.report_prompt_versions SET is_production = 0
                WHERE is_production <> 0
            """)
            cur.execute("""
                UPDATE public.report_prompt_versions
                SET is_production = 1
                WHERE id = %s
            """, (prompt_id,))
            cur.execute("""
                SELECT * FROM public.report_prompt_versions WHERE id = %s
            """, (prompt_id,))
            row = cur.fetchone()
        conn.commit()
        return _row_to_dict(row) if row else None


def render_report_prompt(
    prompt: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, str]:
    """Заполняет placeholders в user_prompt_template. Возвращает {system, user}."""
    system_prompt = str(prompt.get("system_prompt") or "")
    template = str(prompt.get("user_prompt_template") or "")
    rendered = template
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", str(value if value is not None else ""))
    return {"system": system_prompt, "user": rendered}


def build_report_context(
    product_name: str,
    analysis: Dict[str, Any],
    profile: Dict[str, Any],
    product_type: str = "",
) -> Dict[str, Any]:
    """Собирает контекст placeholders для персонального Report."""
    from .services import _build_report_input, _report_input_text

    inp = _build_report_input(analysis)
    profile = profile or {}

    skin = str(
        profile.get("skin_type")
        or profile.get("skin_type_determined")
        or ""
    )

    is_blocked_report = inp.get("phase1_status") == "blocked"

    if is_blocked_report:
        # Заблокированный результат объясняется только подтверждёнными
        # факторами Score Engine. Не передаём модели свободный текст
        # профиля, где могут упоминаться лекарства и сторонние средства.
        profile_context = {
            "skin_type": "",
            "age": "",
            "concerns": [],
            "allergies": [],
            "custom_text": "",
            "structured": {},
        }
    else:
        profile_context = {
            "skin_type": skin,
            "age": profile.get("age") or "",
            "concerns": profile.get("concerns") or [],
            "allergies": profile.get("allergies") or [],
            "custom_text": profile.get("custom_text") or "",
            "structured": profile.get("structured") or {},
        }

    # При blocked цели намеренно исключены из контекста: отчёт объясняет
    # причину отказа, а не перечисляет потенциальные достоинства продукта.
    goal_context = json.dumps(
        [] if is_blocked_report else (inp.get("goal_evidence") or []),
        ensure_ascii=False,
    )
    input_text = _report_input_text(inp)
    input_text += """

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА ДОСТОВЕРНОСТИ ОТЧЁТА:
- Используй только ингредиенты, явно присутствующие в переданном составе.
  Не добавляй ингредиенты по памяти, по типу продукта или по аналогии.
- Описывай только свойства, которые подтверждены переданными
  детерминированными факторами и данными об ингредиентах.
- Не приписывай продукту отшелушивание, регенерацию, лифтинг,
  омоложение, действие на коллаген или другие эффекты, которые
  не подтверждены данными Score Engine.
- Не делай вывод о пользе или риске только по названию продукта.
- Если подтверждён фактор, объясняй его простым пользовательским языком.
  Не упоминай внутренние оси, вклады, баллы или технические статусы.
- Не заменяй отсутствующие сведения догадками. Не заявляй, что профиль
  неполный, если это прямо не подтверждено данными.
- Верни полноценное связное объяснение на основе имеющихся факторов,
  без выдуманных деталей и без шаблонных обещаний.
"""
    if inp.get("phase1_status") == "blocked":
        input_text += """

ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА ПОЛЬЗОВАТЕЛЬСКОГО ЯЗЫКА ДЛЯ ЭТОГО ОТЧЁТА:
- Не используй медицинские и профессиональные термины, в частности слово
  «сенсибилизация». Объясняй подтверждённый риск простыми словами:
  «повышенный риск нежелательной реакции кожи».
- Не утверждай, что профиль заполнен не полностью: сам статус blocked
  этого не означает.
- При blocked не обсуждай цели пользователя, эффективность продукта или его возможные преимущества.
- Объясняй отказ только подтверждёнными отрицательными факторами. Не придумывай риски,
  свойства ингредиентов или связь с лечением.
- Называй 1–2 главных ингредиента из переданных отрицательных факторов. Если у ингредиента
  есть однозначное общеупотребительное русское название, используй его и добавь точное INCI
  в скобках; если перевод неоднозначен — оставь INCI как есть.
- Не называй продукт причиной аллергии и не ставь диагноз.
- Пиши коротко, понятно и без внутренних терминов Score Engine.
"""
    inci = ", ".join(str(i) for i in (inp.get("inci") or []))

    from .category_knowledge import render_category_knowledge

    return {
        "product_name": product_name,
        "product_type": product_type or "не указан",
        "category_knowledge": render_category_knowledge(product_type) or "—",
        "skin_type": ("не передаётся при заблокированном результате" if is_blocked_report else (skin or "не указан")),
        "profile_context": json.dumps(
            profile_context,
            ensure_ascii=False,
            indent=2,
        ),
        "goal_evidence": goal_context or "[]",
        "deterministic_input": input_text,
        "inci": inci or "—",
    }


def _inject_category_knowledge_placeholder(template: str) -> str:
    if "{{category_knowledge}}" in template:
        return template
    marker = "{{product_type}}"
    if marker in template:
        return template.replace(
            marker,
            marker + "\nИнструкция по категории (что можно/нельзя заключать для этого типа средства):\n{{category_knowledge}}",
            1,
        )
    return template + "\nИнструкция по категории:\n{{category_knowledge}}"


def ensure_category_knowledge_prompt() -> Optional[Dict[str, Any]]:
    """Миграция: добавляет placeholder {{category_knowledge}} в production prompt,
    если он ещё отсутствует. Создаёт новую версию и публикует её (идемпотентно)."""
    prompt = get_production_report_prompt()
    if not prompt or not prompt.get("user_prompt_template"):
        return None
    if "{{category_knowledge}}" in prompt["user_prompt_template"]:
        return prompt
    new_template = _inject_category_knowledge_placeholder(prompt["user_prompt_template"])
    created = create_report_prompt(
        name=f"{prompt.get('name', 'Report Prompt')} + category knowledge",
        system_prompt=prompt.get("system_prompt") or "",
        user_prompt_template=new_template,
        description="Добавлен placeholder {{category_knowledge}} (база знаний категорий).",
        created_by="system",
    )
    if created and created.get("id"):
        return publish_report_prompt(created["id"])
    return None
