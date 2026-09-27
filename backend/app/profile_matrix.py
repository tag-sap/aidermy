# profile_matrix.py
# Единая PROFILE MATRIX — источник истины для маппинга structured profile IDs
# в веса 6 canonical axes (profile weights / importance).
#
# UI знает только ID (closed_comedones, tretinoin, recent_laser, ...).
# Backend знает, что каждый ID означает математически.
# Калибровку матрицы можно менять, не переписывая интерфейс анкеты.
#
# mode:
#   score       -> вклад в profile weights (axes)
#   warning     -> предупреждение (НЕ вклад в score)
#   context     -> метаданные (НЕ вклад в score)
#   restriction -> ограничение/исключение (НЕ вклад в score)

from __future__ import annotations

from typing import Any, Dict, List

# Канонические оси (совпадает с scoring_config.AXES).
AXES: tuple = ("hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation")


def _axes(h: float = 0.0, b: float = 0.0, i: float = 0.0, s: float = 0.0, se: float = 0.0, p: float = 0.0) -> Dict[str, float]:
    return {"hydration": h, "barrier": b, "irritation": i, "sensitization": s, "sebum": se, "pigmentation": p}


def _m(
    id_: str,
    category: str,
    mode: str,
    axes: Dict[str, float],
    *,
    parent: str | None = None,
    mutually_exclusive_group: str | None = None,
    label: str | None = None,
    description: str | None = None,
    warning: str | None = None,
    requires_confirmation: bool = False,
    ui_section: str | None = None,
    source_type: str = "self_report",
    temporal: bool = False,
    max_contribution: float = 1.0,
) -> Dict[str, Any]:
    return {
        "id": id_,
        "category": category,
        "mode": mode,
        "axes": axes,
        "parent": parent,
        "mutually_exclusive_group": mutually_exclusive_group,
        "label": label or id_,
        "description": description,
        "warning": warning,
        "requires_confirmation": requires_confirmation,
        "ui_section": ui_section,
        "source_type": source_type,
        "temporal": temporal,
        "max_contribution": max_contribution,
    }


# ===========================================================================
# SKIN TYPES (single-select; category="skin_type")
# ===========================================================================
SKIN_TYPE_MATRIX: Dict[str, Dict[str, Any]] = {
    "normal": _m("normal", "skin_type", "score", _axes(.30, .30, .05, .00, .05, .05), label="Нормальная"),
    "dry": _m("dry", "skin_type", "score", _axes(.80, .70, .25, .05, 0, .05), label="Сухая"),
    "oily": _m("oily", "skin_type", "score", _axes(.30, .15, .30, .05, .45, .05), label="Жирная"),
    "combination": _m("combination", "skin_type", "score", _axes(.45, .20, .20, .05, .40, .05), label="Комбинированная"),
    "sensitive": _m("sensitive", "skin_type", "score", _axes(.25, .70, .75, .65, .05, .05), label="Чувствительная"),
    "dehydrated": _m(
        "dehydrated", "skin_type", "score", _axes(.85, .45, .25, .05, .05, .05),
        label="Обезвоженная", mutually_exclusive_group="dehydration",
    ),
}

# ===========================================================================
# ACNE / BREAKOUTS (category="acne")
# ===========================================================================
ACNE_MATRIX: Dict[str, Dict[str, Any]] = {
    "acne_general": _m("acne_general", "acne", "score", _axes(.15, .25, .55, .15, .45, .15), label="Акне", ui_section="acne"),
    "open_comedones": _m("open_comedones", "acne", "score", _axes(0, .05, .10, .05, .55, .10), parent="acne_general", label="Открытые комедоны"),
    "closed_comedones": _m("closed_comedones", "acne", "score", _axes(0, .05, .15, .05, .50, .10), parent="acne_general", label="Закрытые комедоны"),
    "blackheads": _m("blackheads", "acne", "score", _axes(0, 0, .05, 0, .55, .10), parent="acne_general", label="Чёрные точки"),
    "clogged_pores": _m("clogged_pores", "acne", "score", _axes(0, .05, .10, .05, .55, .05), parent="acne_general", label="Забитые поры"),
    "inflammatory_acne": _m("inflammatory_acne", "acne", "score", _axes(0, .20, .85, .50, .50, .15), parent="acne_general", label="Воспалительные высыпания"),
    "papules": _m("papules", "acne", "score", _axes(0, .15, .70, .40, .50, .15), parent="inflammatory_acne", label="Папулы"),
    "pustules": _m("pustules", "acne", "score", _axes(0, .15, .80, .20, .40, .15), parent="inflammatory_acne", label="Пустулы"),
    "deep_inflammation": _m("deep_inflammation", "acne", "score", _axes(0, .25, .90, .55, .40, .15), parent="inflammatory_acne", label="Глубокие подкожные воспаления"),
    "nodules": _m("nodules", "acne", "score", _axes(0, .25, .90, .55, .35, .20), parent="inflammatory_acne", label="Узлы"),
    "cysts": _m("cysts", "acne", "score", _axes(0, .30, .95, .60, .35, .20), parent="inflammatory_acne", label="Кисты"),
    "painful_breakouts": _m("painful_breakouts", "acne", "score", _axes(0, .20, .85, .45, .40, .10), parent="inflammatory_acne", label="Болезненные высыпания"),
    "recurrent_breakouts": _m("recurrent_breakouts", "acne", "score", _axes(.05, .20, .70, .40, .55, .10), parent="acne_general", label="Регулярные высыпания"),
}

