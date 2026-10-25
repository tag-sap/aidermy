"""Independent assessment of the product's primary function.

This module answers a different question from personal compatibility:

    "Does the confirmed formula support the product's own purpose?"

It never uses the user's profile, questionnaire answers or the mean of personal
parameters. The purpose is taken from the trusted Aidermy catalogue
classification; the support is checked against the confirmed INCI. A marketing
description alone is not enough to produce a score.

The result is deliberately conservative: a known category with a confirmed
formula can be assessed, but an unknown category or an unconfirmed/absent INCI
returns ``None`` instead of an invented number. The number is a **formula
support** score, not a clinical efficacy score: the deterministic input has no
concentration or finished-product evidence, so the maximum is 90 and a score of
100 is never produced here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..catalog_taxonomy import classify_product
from ..category_knowledge import get_category_knowledge
from .inci import split_inci

PRIMARY_FUNCTION_VERSION = "2.0.0"
PRIMARY_SCORE_KIND = "formula_support"
PRIMARY_SCORE_LABEL = "Соответствие состава"
PRIMARY_SCORE_NOTE = (
    "Оценка отражает наличие функциональных групп в подтверждённом INCI. "
    "Она не подтверждает концентрацию, эффективность готового продукта или "
    "клинический результат."
)


@dataclass(frozen=True)
class FunctionSpec:
    key: str
    label: str
    purpose: str
    expected_groups: tuple[str, ...]

# A product type is mapped to one product-level function. ``expected_groups``
# describes the functional ingredient classes that can support that function;
# they are NOT questionnaire parameters and never enter personal compatibility.
_SPECS: dict[str, FunctionSpec] = {
    "face:cleansing": FunctionSpec(
        "cleansing", "Очищение", "Очистить кожу и снять загрязнения.",
        ("surfactants",),
    ),
    "face:acne": FunctionSpec(
        "anti_acne", "Антиакне-уход", "Уменьшить проявления акне и воспалений.",
        ("acne_actives", "soothing", "acids", "retinoids"),
    ),
    "face:brightening": FunctionSpec(
        "brightening", "Выравнивание тона", "Поддержать выравнивание тона и снизить видимую пигментацию.",
        ("brightening_actives", "antioxidants", "acids"),
    ),
    "face:barrier": FunctionSpec(
        "barrier", "Восстановление барьера", "Поддержать барьер и снизить потерю влаги.",
        ("ceramides", "soothing", "occlusives", "humectants"),
    ),
    "face:hydration": FunctionSpec(
        "hydration", "Увлажнение", "Увлажнить и смягчить кожу.",
        ("humectants", "emollients"),
    ),
    "face:toning": FunctionSpec(
        "toning", "Тонизирование", "Подготовить кожу после очищения и освежить её.",
        ("humectants", "soothing"),
    ),
    "face:serums": FunctionSpec(
        "treatment", "Уход за кожей", "Доставить целевые компоненты в зависимости от состава.",
        ("actives", "humectants"),
    ),
    "face:creams": FunctionSpec(
        "moisturizing", "Увлажнение", "Увлажнить и смягчить кожу.",
        ("humectants", "emollients", "occlusives", "ceramides"),
    ),
    "face:moisturizing": FunctionSpec(
        "moisturizing", "Увлажнение", "Увлажнить и напитать кожу.",
        ("humectants", "emollients", "occlusives", "ceramides"),
    ),
    "face:scrubs": FunctionSpec(
        "exfoliation", "Отшелушивание", "Удалить ороговевшие клетки и обновить поверхность кожи.",
        ("acids", "abrasives", "enzymes"),
    ),
    "face:masks": FunctionSpec(
        "treatment", "Уход за кожей", "Временно поддержать кожу в зависимости от типа маски.",
        ("humectants", "soothing", "clays", "acids"),
    ),
    "face:patches": FunctionSpec(
        "local_care", "Локальный уход", "Поддержать кожу в ограниченной зоне нанесения.",
        ("humectants", "soothing"),
    ),
    "face:pads": FunctionSpec(
        "toning", "Тонизирование", "Протереть кожу и нанести компоненты пропитки.",
        ("humectants", "soothing", "acids"),
    ),
    "face:eyes": FunctionSpec(
        "eye_care", "Уход за областью вокруг глаз", "Увлажнить и поддержать тонкую кожу вокруг глаз.",
        ("humectants", "soothing", "peptides"),
    ),
    "face:lips": FunctionSpec(
        "lip_care", "Уход за губами", "Увлажнить и смягчить кожу губ.",
        ("humectants", "emollients", "occlusives"),
    ),
    "face:special": FunctionSpec(
        "targeted", "Целевой уход", "Воздействовать на конкретную задачу в пределах состава.",
        ("actives", "acids", "retinoids", "antioxidants"),
    ),
    "face:antiage": FunctionSpec(
        "anti_age", "Антивозрастной уход", "Поддержать кожу и снизить видимые признаки старения.",
        ("retinoids", "peptides", "antioxidants"),
    ),
    "sun_protection:spf": FunctionSpec(
        "sun_protection", "Защита от солнца", "Защитить кожу от ультрафиолетового излучения.",
        ("uv_filters",),
    ),
    "body:basic": FunctionSpec(
        "body_care", "Уход за телом", "Увлажнить и смягчить кожу тела.",
        ("humectants", "emollients", "occlusives"),
    ),
    "hair:basic": FunctionSpec(
        "hair_care", "Уход за волосами", "Очистить или поддержать волосы в зависимости от формулы.",
        ("surfactants", "emollients"),
    ),
    "makeup:foundation": FunctionSpec(
        "coverage", "Выравнивание тона", "Выровнять тон кожи и создать покрытие.",
        ("pigments",),
    ),
    "makeup:concealers": FunctionSpec(
        "coverage", "Маскировка", "Замаскировать несовершенства и выровнять тон.",
        ("pigments",),
    ),
    "makeup:powders": FunctionSpec(
        "matting", "Матирование", "Снизить блеск и зафиксировать макияж.",
        ("absorbents", "pigments"),
    ),
    "makeup:blush": FunctionSpec(
        "colour", "Придание цвета", "Добавить цвет щекам.",
        ("pigments",),
    ),
    "makeup:mascara": FunctionSpec(
        "eye_makeup", "Макияж ресниц", "Придать ресницам объём или длину.",
        ("pigments", "waxes"),
    ),
    "makeup:lipstick": FunctionSpec(
        "lip_colour", "Цвет губ", "Придать губам цвет.",
        ("pigments", "waxes"),
    ),
    "makeup:eyes": FunctionSpec(
        "eye_makeup", "Макияж глаз", "Создать декоративное покрытие в области глаз.",
        ("pigments",),
    ),
}

# A deliberately small, auditable lexicon. It recognises functional ingredient
# families, not brands or marketing claims. Unknown ingredients simply do not
# count; they are never treated as evidence of absence.
_MARKERS: dict[str, tuple[str, ...]] = {
    "humectants": (
        "glycerin", "glycerine", "sodium hyaluronate", "hyaluronic acid",
        "hydroxyethyl urea", "urea", "panthenol", "propylene glycol",
        "butylene glycol", "sorbitol", "betaine", "trehalose", "aloe",
    ),
    "emollients": (
        "butyrospermum parkii", "shea butter", "caprylic/capric triglyceride",
        "cetearyl alcohol", "cetyl alcohol", "stearyl alcohol", "squalane",
        "isopropyl myristate", "jojoba", "dimethicone", "cyclopentasiloxane",
        "sunflower oil", "olive oil", "sweet almond oil", "glycerides",
    ),
    "occlusives": (
        "petrolatum", "mineral oil", "beeswax", "candelilla", "paraffin",
        "lanolin", "shea butter", "butyrospermum parkii", "dimethicone",
    ),
    "ceramides": ("ceramide",),
    "surfactants": (
        "sodium cocoyl", "cocamidopropyl", "sodium lauryl", "sodium laureth",
        "coco-glucoside", "decyl glucoside", "polysorbate", "peg-",
        "potassium cocoate", "sodium cocoate", "soap", "saponin",
    ),
    "uv_filters": (
        "zinc oxide", "titanium dioxide", "avobenzone", "octocrylene",
        "octinoxate", "homosalate", "oxybenzone", "bemotrizinol",
        "bis-ethylhexyloxyphenol methoxyphenyl triazine", "ethylhexyl triazone",
        "diethylamino hydroxybenzoyl hexyl benzoate", "ensulizole",
        "methylene bis-benzotriazolyl tetramethylbutylphenol",
    ),
    "acids": (
        "glycolic acid", "lactic acid", "salicylic acid", "mandelic acid",
        "azelaic acid", "citric acid", "phytic acid", "gluconolactone",
        "lactobionic acid", "malic acid", "tartaric acid",
    ),
    "retinoids": (
        "retinol", "retinal", "retinyl", "adapalene", "tretinoin",
        "tazarotene", "hydroxypinacolone retinoate",
    ),
    "peptides": ("peptide", "palmitoyl", "matrixyl", "tripeptide"),
    "antioxidants": (
        "tocopherol", "tocopheryl acetate", "ascorbic acid", "ascorbyl",
        "ferulic acid", "resveratrol", "green tea", "camellia sinensis",
    ),
    "soothing": (
        "panthenol", "allantoin", "bisabolol", "centella", "madecassoside",
        "aloe", "licorice", "glycyrrhiza",
    ),
    "acne_actives": (
        "salicylic acid", "niacinamide", "nicotinamide", "zinc pca",
        "zinc gluconate", "sulfur", "benzoyl peroxide", "azelaic acid",
        "adapalene", "tretinoin", "retinal", "retinol", "tea tree",
        "melaleuca", "capryloyl salicylic acid",
    ),
    "brightening_actives": (
        "niacinamide", "nicotinamide", "ascorbic acid", "ascorbyl",
        "arbutin", "tranexamic acid", "kojic acid", "licorice",
        "glycyrrhiza", "azelaic acid", "resorcinol", "glutathione",
    ),
    "clays": ("kaolin", "bentonite", "montmorillonite", "clay"),
    "abrasives": (
        "silica", "jojoba esters", "sugar", "salt", "walnut", "apricot",
        "cellulose",
    ),
    "enzymes": ("papain", "bromelain", "protease", "enzyme"),
    "pigments": (
        "iron oxide", "mica", "ci 77891", "ci 77491", "ci 77492", "ci 77499",
        "titanium dioxide", "ultramarine", "carmine",
    ),
    "absorbents": ("silica", "kaolin", "talc", "bentonite", "starch"),
    "waxes": ("beeswax", "carnauba", "candelilla", "paraffin", "ozokerite"),
}

_GROUP_LABELS = {
    "humectants": "увлажняющие компоненты",
    "emollients": "смягчающие компоненты",
    "occlusives": "окклюзивные компоненты",
    "ceramides": "церамиды",
    "surfactants": "поверхностно-активные компоненты",
    "uv_filters": "UV-фильтры",
    "acids": "кислоты",
    "retinoids": "ретиноиды",
    "peptides": "пептиды",
    "antioxidants": "антиоксиданты",
    "soothing": "успокаивающие компоненты",
    "acne_actives": "компоненты против акне",
    "brightening_actives": "осветляющие компоненты",
    "clays": "глины",
    "abrasives": "абразивные частицы",
    "enzymes": "энзимы",
    "pigments": "пигменты",
    "absorbents": "абсорбенты",
    "waxes": "воски",
    "actives": "целевые активы",
}


def _text(product: Mapping) -> str:
    return " ".join(
        str(product.get(key) or "").replace("\n", " ")
        for key in ("name", "category", "subcategory", "taxonomy_category")
    ).casefold()


def _function_key(product: Mapping, classification: Mapping) -> str:
    text = _text(product)
    # Explicit sun protection is a purpose marker, not a form. It must be
    # checked before form categories such as "cream" and before a catalog pair
    # that contradicts an unmistakably named sunscreen.
    if any(
        marker in text
        for marker in (
            "sunscreen", "sun screen", "sun cream", "sun fluid", "sun serum",
            "sunblock", "spf", "защита от солнца", "солнцезащит",
        )
    ):
        return "sun_protection:spf"
    # The catalog's function_key distinguishes purpose (anti-acne, barrier,
    # brightening) from form (serum/cream/gel). It must win over generic form
    # markers, but only when the catalog source was not contradicted by text.
    trusted = str(classification.get("function_key") or "").strip()
    if trusted in _SPECS and str(classification.get("category_source") or "") == "catalog":
        return trusted
    body_area = str(classification.get("body_area") or "")
    product_type = str(classification.get("product_type") or "")
    key = f"{body_area}:{product_type}"
    if key in _SPECS:
        return key
    title = str(classification.get("canonical_category") or "").casefold()
    if "очищ" in title or "cleans" in title:
        return "face:cleansing"
    if "крем" in title or "cream" in title:
        return "face:creams"
    if "увлажн" in title or "moist" in title:
        return "face:moisturizing"
    if "сыворот" in title or "serum" in title:
        return "face:serums"
    if "солнц" in title or "spf" in title:
        return "sun_protection:spf"
    return ""


def _normalise_ingredient(name: str) -> str:
    return str(name or "").casefold().strip().split("(", 1)[0].strip()


def _matches(ingredients: Sequence[str]) -> tuple[list[str], list[str]]:
    groups: list[str] = []
    matched_ingredients: list[str] = []
    for group, markers in _MARKERS.items():
        found: list[str] = []
        for ingredient in ingredients:
            name = _normalise_ingredient(ingredient)
            if any(
                marker in name
                and not (marker == "urea" and name != "urea")
                for marker in markers
            ):
                found.append(str(ingredient).strip())
        if found:
            groups.append(group)
            for name in found:
                if name not in matched_ingredients:
                    matched_ingredients.append(name)
    return groups, matched_ingredients


def build_primary_function(
    product: Mapping,
    composition: Mapping | None = None,
    *,
    composition_status: str = "active",
) -> dict:
    """Return the independent product-function assessment.

    ``score=None`` means that the available data does not support a number:
    the category is unknown, the INCI is missing, or the composition is not
    confirmed. This is not converted to 0 or 50.
    """
    product = product or {}
    composition = composition or {}
    classification = classify_product(dict(product))
    key = _function_key(product, classification)
    spec = _SPECS.get(key)
    canonical = str(classification.get("canonical_category") or "").strip()
    category_source = str(classification.get("category_source") or "")
    category_knowledge = get_category_knowledge(canonical)
    category_purpose = str(category_knowledge.get("intended_purpose") or "").strip()

    inci_raw = str(composition.get("inci_raw") or product.get("ingredients") or "").strip()
    ingredients = split_inci(inci_raw)

    if spec is None:
        return {
            "version": PRIMARY_FUNCTION_VERSION,
            "status": "insufficient_evidence",
            "function_id": "",
            "label": "Основная функция не определена",
            "purpose": category_purpose or "Недостаточно подтверждённых данных о назначении.",
            "score": None,
            "reason": "По данным каталога и состава нельзя надёжно определить основную функцию.",
            "basis": [],
            "category": canonical,
            "category_source": category_source,
        }

    if str(composition_status or "") != "active":
        return {
            "version": PRIMARY_FUNCTION_VERSION,
            "status": "insufficient_evidence",
            "function_id": spec.key,
            "label": spec.label,
            "purpose": spec.purpose,
            "score": None,
            "reason": "Состав не подтверждён, поэтому оценивать соответствие функции нельзя.",
            "basis": [],
            "category": canonical,
            "category_source": category_source,
        }

    if len(ingredients) < 2:
        return {
            "version": PRIMARY_FUNCTION_VERSION,
            "status": "insufficient_evidence",
            "function_id": spec.key,
            "label": spec.label,
            "purpose": spec.purpose,
            "score": None,
            "reason": "Для оценки основной функции нужен подтверждённый состав.",
            "basis": [],
            "category": canonical,
            "category_source": category_source,
        }

    found_groups, matched = _matches(ingredients)
    expected = list(spec.expected_groups)
    # "actives" is a convenience family: any targeted active supports a serum.
    if "actives" in expected:
        active_groups = {
            "acids", "retinoids", "peptides", "antioxidants", "soothing",
        }
        found_active = [group for group in found_groups if group in active_groups]
        expected = [group for group in expected if group != "actives"]
        if found_active:
            found_groups = list(dict.fromkeys(found_groups + ["actives"]))
            expected = list(dict.fromkeys(expected + ["actives"]))
    # All remaining expected groups are real marker families. Unknown groups
    # are ignored rather than silently changing the denominator.
    expected = [group for group in expected if group in _MARKERS or group == "actives"]
    relevant_found = [group for group in expected if group in found_groups]
    if not relevant_found:
        # The formula exists, but it contains no recognised support for this
        # function. That is insufficient evidence, not a zero or an invented
        # low score: the lexicon is not a proof of absence.
        return {
            "version": PRIMARY_FUNCTION_VERSION,
            "status": "insufficient_evidence",
            "function_id": spec.key,
            "label": spec.label,
            "purpose": spec.purpose,
            "score": None,
            "reason": (
                f"В составе не найдено подтверждённых компонентов для функции "
                f"«{spec.label}»."
            ),
            "basis": [
                {
                    "type": "category",
                    "label": "Категория",
                    "value": canonical or "не определена",
                    "source": category_source or "каталог",
                }
            ],
            "category": canonical,
            "category_source": category_source,
        }
    # The score describes formula support, not clinical efficacy. A category
    # and even several matching ingredients cannot prove that the finished
    # product works at an effective concentration. The maximum is therefore
    # deliberately below 100: 100 is reserved for independently confirmed
    # efficacy, which this deterministic input does not contain.
    # Only groups that belong to the function's own support model count. A
    # cleanser does not become 100% cleansing because it also contains a
    # humectant or a soothing extract; those are useful, but not evidence for
    # the primary cleansing function.
    score_groups = list(relevant_found)
    support_count = len(score_groups)
    if support_count == 1:
        score = 50
    elif support_count == 2:
        score = 65
    elif support_count == 3:
        score = 80
    else:
        score = 90

    found_labels = [
        _GROUP_LABELS.get(group, group) for group in score_groups
    ]
    if support_count == 1:
        reason = (
            f"Состав содержит базовую функциональную группу для функции "
            f"«{spec.label}»: {', '.join(found_labels)}."
        )
    else:
        reason = (
            f"Состав содержит {support_count} независимые функциональные группы "
            f"для функции «{spec.label}»: {', '.join(found_labels)}."
        )

    basis = [
        {
            "type": "category",
            "label": "Категория",
            "value": canonical or "не определена",
            "source": category_source or "каталог",
        }
    ]
    if matched:
        basis.append({
            "type": "composition",
            "label": "Подтверждающие компоненты",
            "value": ", ".join(matched[:8]),
            "source": str(composition.get("source") or "подтверждённый INCI"),
        })
    if found_labels:
        basis.append({
            "type": "function",
            "label": "Что учтено",
            "value": "; ".join(found_labels),
            "source": "состав",
        })
    return {
        "version": PRIMARY_FUNCTION_VERSION,
        "status": "assessed",
        "function_id": spec.key,
        "label": spec.label,
        "purpose": spec.purpose,
        "score": score,
        "score_kind": PRIMARY_SCORE_KIND,
        "score_label": PRIMARY_SCORE_LABEL,
        "score_note": PRIMARY_SCORE_NOTE,
        "reason": reason,
        "basis": basis,
        "category": canonical,
        "category_source": category_source,
    }


_PURPOSE_DETAIL_MARKERS = (
    "только", " кроме", "за исключением", "избег", "концентрац", "частот",
    "утро", "вечер", "до ", "после ", "курс", "не более", "не менее",
    "механизм", "кислот", "фермент", "ретинол", "пептид", "кератин",
    "водостой", "зон", " если", " при ", " нельзя", " не ",
)


def _purpose_adds_extra_detail(label: str, purpose: str) -> bool:
    """Whether the purpose text adds a mechanism/constraint, not a paraphrase.

    All built-in ``FunctionSpec.purpose`` values are short restatements of the
    label. They remain available to research/LLM context, but are not repeated
    under the user-facing "Основная функция" line.
    """
    clean = " ".join(str(purpose or "").replace("\n", " ").split())
    if not clean:
        return False
    if str(label or "").startswith("Основная функция не определена"):
        return False
    low = clean.casefold()
    if any(char.isdigit() for char in low):
        return True
    return any(marker in low for marker in _PURPOSE_DETAIL_MARKERS)


def public_primary_function(result: Mapping | None) -> dict:
    """Remove internal wording/status before returning a user-facing report."""
    result = result or {}
    label = str(result.get("label") or "Основная функция не определена")
    purpose = str(result.get("purpose") or "")
    # Do not print "Защита от солнца · Защитить кожу от ультрафиолета": the
    # title already says it. Only an actual mechanism or constraint survives.
    if not _purpose_adds_extra_detail(label, purpose):
        purpose = ""
    # The "Что учтено" row repeats the functional groups already named in the
    # reason. Keep it in the internal result for audit, but not twice in UI.
    basis = [row for row in (result.get("basis") or []) if row.get("type") != "function"]
    return {
        "label": label,
        "purpose": purpose,
        "score": result.get("score"),
        "score_kind": str(result.get("score_kind") or PRIMARY_SCORE_KIND),
        "score_label": str(result.get("score_label") or PRIMARY_SCORE_LABEL),
        "score_note": str(result.get("score_note") or PRIMARY_SCORE_NOTE),
        "reason": str(result.get("reason") or ""),
        "basis": basis,
    }


