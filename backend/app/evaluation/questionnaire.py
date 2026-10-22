"""Real Aidermy questionnaire catalog — the source of evaluated parameters.

Every id below is copied from the production questionnaire that users actually
fill in (``figma-make-preview/src/data.ts``). Nothing here is invented:

  * ``tests/test_evaluation_questionnaire.py`` parses that TypeScript file and
    fails if the catalog drifts from it (new/renamed/removed options), so the
    evaluation layer cannot silently score a questionnaire that no longer exists;
  * labels are used to resolve the flat production payload, which sends human
    labels (``concerns``/``allergies``) instead of ids.

Seven questionnaire sections
----------------------------
1. ``skin_type``  — single choice; ``unknown`` is NOT evaluated (no information).
2. ``age``        — collected but NOT evaluated: age alone is not a property of a
                    product, so it stays context and never enters shared product
                    knowledge.
3. ``problem``    — concern cards (``acne_general``, ``dryness``, ...); branch
                    answers (``papules``, ``flaking``, ...) are refinements shown to
                    the user, not separate evaluated units.
4. ``therapy``    — active treatment; the concrete substance wins over the group
                    (``tretinoin`` instead of ``topical_retinoid``).
5. ``procedure``  — procedure + period after it; both are part of the identity
                    (``procedure:recent_laser@<7``). ``>3m`` creates no restriction
                    in this method version.
6. ``intolerance``— ingredient group the user avoids; a specific ingredient id from
                    a structured profile becomes its own parameter.
7. ``goal``       — care goal (``hydration``, ``barrier``, ...).

Pure data module: no I/O, no network.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Version of the questionnaire the ids were taken from. Bump it when the
# production questionnaire changes; stale evaluations keep their own version.
QUESTIONNAIRE_VERSION = "quiz-1.0.0"
QUESTIONNAIRE_SOURCE = "figma-make-preview/src/data.ts"

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_SPACES = re.compile(r"\s+")
_SLUG = re.compile(r"[^0-9a-zа-яё]+")


def normalize(value: object) -> str:
    """Case/space/dash-insensitive form used to match ids and labels."""
    text = str(value or "").translate(_DASHES).casefold().replace("ё", "е")
    return _SPACES.sub(" ", text).strip()


def slug(value: object) -> str:
    """Stable key fragment for a free-form ingredient name."""
    cleaned = _SLUG.sub("_", normalize(value)).strip("_")
    return cleaned[:60]


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    short_label: str = ""
    parent: str = ""      # group option this one refines (retinoids, acids)

    def matches(self, value: object) -> bool:
        candidate = normalize(value)
        return candidate in {
            normalize(self.id),
            normalize(self.label),
            normalize(self.short_label),
        }


@dataclass(frozen=True)
class Section:
    id: str
    label: str
    field: str
    evaluated: bool = True
    options: tuple[Option, ...] = ()
    modifiers: tuple[Option, ...] = ()      # e.g. procedure periods
    modifier_label: str = ""

    def option(self, option_id: str) -> Option | None:
        for item in self.options:
            if item.id == option_id:
                return item
        return None

    def modifier(self, modifier_id: str) -> Option | None:
        for item in self.modifiers:
            if item.id == modifier_id:
                return item
        return None

    def find(self, value: object) -> Option | None:
        """Resolve an id, full label or short label to one option."""
        if value is None or str(value).strip() == "":
            return None
        for item in self.options:
            if item.matches(value):
                return item
        return None


# --------------------------------------------------------------------------
# 1. Skin type (data.ts: SKIN_TYPE_OPTIONS)
# --------------------------------------------------------------------------
SKIN_TYPES = Section(
    id="skin_type",
    label="Тип кожи",
    field="skin_type",
    options=(
        Option("normal", "Нормальная"),
        Option("dry", "Сухая"),
        Option("oily", "Жирная"),
        Option("combination", "Комбинированная"),
        Option("sensitive", "Чувствительная"),
        Option("unknown", "Не знаю"),
    ),
)

# The only skin-type answer that produces no parameter: it carries no information.
UNEVALUATED_SKIN_TYPE = "unknown"

# --------------------------------------------------------------------------
# 2. Age (data.ts: AGE_OPTIONS) — context only, never a scored parameter
# --------------------------------------------------------------------------
AGES = Section(
    id="age",
    label="Возраст",
    field="age",
    evaluated=False,
    options=(
        Option("under_25", "До 25"),
        Option("25_35", "25–35"),
        Option("35_45", "35–45"),
        Option("45_plus", "45+"),
    ),
)

# --------------------------------------------------------------------------
# 3. Problems (data.ts: CONCERN_CARDS) — branch answers are refinements
# --------------------------------------------------------------------------
PROBLEMS = Section(
    id="problem",
    label="Проблема",
    field="concerns",
    options=(
        Option("acne_general", "Высыпания", "Высыпания"),
        Option("sebum_pores", "Поры и жирность", "Поры и жирность"),
        Option("dryness", "Сухость / обезвоженность", "Сухость"),
        Option("sensitivity", "Чувствительность", "Чувствительность"),
        Option("redness", "Покраснения", "Покраснения"),
        Option("pigmentation", "Пигментация", "Пигментация"),
        Option("texture", "Неровный рельеф", "Рельеф"),
        Option("post_acne", "Следы после акне", "Следы после акне"),
        Option("ageing", "Возрастные изменения", "Морщины"),
        Option("dullness", "Тусклый тон", "Тусклость"),
    ),
)

# --------------------------------------------------------------------------
# 4. Therapy (data.ts: THERAPY_OPTIONS + RETINOID_OPTIONS + ACID_OPTIONS)
# --------------------------------------------------------------------------
THERAPIES = Section(
    id="therapy",
    label="Лечение",
    field="therapy",
    options=(
        Option("topical_retinoid", "Ретиноиды"),
        Option("acid_therapy", "Кислоты"),
        Option("azelaic_acid_therapy", "Азелаиновая кислота"),
        Option("benzoyl_peroxide", "Бензоилпероксид"),
        Option("antibiotic", "Антибиотики"),
        Option("adapalene", "Адапален", parent="topical_retinoid"),
        Option("tretinoin", "Третиноин", parent="topical_retinoid"),
        Option("tazarotene", "Тазаротен", parent="topical_retinoid"),
        Option("systemic_isotretinoin", "Изотретиноин внутрь", parent="topical_retinoid"),
        Option("other_retinoid", "Другой / не знаю", parent="topical_retinoid"),
        Option("aha_therapy", "AHA", parent="acid_therapy"),
        Option("bha_therapy", "BHA", parent="acid_therapy"),
        Option("pha_therapy", "PHA", parent="acid_therapy"),
    ),
)

# --------------------------------------------------------------------------
# 5. Procedures (data.ts: PROCEDURE_OPTIONS + PROCEDURE_PERIODS)
# --------------------------------------------------------------------------
PROCEDURES = Section(
    id="procedure",
    label="Процедура",
    field="procedures",
    options=(
        Option("recent_laser", "Лазер"),
        Option("recent_ipl", "IPL"),
        Option("recent_microneedling", "Микронидлинг"),
        Option("recent_dermabrasion", "Дермабразия"),
        Option("recent_rfa", "RF / RFA"),
        Option("recent_botox", "Ботокс"),
        Option("recent_fillers", "Филлеры"),
        Option("recent_biorevitalization", "Биоревитализация"),
        Option("recent_mesotherapy", "Мезотерапия"),
        Option("recent_peeling", "Пилинг"),
    ),
    modifiers=(
        Option("<7", "Последние 7 дней"),
        Option("7-14", "7–14 дней"),
        Option("14-30", "14–30 дней"),
        Option("1-3m", "1–3 месяца"),
        Option(">3m", "Более 3 месяцев"),
    ),
    modifier_label="период",
)

# Periods that create a restriction in this method version. ``>3m`` is ignored
# (documented methodological decision, not a validated medical rule).
EVALUATED_PERIODS = ("<7", "7-14", "14-30", "1-3m")
IGNORED_PERIODS = (">3m",)
PERIOD_ALIASES = {
    "<7 days": "<7",
    "7-14 days": "7-14",
    "14-30 days": "14-30",
    "1-3 months": "1-3m",
    "3+ months": ">3m",
}



# --------------------------------------------------------------------------
# 6. Intolerances (data.ts: INTOLERANCE_OPTIONS)
# --------------------------------------------------------------------------
INTOLERANCES = Section(
    id="intolerance",
    label="Непереносимость",
    field="allergies",
    options=(
        Option("fragrance_intolerance", "Отдушки"),
        Option("alcohol_intolerance", "Спирт"),
        Option("essential_oil_intolerance", "Эфирные масла"),
        Option("retinoid_intolerance", "Ретиноиды"),
        Option("acid_intolerance", "Кислоты"),
        Option("niacinamide_intolerance", "Ниацинамид"),
    ),
)

# --------------------------------------------------------------------------
# 7. Goals (data.ts: GOALS_OPTIONS)
# --------------------------------------------------------------------------
GOALS = Section(
    id="goal",
    label="Цель",
    field="goals",
    options=(
        Option("barrier", "Восстановить барьер кожи"),
        Option("hydration", "Увлажнить кожу"),
        Option("sebum", "Убрать жирный блеск"),
        Option("acne", "Убрать акне"),
        Option("brightening", "Выровнять тон"),
        Option("anti_age", "Разгладить морщины"),
        Option("calm", "Успокоить кожу"),
    ),
)

SECTIONS: tuple[Section, ...] = (
    SKIN_TYPES,
    AGES,
    PROBLEMS,
    THERAPIES,
    PROCEDURES,
    INTOLERANCES,
    GOALS,
)

SECTIONS_BY_ID = {item.id: item for item in SECTIONS}


def section(section_id: str) -> Section:
    try:
        return SECTIONS_BY_ID[section_id]
    except KeyError as exc:
        raise KeyError(f"unknown questionnaire section: {section_id}") from exc


def find_option(section_id: str, value: object) -> Option | None:
    """Resolve a raw answer (id, label or short label) inside one section."""
    return section(section_id).find(value)


def normalize_period(value: object) -> str:
    """Map production and legacy period spellings to one canonical id."""
    text = normalize(value)
    for suffix in ("дней", "дня", "день", "days", "day"):
        text = text.replace(suffix, "")
    text = text.strip()
    if text in PERIOD_ALIASES:
        return PERIOD_ALIASES[text]
    if text in {item.id for item in PROCEDURES.modifiers}:
        return text
    return text


def section_options(section_id: str) -> tuple[Option, ...]:
    return section(section_id).options


def iter_evaluated_options() -> Iterable[tuple[Section, Option]]:
    for item in SECTIONS:
        if not item.evaluated:
            continue
        for option in item.options:
            yield item, option