# ===========================================================================
# SEBUM / PORES (category="sebum_pores")
# ===========================================================================
SEBUM_PORES_MATRIX: Dict[str, Dict[str, Any]] = {
    "excess_sebum": _m("excess_sebum", "sebum_pores", "score", _axes(0, .10, .20, .10, .55, .05), label="Избыток себума", ui_section="sebum_pores"),
    "oily_t_zone": _m("oily_t_zone", "sebum_pores", "score", _axes(.05, .05, .10, .05, .55, .05), parent="excess_sebum", label="Жирная Т-зона"),
    "enlarged_pores": _m("enlarged_pores", "sebum_pores", "score", _axes(0, .05, .10, .05, .50, .05), label="Расширенные поры"),
    "visible_pores": _m("visible_pores", "sebum_pores", "score", _axes(0, .05, .10, .05, .55, .05), label="Видимые поры"),
    "sebaceous_filaments": _m("sebaceous_filaments", "sebum_pores", "score", _axes(0, 0, .05, 0, .55, .05), label="Сальные нити"),
    "sebum_plugs": _m("sebum_plugs", "sebum_pores", "score", _axes(0, .05, .10, .05, .55, .05), label="Сальные пробки"),
}
# ===========================================================================
# TEXTURE / KERATINIZATION (category="texture")
# ===========================================================================
TEXTURE_MATRIX: Dict[str, Dict[str, Any]] = {
    "uneven_texture": _m("uneven_texture", "texture", "score", _axes(.15, .20, .10, .05, .20, .15), label="Неровный рельеф", ui_section="texture"),
    "roughness": _m("roughness", "texture", "score", _axes(.20, .30, .10, .10, .10, .05), label="Шероховатость"),
    "hyperkeratosis": _m("hyperkeratosis", "texture", "score", _axes(.05, .20, .15, .10, .30, .05), label="Гиперкератоз"),
    "follicular_hyperkeratosis": _m("follicular_hyperkeratosis", "texture", "score", _axes(.05, .15, .15, .10, .30, .05), parent="hyperkeratosis", label="Фолликулярный гиперкератоз"),
    "keratosis_pilaris": _m("keratosis_pilaris", "texture", "score", _axes(.05, .15, .15, .10, .25, .05), parent="hyperkeratosis", label="Кератоз пиларис"),
    "scaling": _m("scaling", "texture", "score", _axes(.40, .50, .40, .25, 0, .05), label="Шелушение"),
    "flaking": _m("flaking", "texture", "score", _axes(.50, .55, .35, .20, 0, 0), label="Отслаивание"),
    "thickened_skin": _m("thickened_skin", "texture", "score", _axes(.05, .20, .10, .05, .10, .05), label="Утолщённая кожа"),
    "post_acne_texture": _m("post_acne_texture", "texture", "score", _axes(.10, .10, .05, .05, .05, .20), label="Текстура после акне"),
}

