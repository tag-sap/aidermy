"""Parameter registry and questionnaire → parameter relevance.

The registry is the single place where the meaning of the 0..100 scale is
defined for each parameter. Relevance comes ONLY from the user's questionnaire
answers (no invented importance): a parameter is evaluated only when at least
one selected answer makes it relevant. Pure module: no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import Parameter

PARAMETERS: dict[str, Parameter] = {
    "hydration": Parameter(
        id="hydration",
        label="Увлажнённость",
        definition=(
            "Соответствие потребности кожи в увлажнении: наличие подтверждённых "
            "влагоудерживающих и смягчающих компонентов и отсутствие высушивающих "
            "факторов без компенсации."
        ),
        anchors=(
            (0, "Подтверждённые высушивающие факторы без компенсирующих компонентов"),
            (50, "Нет подтверждённых данных ни за, ни против"),
            (100, "Подтверждённые влагоудерживающие и смягчающие компоненты в значимых позициях"),
        ),
        direction="benefit",
    ),
    "barrier": Parameter(
        id="barrier",
        label="Поддержка барьера",
        definition=(
            "Соответствие задаче поддержки кожного барьера: липиды, церамиды, "
            "компоненты восстановления и отсутствие агрессивных ПАВ."
        ),
        anchors=(
            (0, "Агрессивные ПАВ/растворители в верхних позициях без компенсации"),
            (50, "Нет подтверждённых данных"),
            (100, "Подтверждённые барьерные компоненты в значимых позициях"),
        ),
        direction="benefit",
    ),
    "irritation": Parameter(
        id="irritation",
        label="Риск раздражения",
        definition=(
            "Соответствие по риску раздражения: чем выше оценка, тем меньше "
            "подтверждённых раздражающих факторов в составе."
        ),
        anchors=(
            (0, "Подтверждённые раздражители в верхних позициях без смягчения"),
            (50, "Данных недостаточно для вывода"),
            (100, "Подтверждённых раздражающих факторов в значимых позициях не найдено"),
        ),
        direction="risk",
    ),
    "sensitization": Parameter(
        id="sensitization",
        label="Риск сенсибилизации",
        definition=(
            "Соответствие по риску аллергической сенсибилизации: чем выше оценка, "
            "тем меньше подтверждённых аллергенов и сенсибилизаторов."
        ),
        anchors=(
            (0, "Подтверждённые сильные аллергены в значимых позициях"),
            (50, "Данных недостаточно для вывода"),
            (100, "Подтверждённых аллергенов/сенсибилизаторов в значимых позициях не найдено"),
        ),
        direction="risk",
    ),
    "sebum": Parameter(
        id="sebum",
        label="Контроль жирности",
        definition=(
            "Соответствие задаче снижения жирности и блеска: подтверждённые "
            "себорегулирующие компоненты против жирных/окклюзивных."
        ),
        anchors=(
            (0, "Подтверждённые жирные/окклюзивные компоненты в верхних позициях"),
            (50, "Нет подтверждённых данных"),
            (100, "Подтверждённые себорегулирующие компоненты в значимых позициях"),
        ),
        direction="benefit",
    ),
    "comedogenicity": Parameter(
        id="comedogenicity",
        label="Риск закупорки пор",
        definition=(
            "Соответствие по риску закупорки пор: чем выше оценка, тем меньше "
            "подтверждённых комедогенных компонентов."
        ),
        anchors=(
            (0, "Подтверждённые комедогенные компоненты в верхних позициях"),
            (50, "Данных недостаточно для вывода"),
            (100, "Подтверждённых комедогенных компонентов в значимых позициях не найдено"),
        ),
        direction="risk",
    ),
    "pigmentation": Parameter(
        id="pigmentation",
        label="Работа с пигментацией",
        definition=(
            "Соответствие задаче выравнивания тона: подтверждённые компоненты, "
            "влияющие на пигментацию, и отсутствие фотосенсибилизаторов."
        ),
        anchors=(
            (0, "Подтверждённых компонентов нет, при этом есть фотосенсибилизаторы"),
            (50, "Нет подтверждённых данных"),
            (100, "Подтверждённые компоненты без фотосенсибилизаторов"),
        ),
        direction="benefit",
    ),
    "texture": Parameter(
        id="texture",
        label="Рельеф и кератоз",
        definition=(
            "Соответствие задаче выравнивания рельефа: подтверждённые "
            "кератолитические/отшелушивающие механизмы."
        ),
        anchors=(
            (0, "Подтверждённых механизмов нет; возможен обратный эффект"),
            (50, "Нет подтверждённых данных"),
            (100, "Подтверждённые кератолитические механизмы в значимых позициях"),
        ),
        direction="benefit",
    ),
    "ageing": Parameter(
        id="ageing",
        label="Возрастные изменения",
        definition=(
            "Соответствие задаче работы с возрастными изменениями: подтверждённые "
            "компоненты (ретиноиды, пептиды, антиоксиданты и др.)."
        ),
        anchors=(
            (0, "Подтверждённых компонентов нет"),
            (50, "Нет подтверждённых данных"),
            (100, "Подтверждённые компоненты с описанным механизмом"),
        ),
        direction="benefit",
    ),
    "therapy_safety": Parameter(
        id="therapy_safety",
        label="Совместимость с терапией",
        definition=(
            "Безопасное сочетание с указанной активной терапией (ретиноиды, кислоты, "
            "бензоилпероксид, изотретиноин): отсутствие дублирующих/конфликтующих "
            "активов и усиливающих раздражение факторов."
        ),
        anchors=(
            (0, "Подтверждённый конфликт с активной терапией"),
            (50, "Данных недостаточно для вывода"),
            (100, "Подтверждённых конфликтов нет"),
        ),
        direction="risk",
    ),
    "procedure_safety": Parameter(
        id="procedure_safety",
        label="Совместимость с процедурами",
        definition=(
            "Подходит ли состав после указанной процедуры (лазер, пилинг, микронидлинг): "
            "отсутствие раздражающих и фотосенсибилизирующих факторов."
        ),
        anchors=(
            (0, "Подтверждённые раздражающие/фотосенсибилизирующие факторы"),
            (50, "Данных недостаточно для вывода"),
            (100, "Подтверждённых факторов риска после процедуры нет"),
        ),
        direction="risk",
    ),
    "fragrance_allergen": Parameter(
        id="fragrance_allergen",
        label="Ароматизаторы и аллергены",
        definition=(
            "Соответствие по наличию подтверждённых ароматизаторов и аллергенов: "
            "чем выше оценка, тем меньше таких компонентов."
        ),
        anchors=(
            (0, "Подтверждённые ароматизаторы/аллергены в верхних позициях"),
            (50, "Данных недостаточно для вывода"),
            (100, "Подтверждённых ароматизаторов/аллергенов не найдено"),
        ),
        direction="risk",
    ),
}

# Relevance of a parameter given a selected questionnaire answer.
# 1.0 = the answer directly states this need; lower = secondary influence.
# Values are a design decision of the questionnaire mapping, NOT calibrated weights.
CATEGORY_RELEVANCE: dict[str, dict[str, float]] = {
    "dryness": {"hydration": 1.0, "barrier": 0.7},
    "barrier": {"barrier": 1.0},
    "sensitivity": {"irritation": 1.0, "sensitization": 0.8},
    "redness": {"irritation": 1.0, "sensitization": 0.5},
    "rosacea": {"irritation": 1.0, "sensitization": 0.6},
    "acne": {"comedogenicity": 1.0, "sebum": 0.8, "irritation": 0.6},
    "sebum_pores": {"sebum": 1.0, "comedogenicity": 0.6},
    "pigmentation": {"pigmentation": 1.0},
    "photosensitivity": {"pigmentation": 0.8, "sensitization": 0.4},
    "post_acne": {"pigmentation": 0.7, "texture": 0.6, "comedogenicity": 0.5},
    "texture": {"texture": 1.0, "comedogenicity": 0.4},
    "ageing": {"ageing": 1.0},
    "dullness": {"pigmentation": 0.6, "texture": 0.4},
    "diagnosed": {"sensitization": 0.5},
    "therapy": {"therapy_safety": 1.0},
    "procedure": {"procedure_safety": 1.0},
}

ID_RELEVANCE: dict[str, dict[str, float]] = {
    # skin type
    "dry": {"hydration": 1.0, "barrier": 0.6},
    "dehydrated": {"hydration": 1.0},
    "oily": {"sebum": 1.0},
    "combination": {"sebum": 0.8},
    "sensitive": {"irritation": 1.0, "sensitization": 0.8, "barrier": 0.5},
    # dryness details
    "cracking": {"barrier": 1.0},
    "dehydration_lines": {"hydration": 1.0},
    "skin_tightness": {"hydration": 0.8, "barrier": 0.5},
    "lipid_deficiency": {"barrier": 1.0, "hydration": 0.5},
    # texture details
    "flaking": {"barrier": 0.8, "texture": 0.5},
    "scaling": {"barrier": 0.8, "texture": 0.4},
    "keratosis_pilaris": {"texture": 1.0},
    "follicular_hyperkeratosis": {"texture": 1.0},
    "hyperkeratosis": {"texture": 1.0},
    # acne details
    "inflammatory_acne": {"irritation": 0.9, "comedogenicity": 0.8},
    "papules": {"irritation": 0.8, "comedogenicity": 0.7},
    "pustules": {"irritation": 0.9, "comedogenicity": 0.7},
    "deep_inflammation": {"irritation": 1.0, "comedogenicity": 0.6},
    "closed_comedones": {"comedogenicity": 1.0, "sebum": 0.7},
    "open_comedones": {"comedogenicity": 1.0, "sebum": 0.7},
    "blackheads": {"comedogenicity": 0.9, "sebum": 0.7},
    "clogged_pores": {"comedogenicity": 0.9, "sebum": 0.6},
    # pigmentation details
    "melasma": {"pigmentation": 1.0},
    "post_acne_pigmentation": {"pigmentation": 0.9},
    "sun_pigmentation": {"pigmentation": 0.9},
    # therapy (only when active)
    "topical_retinoid": {"therapy_safety": 1.0, "irritation": 0.4},
    "adapalene": {"therapy_safety": 1.0, "irritation": 0.4},
    "tretinoin": {"therapy_safety": 1.0, "irritation": 0.5},
    "tazarotene": {"therapy_safety": 1.0, "irritation": 0.5},
    "systemic_isotretinoin": {"therapy_safety": 1.0, "barrier": 0.6, "hydration": 0.6},
    "benzoyl_peroxide": {"therapy_safety": 1.0, "irritation": 0.4},
    "aha_therapy": {"therapy_safety": 1.0, "irritation": 0.4},
    "bha_therapy": {"therapy_safety": 1.0, "irritation": 0.4},
    "pha_therapy": {"therapy_safety": 1.0},
    "azelaic_acid_therapy": {"therapy_safety": 1.0},
    # procedures (only when recent)
    "recent_laser": {"procedure_safety": 1.0},
    "recent_ipl": {"procedure_safety": 1.0},
    "recent_microneedling": {"procedure_safety": 1.0},
    "recent_dermabrasion": {"procedure_safety": 1.0},
    "recent_rfa": {"procedure_safety": 1.0},
    "recent_invasive_procedure": {"procedure_safety": 1.0},
}


RECENT_PERIODS = {"<7 days", "7-14 days", "14-30 days"}


@dataclass(frozen=True)
class ProfileSignals:
    """Questionnaire signals extracted from a profile payload."""

    ids: tuple[str, ...]
    active_therapy: tuple[str, ...]
    recent_procedures: tuple[str, ...]
    allergies: tuple[str, ...]
    intolerances: tuple[str, ...]


@dataclass(frozen=True)
class Relevance:
    """Resolved parameter relevance for one user profile."""

    weights: dict
    notes: tuple[str, ...]


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def collect_signals(profile: Mapping[str, Any] | None) -> ProfileSignals:
    """Extract questionnaire IDs and risk flags from a profile payload.

    Supports both the flat production payload (skin_type/concerns/allergies)
    and the structured one (therapy/procedures/intolerances).
    """
    profile = profile or {}
    structured = profile.get("structured")
    structured = structured if isinstance(structured, Mapping) else {}

    ids: set[str] = set()
    for key in ("concerns", "imperfections", "states", "goals"):
        ids.update(_as_list(structured.get(key)))
    ids.update(_as_list(profile.get("concerns")))

    skin_type = structured.get("skin_type") or profile.get("skin_type")
    if skin_type:
        ids.add(str(skin_type).strip())

    active_therapy: list[str] = []
    for item in structured.get("therapy") or []:
        if isinstance(item, Mapping):
            therapy_id = str(item.get("id") or "").strip()
            if therapy_id and bool(item.get("active", True)):
                active_therapy.append(therapy_id)
        elif isinstance(item, str) and item.strip():
            active_therapy.append(item.strip())

    recent_procedures: list[str] = []
    for item in structured.get("procedures") or []:
        if isinstance(item, Mapping):
            procedure_id = str(item.get("id") or "").strip()
            period = str(item.get("period") or "").strip()
            if procedure_id and (period in RECENT_PERIODS or not period):
                recent_procedures.append(procedure_id)

    allergies = list(dict.fromkeys(
        _as_list(profile.get("allergies")) + _as_list(structured.get("allergies"))
    ))
    intolerances = list(dict.fromkeys(_as_list(structured.get("intolerances"))))

    return ProfileSignals(
        ids=tuple(sorted(ids)),
        active_therapy=tuple(sorted(set(active_therapy))),
        recent_procedures=tuple(sorted(set(recent_procedures))),
        allergies=tuple(allergies),
        intolerances=tuple(intolerances),
    )


def _merge(weights: dict, extra: Mapping[str, float]) -> None:
    for parameter_id, value in (extra or {}).items():
        weights[parameter_id] = max(weights.get(parameter_id, 0.0), float(value))


def resolve_relevance(profile: Mapping[str, Any] | None) -> Relevance:
    """Map questionnaire answers to parameter relevance (max, never sum).

    Using max instead of sum prevents "selecting more options" from inflating
    a parameter's weight. Unknown answers are ignored and reported in notes.
    """
    signals = collect_signals(profile)
    weights: dict[str, float] = {}
    notes: list[str] = []
    unknown: list[str] = []

    for qid in signals.ids:
        matched = False
        if qid in ID_RELEVANCE:
            _merge(weights, ID_RELEVANCE[qid])
            matched = True
        if qid in CATEGORY_RELEVANCE:
            _merge(weights, CATEGORY_RELEVANCE[qid])
            matched = True
        if not matched:
            unknown.append(qid)

    for therapy_id in signals.active_therapy:
        _merge(weights, ID_RELEVANCE.get(therapy_id, {"therapy_safety": 1.0}))

    for procedure_id in signals.recent_procedures:
        _merge(weights, ID_RELEVANCE.get(procedure_id, {"procedure_safety": 1.0}))

    if signals.allergies:
        _merge(weights, {"fragrance_allergen": 0.8})
        notes.append(
            "Указаны аллергии без привязки к конкретным ингредиентам: параметр "
            "«Ароматизаторы и аллергены» учитывается по общему признаку."
        )
    if signals.intolerances:
        _merge(weights, {"irritation": 0.5})
        notes.append(
            "Указана непереносимость компонентов. Персональный конфликт по конкретному "
            "ингредиенту в текущей версии методики не рассчитывается и требует проверки."
        )
    if unknown:
        notes.append(
            "Часть ответов анкеты не влияет на оценку в этой версии методики: "
            + ", ".join(sorted(unknown)[:10])
            + (" …" if len(unknown) > 10 else "")
        )

    valid = {pid: w for pid, w in weights.items() if pid in PARAMETERS and w > 0}
    return Relevance(weights=valid, notes=tuple(notes))


def validate_registry() -> None:
    """Fail fast if the mapping references an unknown parameter."""
    for table_name, table in (("ID_RELEVANCE", ID_RELEVANCE), ("CATEGORY_RELEVANCE", CATEGORY_RELEVANCE)):
        for key, mapping in table.items():
            for parameter_id in mapping:
                if parameter_id not in PARAMETERS:
                    raise ValueError(f"{table_name}[{key}] references unknown parameter {parameter_id}")
