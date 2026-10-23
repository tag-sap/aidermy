"""Questionnaire answers → evaluated parameters.

The identity of a stored evaluation is the questionnaire option the user chose:

    ``<section>:<option>``                    e.g. ``problem:acne_general``
    ``procedure:<procedure>@<period>``        e.g. ``procedure:recent_laser@<7``
    ``intolerance:ingredient:<name>``         a concrete ingredient from a
                                              structured profile

Product-level technical aspects (sebum, comedogenicity, barrier, ...) are NOT
evaluated units: they only describe what to look for inside a questionnaire
parameter (``Parameter.product_axes``). This keeps shared product knowledge bound
to what the user actually selected instead of an invented universal scorecard.

No importance weights are produced here: every relevant parameter gets an equal
share in ``engine.py`` (plain arithmetic mean). Relevance only selects WHICH
parameters matter for this profile. Pure module: no I/O, no network, no AI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import questionnaire as q
from .contracts import ContractError, Parameter

# ---------------------------------------------------------------------------
# 0..100 scale: wording is derived from the parameter's own question, so the
# anchors never promise a clinical effect, safety or harm.
# ---------------------------------------------------------------------------
ANCHORS_BENEFIT: tuple[tuple[int, str], ...] = (
    (0, "Подтверждённое свойство состава прямо противоречит требованию пункта; "
        "отсутствие специального назначения само по себе не является таким противоречием"),
    (25, "Подтверждённые свойства в основном не соответствуют требованию, "
         "есть отдельные совпадения"),
    (50, "Данные частично соответствуют и частично не соответствуют требованию; "
         "это осознанно обоснованное смешанное соответствие, а не «неизвестно»"),
    (75, "Подтверждённые свойства в основном соответствуют требованию, "
         "есть второстепенные ограничения"),
    (100, "Подтверждённые свойства прямо соответствуют требованию; "
          "существенных подтверждённых возражений нет"),
)
ANCHORS_RISK: tuple[tuple[int, str], ...] = (
    (0, "Подтверждённый конфликт с требованием пункта (например, вещество, "
        "которого пользователь избегает)"),
    (25, "Подтверждённые данные в основном указывают на риск, "
         "но есть отдельные смягчающие факторы"),
    (50, "Данные смешанные: есть и подтверждённые факторы риска, и смягчающие "
         "факторы; это не «неизвестно»"),
    (75, "Подтверждённых существенных факторов риска мало; "
         "остаются отдельные ограничения данных"),
    (100, "Подтверждённых конфликтов с требованием пункта не найдено "
          "в пределах доступного состава и источников; это не абсолютная гарантия"),
)

_RISK_SECTIONS = {"therapy", "procedure", "intolerance"}

_SECTION_LABEL = {
    "skin_type": "Тип кожи",
    "problem": "Проблема",
    "therapy": "Лечение",
    "procedure": "Процедура",
    "intolerance": "Непереносимость",
    "goal": "Цель",
}

_QUESTION = {
    "skin_type": "Подходит ли состав для кожи типа «{label}»?",
    "problem": "Соответствует ли состав задаче «{label}»?",
    "therapy": "Совместим ли состав с активной терапией «{label}»?",
    "procedure": "Применим ли состав в период «{period}» после процедуры «{label}»?",
    "intolerance": "Можно ли использовать состав при непереносимости «{label}»?",
    "goal": "Соответствует ли состав цели «{label}»?",
}

_DEFINITION = {
    "skin_type": (
        "Соответствие типу кожи «{label}»: подтверждённые свойства состава, "
        "значимые для этого типа кожи ({aspects}), и отсутствие подтверждённых "
        "факторов, которые ему противоречат."
    ),
    "problem": (
        "Соответствие задаче «{label}»: подтверждённые свойства состава, значимые "
        "для этой задачи ({aspects}), и отсутствие подтверждённых факторов, которые "
        "её усиливают."
    ),
    "therapy": (
        "Безопасное сочетание с активной терапией «{label}»: отсутствие "
        "подтверждённых конфликтов и дублирования активов; учитываются {aspects}."
    ),
    "procedure": (
        "Применимость состава в период «{period}» после процедуры «{label}»: "
        "отсутствие подтверждённых факторов риска; учитываются {aspects}."
    ),
    "intolerance": (
        "Отсутствие в составе компонентов категории «{label}» ({aspects}); "
        "учитываются только подтверждённые сведения о наличии этих компонентов."
    ),
    "goal": (
        "Соответствие цели «{label}»: подтверждённые свойства состава, значимые для "
        "этой цели ({aspects})."
    ),
}

_LABEL = {
    "skin_type": "Тип кожи: «{label}»",
    "problem": "Проблема: «{label}»",
    "therapy": "Лечение: «{label}»",
    "procedure": "Процедура: «{label}», {period}",
    "intolerance": "Непереносимость: «{label}»",
    "goal": "Цель: «{label}»",
}


# What to look for inside each questionnaire option (research hints only; the
# stored result stays bound to the questionnaire parameter, never to these axes).
ASPECTS: dict[str, str] = {
    # skin type
    "skin_type:normal": "сбалансированная формула без избыточной нагрузки",
    "skin_type:dry": "увлажнение, липиды, барьер",
    "skin_type:oily": "себорегуляция, лёгкая текстура, некомедогенность",
    "skin_type:combination": "увлажнение без избыточной окклюзии, себорегуляция Т-зоны",
    "skin_type:sensitive": "отсутствие раздражителей и аллергенов, поддержка барьера",
    # problems
    "problem:acne_general": "себорегуляция, кератинизация, воспаление, комедогенность",
    "problem:sebum_pores": "себорегуляция, размер пор, комедогенность",
    "problem:dryness": "увлажнение, липиды, барьер",
    "problem:sensitivity": "раздражители, аллергены, барьер",
    "problem:redness": "раздражители, тонус сосудов, успокаивающие компоненты",
    "problem:pigmentation": "осветляющие механизмы, фотосенсибилизация",
    "problem:texture": "кератолитики, отшелушивание, рельеф",
    "problem:post_acne": "постакне, отшелушивание, осветление следов",
    "problem:ageing": "ретиноиды, пептиды, антиоксиданты, фотозащита",
    "problem:dullness": "отшелушивание, увлажнение, сияние",
    # therapy
    "therapy:topical_retinoid": "дублирование ретиноидов, раздражение, фотосенсибилизация",
    "therapy:adapalene": "дублирование ретиноидов, раздражение, фотосенсибилизация",
    "therapy:tretinoin": "дублирование ретиноидов, раздражение, фотосенсибилизация",
    "therapy:tazarotene": "дублирование ретиноидов, раздражение, фотосенсибилизация",
    "therapy:systemic_isotretinoin": "сухость, фотосенсибилизация, раздражение",
    "therapy:other_retinoid": "дублирование ретиноидов, раздражение, фотосенсибилизация",
    "therapy:acid_therapy": "кислоты, раздражение, фотосенсибилизация",
    "therapy:aha_therapy": "кислоты, раздражение, фотосенсибилизация",
    "therapy:bha_therapy": "кислоты, раздражение, фотосенсибилизация",
    "therapy:pha_therapy": "кислоты, раздражение, фотосенсибилизация",
    "therapy:azelaic_acid_therapy": "раздражение, отшелушивание",
    "therapy:benzoyl_peroxide": "окислители, раздражение, сухость",
    "therapy:antibiotic": "раздражение, сухость",
    # procedures
    "procedure:recent_laser": "раздражение, фотосенсибилизация, заживление",
    "procedure:recent_ipl": "раздражение, фотосенсибилизация, заживление",
    "procedure:recent_microneedling": "раздражение, восстановление барьера",
    "procedure:recent_dermabrasion": "раздражение, восстановление барьера",
    "procedure:recent_rfa": "раздражение, восстановление барьера",
    "procedure:recent_botox": "раздражение в зонах инъекций",
    "procedure:recent_fillers": "раздражение в зонах инъекций",
    "procedure:recent_biorevitalization": "раздражение в зонах инъекций, восстановление",
    "procedure:recent_mesotherapy": "раздражение в зонах инъекций, восстановление",
    "procedure:recent_peeling": "раздражение, фотосенсибилизация, заживление",
    # intolerances
    "intolerance:fragrance_intolerance": "отдушки, ароматические композиции",
    "intolerance:alcohol_intolerance": "этанол и другие спирты",
    "intolerance:essential_oil_intolerance": "эфирные масла",
    "intolerance:retinoid_intolerance": "ретиноиды и их производные",
    "intolerance:acid_intolerance": "AHA, BHA, PHA и другие кислоты",
    "intolerance:niacinamide_intolerance": "ниацинамид",
    # goals
    "goal:barrier": "липиды, церамиды, восстановление барьера",
    "goal:hydration": "влагоудерживающие и смягчающие компоненты",
    "goal:sebum": "себорегуляция, матирование",
    "goal:acne": "себорегуляция, кератинизация, воспаление",
    "goal:brightening": "осветление, выравнивание тона",
    "goal:anti_age": "ретиноиды, пептиды, антиоксиданты",
    "goal:calm": "успокаивающие компоненты, отсутствие раздражителей",
}

_SECTION_DEFAULT_ASPECT = {
    "skin_type": "свойства, значимые для этого типа кожи",
    "problem": "свойства, значимые для этой задачи",
    "therapy": "конфликтующие активы и раздражители",
    "procedure": "раздражители и фотосенсибилизаторы",
    "intolerance": "указанная категория компонентов",
    "goal": "свойства, значимые для этой цели",
}


def parameter_id(section_id: str, option_id: str, modifier: str = "") -> str:
    if section_id == "procedure":
        if not modifier:
            raise ContractError("procedure parameter requires a period")
        return f"procedure:{option_id}@{modifier}"
    return f"{section_id}:{option_id}"


def build_parameter(section_id: str, option_id: str, modifier: str = "") -> Parameter:
    """Build one registry entry from a real questionnaire option."""
    section = q.section(section_id)
    if not section.evaluated:
        raise ContractError(f"section {section_id!r} is not evaluated")
    option = section.option(option_id)
    if option is None:
        raise ContractError(f"unknown option {option_id!r} in section {section_id!r}")

    period_label = ""
    if section_id == "procedure":
        modifier_option = section.modifier(modifier)
        if modifier_option is None:
            raise ContractError(f"unknown period {modifier!r} for {option_id!r}")
        period_label = modifier_option.label

    aspects = ASPECTS.get(f"{section_id}:{option_id}", _SECTION_DEFAULT_ASPECT[section_id])
    fields = {"label": option.label, "aspects": aspects, "period": period_label}
    direction = "risk" if section_id in _RISK_SECTIONS else "benefit"
    return Parameter(
        id=parameter_id(section_id, option_id, modifier),
        label=_LABEL[section_id].format(**fields),
        definition=_DEFINITION[section_id].format(**fields),
        anchors=ANCHORS_RISK if direction == "risk" else ANCHORS_BENEFIT,
        direction=direction,
        section=section_id,
        option_id=option_id,
        modifier=modifier,
        question=_QUESTION[section_id].format(**fields),
        product_axes=tuple(part.strip() for part in aspects.split(",") if part.strip()),
    )


def ingredient_parameter(ingredient: str) -> Parameter:
    """A concrete ingredient the user avoids (structured profile only)."""
    name = str(ingredient or "").strip()
    key = q.slug(name)
    if not key:
        raise ContractError("ingredient name is empty")
    return Parameter(
        id=f"intolerance:ingredient:{key}",
        label=f"Непереносимость: «{name}»",
        definition=(
            f"Отсутствие в составе ингредиента «{name}»; учитываются только "
            "подтверждённые сведения о его наличии."
        ),
        anchors=ANCHORS_RISK,
        direction="risk",
        section="intolerance",
        option_id=f"ingredient:{key}",
        question=f"Можно ли использовать состав при непереносимости «{name}»?",
        product_axes=(name,),
    )


def catalog_parameters() -> tuple[Parameter, ...]:
    """Every parameter the questionnaire can produce (``age`` excluded)."""
    items: list[Parameter] = []
    for section, option in q.iter_evaluated_options():
        if section.id == "skin_type" and option.id == q.UNEVALUATED_SKIN_TYPE:
            continue
        if section.id == "procedure":
            items.extend(
                build_parameter(section.id, option.id, period)
                for period in q.EVALUATED_PERIODS
            )
        else:
            items.append(build_parameter(section.id, option.id))
    return tuple(sorted(items, key=lambda item: item.id))


# Full catalog, not a user's relevant set: used by the API listing and by
# ``seed_registry`` for audit. Relevance comes from ``resolve_parameters``.
PARAMETERS: dict[str, Parameter] = {item.id: item for item in catalog_parameters()}


def validate_registry() -> None:
    """Fail fast if the catalog and the real questionnaire disagree."""
    if len(PARAMETERS) != len(catalog_parameters()):
        raise ValueError("duplicate parameter ids in the catalog")
    for item in PARAMETERS.values():
        if not item.id.startswith(f"{item.section}:"):
            raise ValueError(f"parameter {item.id} is not bound to its section")
        if not item.question:
            raise ValueError(f"parameter {item.id} has no user-facing question")
        if item.section not in q.SECTIONS_BY_ID:
            raise ValueError(f"parameter {item.id} uses unknown section {item.section}")
        if q.section(item.section).option(item.option_id) is None:
            raise ValueError(f"parameter {item.id} uses unknown option {item.option_id}")
    for section, option in q.iter_evaluated_options():
        if section.id == "skin_type" and option.id == q.UNEVALUATED_SKIN_TYPE:
            continue
        modifiers = q.EVALUATED_PERIODS if section.id == "procedure" else ("",)
        for modifier in modifiers:
            key = parameter_id(section.id, option.id, modifier)
            if key not in PARAMETERS:
                raise ValueError(f"questionnaire option {key} has no parameter")



# ---------------------------------------------------------------------------
# Profile payload → evaluated parameters
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedParameters:
    """Parameters a concrete profile needs, with transparency notes."""

    parameters: tuple[Parameter, ...]
    notes: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.parameters)


@dataclass(frozen=True)
class Relevance:
    """Resolved parameter relevance for one user profile."""

    weights: dict
    notes: tuple[str, ...]
    parameters: tuple[Parameter, ...] = ()

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.weights))


@dataclass(frozen=True)
class ProfileSignals:
    """Canonical questionnaire signals (no free text, no raw personal data)."""

    skin_type: str = ""
    problems: tuple[str, ...] = ()
    therapy: tuple[str, ...] = ()
    procedures: tuple[str, ...] = ()
    intolerances: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    age: str = ""
    unresolved: tuple[str, ...] = ()


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _as_items(value: Any) -> list:
    """Normalise list-like and dict-like questionnaire collections.

    Production payloads use lists of dicts, but older/custom profiles may store
    ``{"tretinoin": true}`` — both must be understood instead of iterating keys.
    """
    if value is None:
        return []
    if isinstance(value, Mapping):
        items: list = []
        for key, flag in value.items():
            if isinstance(flag, Mapping):
                item = dict(flag)
                item.setdefault("id", key)
                items.append(item)
            elif isinstance(flag, bool):
                if flag:
                    items.append({"id": key})
            else:
                items.append({"id": key, "period": str(flag)})
        return items
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _entry_id(item: object) -> str:
    if isinstance(item, Mapping):
        return str(item.get("id") or item.get("type") or "").strip()
    return str(item).strip()



def resolve_parameters(profile: Mapping[str, Any] | None) -> ResolvedParameters:
    """Map the real questionnaire answers to the parameters to evaluate.

    Accepts both the production payload (labels in ``concerns``/``allergies``,
    ids in ``structured``) and a structured-only payload. Unknown answers are
    reported, never guessed.
    """
    profile = profile if isinstance(profile, Mapping) else {}
    structured = profile.get("structured")
    structured = structured if isinstance(structured, Mapping) else {}

    found: dict[str, Parameter] = {}
    notes: list[str] = []
    unresolved: list[str] = []

    def add(section_id: str, value: object) -> bool:
        option = q.find_option(section_id, value)
        if option is None:
            return False
        if section_id == "skin_type" and option.id == q.UNEVALUATED_SKIN_TYPE:
            notes.append("Тип кожи указан как «Не знаю» — параметр типа кожи не оценивается.")
            return True
        item = build_parameter(section_id, option.id)
        found.setdefault(item.id, item)
        return True

    for value in (structured.get("skin_type"), profile.get("skin_type")):
        if value in (None, ""):
            continue
        if not add("skin_type", value):
            unresolved.append(f"skin_type:{value}")

    for key in ("concerns", "imperfections", "states"):
        for value in _as_list(structured.get(key)):
            if not add("problem", value):
                unresolved.append(f"concern:{value}")
    for value in _as_list(profile.get("concerns")):
        if not add("problem", value):
            unresolved.append(f"concern:{value}")

    for item in _as_items(structured.get("therapy")) + _as_items(profile.get("therapy")):
        if isinstance(item, Mapping) and item.get("active") is False:
            continue
        value = _entry_id(item)
        if value and not add("therapy", value):
            unresolved.append(f"therapy:{value}")

    for item in _as_items(structured.get("procedures")) + _as_items(profile.get("procedures")):
        if isinstance(item, Mapping):
            procedure_id = str(item.get("id") or "").strip()
            period = q.normalize_period(item.get("period") or "")
        else:
            procedure_id, period = str(item).strip(), ""
        option = q.PROCEDURES.find(procedure_id) if procedure_id else None
        if option is None:
            unresolved.append(f"procedure:{procedure_id or item}")
            continue
        if not period:
            unresolved.append(f"procedure:{option.id} (период не указан)")
            continue
        if period in q.IGNORED_PERIODS:
            notes.append(
                f"Процедура «{option.label}» с периодом более 3 месяцев не создаёт "
                "ограничений в этой версии методики."
            )
            continue
        if period not in q.EVALUATED_PERIODS:
            unresolved.append(f"procedure:{option.id} (неизвестный период {period!r})")
            continue
        parameter = build_parameter("procedure", option.id, period)
        found.setdefault(parameter.id, parameter)

    raw_intolerances = (
        _as_items(structured.get("intolerances"))
        + _as_list(structured.get("allergies"))
        + _as_list(profile.get("allergies"))
    )
    for item in raw_intolerances:
        ingredient = ""
        explicit = False
        if isinstance(item, Mapping):
            ingredient = str(item.get("ingredient_id") or item.get("ingredient") or "").strip()
            explicit = bool(item.get("ingredient_id")) or str(item.get("type") or "") == "specific_ingredient"
            value = ingredient or _entry_id(item)
        else:
            value = str(item).strip()
        if not value:
            continue
        option = q.INTOLERANCES.find(value)
        if option is not None:
            parameter = build_parameter("intolerance", option.id)
            found.setdefault(parameter.id, parameter)
        elif explicit and ingredient:
            parameter = ingredient_parameter(ingredient)
            found.setdefault(parameter.id, parameter)
        else:
            unresolved.append(f"intolerance:{value}")

    for value in _as_list(structured.get("goals")) + _as_list(profile.get("goals")):
        if not add("goal", value):
            unresolved.append(f"goal:{value}")
    if structured.get("skin_goals") or profile.get("skin_goals"):
        notes.append(
            "Поле skin_goals использует устаревшие названия измерений и не "
            "сопоставляется с целями анкеты автоматически."
        )

    unique = sorted(set(unresolved))
    if unique:
        notes.append(
            "Ответы анкеты, которые не удалось сопоставить с параметрами: "
            + ", ".join(unique[:10])
            + (" …" if len(unique) > 10 else "")
        )

    return ResolvedParameters(
        parameters=tuple(sorted(found.values(), key=lambda item: item.id)),
        notes=tuple(notes),
        unresolved=tuple(unique),
    )


def resolve_relevance(profile: Mapping[str, Any] | None) -> Relevance:
    """Parameters relevant to this profile; equal weights (no importance)."""
    resolved = resolve_parameters(profile)
    return Relevance(
        weights={item.id: 1.0 for item in resolved.parameters},
        notes=resolved.notes,
        parameters=resolved.parameters,
    )


def collect_signals(profile: Mapping[str, Any] | None) -> ProfileSignals:
    """Canonical questionnaire signals, used by snapshot fingerprints."""
    resolved = resolve_parameters(profile)
    groups: dict[str, list] = {"skin_type": [], "problem": [], "therapy": [],
                               "procedure": [], "intolerance": [], "goal": []}
    for item in resolved.parameters:
        value = item.option_id
        if item.section == "procedure":
            value = f"{item.option_id}@{item.modifier}"
        groups.setdefault(item.section, []).append(value)

    profile = profile if isinstance(profile, Mapping) else {}
    structured = profile.get("structured")
    structured = structured if isinstance(structured, Mapping) else {}
    raw_age = structured.get("age")
    if not raw_age:
        raw_age = profile.get("age")
    age = q.AGES.find(raw_age)
    return ProfileSignals(
        skin_type=(groups["skin_type"][0] if groups["skin_type"] else ""),
        problems=tuple(sorted(groups["problem"])),
        therapy=tuple(sorted(groups["therapy"])),
        procedures=tuple(sorted(groups["procedure"])),
        intolerances=tuple(sorted(groups["intolerance"])),
        goals=tuple(sorted(groups["goal"])),
        age=age.id if age else "",
        unresolved=resolved.unresolved,
    )