# ===========================================================================
# DRYNESS / DEHYDRATION (category="dryness")
# ===========================================================================
DRYNESS_MATRIX: Dict[str, Dict[str, Any]] = {
    "skin_tightness": _m("skin_tightness", "dryness", "score", _axes(.75, .55, .30, .20, 0, 0), label="Стянутость", ui_section="dryness"),
    "lipid_deficiency": _m("lipid_deficiency", "dryness", "score", _axes(.65, .80, .25, .15, 0, 0), label="Недостаток липидов"),
    "dehydrated_skin": _m(
        "dehydrated_skin", "dryness", "score", _axes(1.00, .45, .25, .20, 0, .05),
        label="Обезвоженность", mutually_exclusive_group="dehydration",
    ),
    "dehydration_lines": _m("dehydration_lines", "dryness", "score", _axes(.70, .35, .10, .10, 0, .05), parent="dehydrated_skin", label="Линии обезвоженности"),
    "cracking": _m("cracking", "dryness", "score", _axes(.80, .85, .55, .35, 0, 0), label="Трещинки"),
}

# ===========================================================================
# BARRIER (category="barrier")
# ===========================================================================
BARRIER_MATRIX: Dict[str, Dict[str, Any]] = {
    "impaired_barrier": _m("impaired_barrier", "barrier", "score", _axes(.70, 1.00, .75, .70, .05, 0), label="Нарушенный барьер", ui_section="barrier"),
    "weak_barrier": _m("weak_barrier", "barrier", "score", _axes(.60, .90, .65, .60, .05, 0), parent="impaired_barrier", label="Слабый барьер"),
    "post_procedure_recovery": _m("post_procedure_recovery", "barrier", "score", _axes(.65, .90, .80, .75, 0, .05), label="Восстановление после процедур"),
}

# ===========================================================================
# SENSITIVITY / REACTIVITY (category="sensitivity")
# ===========================================================================
SENSITIVITY_MATRIX: Dict[str, Dict[str, Any]] = {
    "reactive_skin": _m("reactive_skin", "sensitivity", "score", _axes(.15, .50, .90, .90, .05, .05), label="Реактивная кожа", ui_section="sensitivity"),
    "burning": _m("burning", "sensitivity", "score", _axes(.10, .50, 1.00, .90, 0, 0), label="Жжение"),
    "stinging": _m("stinging", "sensitivity", "score", _axes(.10, .50, .95, .90, 0, 0), label="Пощипывание"),
    "irritation_prone": _m("irritation_prone", "sensitivity", "score", _axes(.10, .55, .90, .85, .05, 0), label="Склонность к раздражению"),
    "product_reactivity": _m("product_reactivity", "sensitivity", "score", _axes(.10, .55, .90, 1.00, 0, .05), label="Реакция на средства"),
    "water_reactivity": _m("water_reactivity", "sensitivity", "score", _axes(.10, .65, 1.00, .90, 0, 0), label="Реакция на воду"),
}

# ===========================================================================
# REDNESS (category="redness")
# ===========================================================================
REDNESS_MATRIX: Dict[str, Dict[str, Any]] = {
    "redness": _m("redness", "redness", "score", _axes(.05, .35, .80, .25, 0, .05), label="Покраснение", ui_section="redness"),
    "persistent_redness": _m("persistent_redness", "redness", "score", _axes(.05, .40, .90, .70, 0, .05), parent="redness", label="Постоянное покраснение"),
    "flushing": _m("flushing", "redness", "score", _axes(0, .30, .90, .80, 0, .05), parent="redness", label="Приливы"),
    "visible_vessels": _m("visible_vessels", "redness", "score", _axes(0, .25, .70, .60, 0, .10), label="Видимые сосудики"),
    "couperose": _m("couperose", "redness", "score", _axes(0, .30, .80, .25, 0, .10), label="Купероз"),
    "post_inflammatory_redness": _m("post_inflammatory_redness", "redness", "score", _axes(.05, .20, .50, .30, .05, .20), label="Поствоспалительное покраснение"),
}

# ===========================================================================
# ROSACEA (category="rosacea")
# ===========================================================================
ROSACEA_MATRIX: Dict[str, Dict[str, Any]] = {
    "rosacea": _m(
        "rosacea", "rosacea", "score", _axes(.10, .65, 1.00, .95, .10, .10),
        label="Розацеа", warning="Розацеа требует особого подбора средств и наблюдения дерматолога.",
        requires_confirmation=True, ui_section="rosacea",
    ),
    "rosacea_flushing": _m("rosacea_flushing", "rosacea", "score", _axes(.05, .50, .95, .90, 0, .05), parent="rosacea", label="Приливы при розацеа"),
    "rosacea_papules_pustules": _m("rosacea_papules_pustules", "rosacea", "score", _axes(.05, .50, 1.00, .85, .25, .10), parent="rosacea", label="Папулы/пустулы при розацеа"),
    "rosacea_burning": _m("rosacea_burning", "rosacea", "score", _axes(.10, .60, 1.00, 1.00, 0, 0), parent="rosacea", label="Жжение при розацеа"),
    "ocular_rosacea": _m(
        "ocular_rosacea", "rosacea", "warning", _axes(.10, .50, .90, .90, 0, 0),
        label="Глазная розацеа",
        warning="Глазная розацеа (окулярная) требует консультации офтальмолога/дерматолога.",
    ),
}

# ===========================================================================
# PIGMENTATION (category="pigmentation")
# ===========================================================================
PIGMENTATION_MATRIX: Dict[str, Dict[str, Any]] = {
    "pigmentation": _m("pigmentation", "pigmentation", "score", _axes(0, .10, .15, .10, 0, 1.00), label="Пигментация", ui_section="pigmentation"),
    "uneven_tone": _m("uneven_tone", "pigmentation", "score", _axes(.05, .05, .10, .05, 0, .80), parent="pigmentation", label="Неровный тон"),
    "dark_spots": _m("dark_spots", "pigmentation", "score", _axes(0, .05, .05, .05, 0, .95), parent="pigmentation", label="Тёмные пятна"),
    "pi_hyperpigmentation": _m("pi_hyperpigmentation", "pigmentation", "score", _axes(.05, .10, .25, .15, 0, 1.00), parent="pigmentation", label="Поствоспалительная гиперпигментация"),
    "post_acne_pigmentation": _m("post_acne_pigmentation", "pigmentation", "score", _axes(.05, .10, .20, .10, .10, .95), parent="pigmentation", label="Пигментация после акне"),
    "sun_pigmentation": _m("sun_pigmentation", "pigmentation", "score", _axes(0, .05, .05, .05, 0, .95), parent="pigmentation", label="Пигментация после солнца"),
    "melasma": _m("melasma", "pigmentation", "score", _axes(.05, .10, .10, .10, 0, 1.00), parent="pigmentation", label="Мелазма", requires_confirmation=True),
}

# ===========================================================================
# DULLNESS (category="dullness")
# ===========================================================================
DULLNESS_MATRIX: Dict[str, Dict[str, Any]] = {
    "dullness": _m("dullness", "dullness", "score", _axes(.20, .15, .05, .05, .10, .50), label="Тусклость", ui_section="dullness"),
    "lack_of_radiance": _m("lack_of_radiance", "dullness", "score", _axes(.20, .10, 0, 0, .05, .45), label="Недостаток сияния"),
    "uneven_color": _m("uneven_color", "dullness", "score", _axes(.05, .05, .05, .05, 0, .60), label="Неровный цвет"),
}

# ===========================================================================
# POST-ACNE / SCARS (category="post_acne")
# ===========================================================================
POST_ACNE_MATRIX: Dict[str, Dict[str, Any]] = {
    "post_acne": _m("post_acne", "post_acne", "score", _axes(.05, .10, .10, .05, .10, .40), label="Следы после акне", ui_section="post_acne"),
    "atrophic_scars": _m("atrophic_scars", "post_acne", "context", _axes(0, .05, 0, 0, 0, .15), label="Атрофические рубцы", description="Косметика ограниченно влияет на рубцы."),
    "ice_pick_scars": _m("ice_pick_scars", "post_acne", "context", _axes(0, .05, 0, 0, 0, .10), parent="atrophic_scars", label="Ice-pick рубцы"),
    "boxcar_scars": _m("boxcar_scars", "post_acne", "context", _axes(0, .05, 0, 0, 0, .10), parent="atrophic_scars", label="Boxcar рубцы"),
    "rolling_scars": _m("rolling_scars", "post_acne", "context", _axes(0, .05, 0, 0, 0, .10), parent="atrophic_scars", label="Rolling рубцы"),
    "hypertrophic_scars": _m("hypertrophic_scars", "post_acne", "context", _axes(0, .10, .05, .05, 0, .05), label="Гипертрофические рубцы"),
}

# ===========================================================================
# AGEING (category="ageing")
# ===========================================================================
AGEING_MATRIX: Dict[str, Dict[str, Any]] = {
    "fine_lines": _m("fine_lines", "ageing", "score", _axes(.30, .30, .05, .05, 0, .20), label="Мелкие морщины", ui_section="ageing"),
    "deep_wrinkles": _m("deep_wrinkles", "ageing", "score", _axes(.20, .30, .05, .05, 0, .20), label="Глубокие морщины"),
    "loss_of_elasticity": _m("loss_of_elasticity", "ageing", "score", _axes(.15, .25, 0, 0, 0, .15), label="Потеря эластичности"),
    "loss_of_firmness": _m("loss_of_firmness", "ageing", "score", _axes(.15, .25, 0, 0, 0, .15), label="Потеря упругости"),
    "skin_density_loss": _m("skin_density_loss", "ageing", "score", _axes(.15, .25, 0, 0, 0, .10), label="Потеря плотности"),
    "photoaging": _m("photoaging", "ageing", "score", _axes(.10, .20, .05, .05, 0, .50), label="Фотостарение"),
}

# ===========================================================================
# DIAGNOSED / CONTEXT CONDITIONS (category="diagnosed")
# ===========================================================================
DIAGNOSED_MATRIX: Dict[str, Dict[str, Any]] = {
    "seborrheic_dermatitis": _m("seborrheic_dermatitis", "diagnosed", "score", _axes(.15, .45, .75, .55, .55, .05), label="Себорейный дерматит", requires_confirmation=True),
    "atopic_skin": _m("atopic_skin", "diagnosed", "score", _axes(.50, .90, .85, .90, .05, .05), label="Атопичная кожа", requires_confirmation=True),
    "eczema": _m("eczema", "diagnosed", "score", _axes(.50, .90, .90, .90, 0, .05), label="Экзема", requires_confirmation=True),
    "contact_dermatitis": _m("contact_dermatitis", "diagnosed", "score", _axes(.15, .65, 1.00, 1.00, 0, .05), label="Контактный дерматит", requires_confirmation=True),
    "perioral_dermatitis": _m("perioral_dermatitis", "diagnosed", "score", _axes(.10, .60, .90, .85, .05, .05), label="Периоральный дерматит", requires_confirmation=True),
    "folliculitis": _m("folliculitis", "diagnosed", "score", _axes(.05, .25, .75, .45, .50, .10), label="Фолликулит", requires_confirmation=True),
    "psoriasis": _m("psoriasis", "diagnosed", "score", _axes(.30, .75, .80, .60, .05, .05), label="Псориаз", requires_confirmation=True),
}

# ===========================================================================
# PHOTOSENSITIVITY (category="photosensitivity")
# ===========================================================================
PHOTOSENSITIVITY_MATRIX: Dict[str, Dict[str, Any]] = {
    "photosensitivity": _m("photosensitivity", "photosensitivity", "score", _axes(.05, .30, .55, .60, 0, .60), label="Фоточувствительность", ui_section="photosensitivity"),
    "sun_reactive_skin": _m("sun_reactive_skin", "photosensitivity", "score", _axes(.05, .20, .45, .50, 0, .65), parent="photosensitivity", label="Реакция на солнце"),
    "pigmentation_after_sun": _m("pigmentation_after_sun", "photosensitivity", "score", _axes(0, .05, .10, .05, 0, .90), label="Пигментация после солнца"),
    "photosensitizing_medication": _m(
        "photosensitizing_medication", "photosensitivity", "warning", _axes(0, 0, 0, 0, 0, 0),
        label="Фотосенсибилизирующие препараты",
        warning="Некоторые препараты повышают чувствительность к солнцу — используйте SPF.",
    ),
}

# ===========================================================================
# THERAPY (category="therapy"; temporal=True)
# ===========================================================================
THERAPY_MATRIX: Dict[str, Dict[str, Any]] = {
    "topical_retinoid": _m("topical_retinoid", "therapy", "score", _axes(.35, .65, .75, .70, .10, .15), label="Наружные ретиноиды", temporal=True, ui_section="therapy"),
    "adapalene": _m("adapalene", "therapy", "score", _axes(.30, .60, .70, .65, .10, .10), parent="topical_retinoid", label="Адапален", temporal=True),
    "tretinoin": _m("tretinoin", "therapy", "score", _axes(.35, .65, .80, .75, .10, .15), parent="topical_retinoid", label="Третиноин", temporal=True),
    "tazarotene": _m("tazarotene", "therapy", "score", _axes(.35, .70, .85, .80, .10, .15), parent="topical_retinoid", label="Тазаротен", temporal=True),
    "systemic_isotretinoin": _m("systemic_isotretinoin", "therapy", "score", _axes(.70, .85, .70, .65, .05, .10), label="Системный изотретиноин", temporal=True, warning="Системные ретиноиды требуют обязательного наблюдения врача."),
    "aha_therapy": _m("aha_therapy", "therapy", "score", _axes(.15, .30, .65, .55, .15, .30), label="AHA-кислоты", temporal=True),
    "bha_therapy": _m("bha_therapy", "therapy", "score", _axes(.10, .25, .60, .50, .35, .20), label="BHA-кислоты", temporal=True),
    "pha_therapy": _m("pha_therapy", "therapy", "score", _axes(.15, .20, .35, .30, .10, .20), label="PHA-кислоты", temporal=True),
    "azelaic_acid_therapy": _m("azelaic_acid_therapy", "therapy", "score", _axes(.10, .20, .40, .30, .15, .45), label="Азелаиновая кислота", temporal=True),
    "professional_peel": _m("professional_peel", "therapy", "score", _axes(.30, .65, .90, .80, .05, .25), label="Профессиональный пилинг", temporal=True),
    "benzoyl_peroxide": _m("benzoyl_peroxide", "therapy", "score", _axes(.15, .45, .65, .50, .30, .10), label="Бензоилпероксид", temporal=True),
    "topical_antibiotic": _m("topical_antibiotic", "therapy", "score", _axes(.05, .15, .25, .20, .15, .05), label="Наружный антибиотик", temporal=True),
    "oral_antibiotic": _m("oral_antibiotic", "therapy", "score", _axes(.05, .10, .15, .15, .05, .05), label="Системный антибиотик", temporal=True),
    "anti_inflammatory_therapy": _m("anti_inflammatory_therapy", "therapy", "score", _axes(.05, .20, .35, .30, .10, .10), label="Противовоспалительная терапия", temporal=True),
    "rosacea_topical_therapy": _m("rosacea_topical_therapy", "therapy", "score", _axes(.15, .30, .50, .45, .05, .20), label="Наружная терапия розацеа", temporal=True),
    "ivermectin_therapy": _m("ivermectin_therapy", "therapy", "score", _axes(.05, .15, .25, .20, .05, .05), parent="rosacea_topical_therapy", label="Ивермектин", temporal=True),
    "metronidazole_therapy": _m("metronidazole_therapy", "therapy", "score", _axes(.05, .15, .25, .20, .05, .10), parent="rosacea_topical_therapy", label="Метронидазол", temporal=True),
    "doxycycline_antiinflammatory": _m("doxycycline_antiinflammatory", "therapy", "score", _axes(.05, .15, .25, .20, .05, .05), label="Доксициклин (противовоспалительно)", temporal=True),
    "hormonal_acne_context": _m("hormonal_acne_context", "therapy", "context", _axes(0, .10, .25, .15, .65, .10), label="Гормональное акне"),
    "hormonal_therapy": _m("hormonal_therapy", "therapy", "context", _axes(0, .05, .05, .05, .15, .10), label="Гормональная терапия"),
    "spironolactone_context": _m("spironolactone_context", "therapy", "context", _axes(0, .05, .05, .05, .20, .05), label="Спиронолактон"),
}

# ===========================================================================
# PROCEDURES (category="procedure"; temporal=True)
# ===========================================================================
PROCEDURE_MATRIX: Dict[str, Dict[str, Any]] = {
    "recent_laser": _m("recent_laser", "procedure", "score", _axes(.30, .80, 1.00, .90, 0, .30), label="Лазер", temporal=True, ui_section="procedure"),
    "recent_ipl": _m("recent_ipl", "procedure", "score", _axes(.25, .70, .85, .80, 0, .35), label="IPL", temporal=True),
    "recent_microneedling": _m("recent_microneedling", "procedure", "score", _axes(.25, .75, .90, .85, 0, .20), label="Микронидлинг", temporal=True),
    "recent_dermabrasion": _m("recent_dermabrasion", "procedure", "score", _axes(.30, .85, 1.00, .90, 0, .20), label="Дермабразия", temporal=True),
    "recent_rfa": _m("recent_rfa", "procedure", "score", _axes(.15, .45, .60, .55, 0, .10), label="RF/RFA", temporal=True),
    "recent_invasive_procedure": _m("recent_invasive_procedure", "procedure", "score", _axes(.30, .85, 1.00, .90, 0, .15), label="Инвазивная процедура", temporal=True),
}

# ===========================================================================
# Объединяем все score/category матрицы
# ===========================================================================
PROFILE_MATRIX: Dict[str, Dict[str, Any]] = {}
for _src in (
    SKIN_TYPE_MATRIX, ACNE_MATRIX, SEBUM_PORES_MATRIX, TEXTURE_MATRIX, DRYNESS_MATRIX,
    BARRIER_MATRIX, SENSITIVITY_MATRIX, REDNESS_MATRIX, ROSACEA_MATRIX, PIGMENTATION_MATRIX,
    DULLNESS_MATRIX, POST_ACNE_MATRIX, AGEING_MATRIX, DIAGNOSED_MATRIX, PHOTOSENSITIVITY_MATRIX,
    THERAPY_MATRIX, PROCEDURE_MATRIX,
):
    PROFILE_MATRIX.update(_src)

# ===========================================================================
# GOALS (metadata/context на первом этапе — НЕ добавляются к score)
# ===========================================================================
GOALS: List[str] = [
    "hydration", "barrier_repair", "sebum_control", "reduce_comedones",
    "reduce_inflammation", "reduce_redness", "reduce_pigmentation", "even_tone",
    "even_texture", "reduce_visible_pores", "reduce_wrinkles", "increase_firmness",
    "increase_radiance", "recovery_after_treatment", "maintenance",
]

# ===========================================================================
# INTOLERANCES (mode=restriction; НЕ axis weights)
# ===========================================================================
# type: "category" — маппится на категорию ингредиентов; "ingredient" — конкретный ингредиент.
INTOLERANCE_CONFIG: Dict[str, Dict[str, Any]] = {
    "fragrance_intolerance": {"type": "category", "label": "Отдушки"},
    "alcohol_intolerance": {"type": "category", "label": "Спирт"},
    "essential_oil_intolerance": {"type": "category", "label": "Эфирные масла"},
    "retinoid_intolerance": {"type": "category", "label": "Ретиноиды"},
    "acid_intolerance": {"type": "category", "label": "Кислоты"},
    "niacinamide_intolerance": {"type": "ingredient", "ingredient": "niacinamide", "label": "Ниацинамид"},
    "specific_ingredient_intolerance": {"type": "ingredient", "label": "Конкретный ингредиент"},
}

# ===========================================================================
# TEMPORAL FACTORS (configurable; НЕ зашиты в scoring engine)
# ===========================================================================
# factor применяется к axes therapy-элементов.
THERAPY_TEMPORAL_FACTOR: Dict[str, Any] = {
    "active": 1.0,
    "recent_days": 30,      # последнее использование < N дней -> "recent"
    "recent_factor": 0.6,
    "old_days": 180,        # < N дней -> "old"
    "old_factor": 0.25,
    "expired_factor": 0.0,  # >= old_days
}

# factor применяется к axes procedure-элементов по ключу периода.
PROCEDURE_TEMPORAL_DECAY: Dict[str, float] = {
    "<7 days": 1.00,
    "7-14 days": 0.75,
    "14-30 days": 0.50,
    "1-3 months": 0.20,
    ">3 months": 0.0,
}

# ===========================================================================
# LEGACY MAPPING (старые RU-поля -> новые structured IDs)
# ===========================================================================
LEGACY_SKIN_TYPE_MAP: Dict[str, str] = {
    "нормальн": "normal",
    "сухая": "dry",
    "сух": "dry",
    "жирн": "oily",
    "комбинирован": "combination",
    "чувствительн": "sensitive",
    "обезвожен": "dehydrated",
}

LEGACY_CONCERN_MAP: Dict[str, str] = {
    "акне": "acne_general",
    "пигментаци": "pigmentation",
    "морщин": "fine_lines",
    "покраснен": "redness",
    "пор": "enlarged_pores",
    "тускл": "dullness",
    "обезвожен": "dehydrated_skin",
    "купероз": "couperose",
}

LEGACY_ALLERGY_MAP: Dict[str, str] = {
    "отдушк": "fragrance_intolerance",
    "спирт": "alcohol_intolerance",
    "эфирн": "essential_oil_intolerance",
    "ретиноид": "retinoid_intolerance",
    "кислот": "acid_intolerance",
}

