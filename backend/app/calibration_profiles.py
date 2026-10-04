# calibration_profiles.py
# Версионированный набор Calibration Profiles (matrix 30 профилей).
#
# Профили — это structured profile (format profile_resolver.resolve_personal_profile):
#   skin_type + concerns + therapy + procedures (+ imperfections/states/selected).
# Они используются ТОЛЬКО в AI Calibration — НЕ влияют на production score напрямую.

from __future__ import annotations

from typing import Any, Dict, List

CALIBRATION_PROFILES_VERSION = "1.0"


def _p(pid: str, label: str, skin_type: str, concerns: List[str] | None = None,
       therapy: List[Dict[str, Any]] | None = None,
       procedures: List[Dict[str, Any]] | None = None,
       imperfections: List[str] | None = None,
       tags: List[str] | None = None) -> Dict[str, Any]:
    return {
        "id": pid,
        "label": label,
        "version": CALIBRATION_PROFILES_VERSION,
        "tags": tags or [],
        "structured": {
            "skin_type": skin_type,
            "concerns": concerns or [],
            "imperfections": imperfections or [],
            "states": [],
            "selected": [],
            "therapy": therapy or [],
            "procedures": procedures or [],
        },
    }


# 30 профилей — осмысленная calibration matrix.
CALIBRATION_PROFILES: List[Dict[str, Any]] = [
    # --- Нейтральные / базовые ---
    _p("P01", "Нормальная (нейтральная)", "normal"),
    _p("P02", "Сухая (нейтральная)", "dry"),
    _p("P03", "Жирная (нейтральная)", "oily"),
    _p("P04", "Комбинированная (нейтральная)", "combination"),
    _p("P05", "Обезвоженная", "dehydrated"),

    # --- Sensitivity ---
    _p("P06", "Чувствительная (базовая)", "sensitive"),
    _p("P07", "Реактивная кожа", "sensitive", concerns=["reactive_skin"]),
    _p("P08", "Склонность к раздражению", "sensitive", concerns=["irritation_prone"]),
    _p("P09", "Покраснение", "sensitive", concerns=["redness"]),
    _p("P10", "Розацеа-чувствительная", "sensitive", concerns=["rosacea"]),

    # --- Acne / sebum ---
    _p("P11", "Жирная + акне", "oily", concerns=["acne_general"]),
    _p("P12", "Жирная + расширенные поры", "oily", concerns=["enlarged_pores"]),
    _p("P13", "Комбинированная + акне", "combination", concerns=["acne_general"]),
    _p("P14", "Акне воспалительное", "oily", concerns=["inflammatory_acne"]),

    # --- Barrier / dryness ---
    _p("P15", "Сухая + нарушенный барьер", "dry", concerns=["impaired_barrier"]),
    _p("P16", "Сухая + шелушение", "dry", concerns=["scaling"]),
    _p("P17", "Обезвоженность", "dry", concerns=["dehydrated_skin"]),

    # --- Pigmentation ---
    _p("P18", "Пигментация", "combination", concerns=["pigmentation"]),
    _p("P19", "Пигментация после акне", "combination", concerns=["post_acne_pigmentation"]),
    _p("P20", "Тусклость / неровный тон", "combination", concerns=["dullness"]),

    # --- Ageing ---
    _p("P21", "Морщины / anti-age", "normal", concerns=["fine_lines"]),
    _p("P22", "Упругость / лифтинг", "normal", concerns=["fine_lines"]),

    # --- Active treatments (stress) ---
    _p("P23", "Чувствительная + активный ретиноид", "sensitive",
       therapy=[{"id": "tretinoin", "active": True}]),
    _p("P24", "Чувствительная + ретиноид + свежий пилинг", "sensitive",
       therapy=[{"id": "tretinoin", "active": True}],
       procedures=[{"id": "recent_peeling", "period": "<7"}]),
    _p("P25", "Жирная + активный ретиноид", "oily",
       therapy=[{"id": "tretinoin", "active": True}]),
    _p("P26", "Акне + антибиотик", "oily",
       concerns=["acne_general"],
       therapy=[{"id": "antibiotic", "active": True}]),

    # --- Multiple concerns ---
    _p("P27", "Чувствительная + акне (мульти)", "sensitive", concerns=["acne_general", "reactive_skin"]),
    _p("P28", "Сухая + пигментация (мульти)", "dry", concerns=["impaired_barrier", "pigmentation"]),
    _p("P29", "Жирная + пигментация (мульти)", "oily", concerns=["acne_general", "pigmentation"]),

    # --- Stress: сильные конфликты ---
    _p("P30", "Чувствительная + ретиноид + антибиотик + пилинг (max conflict)",
       "sensitive",
       concerns=["reactive_skin"],
       therapy=[{"id": "tretinoin", "active": True}, {"id": "antibiotic", "active": True}],
       procedures=[{"id": "recent_peeling", "period": "<7"}]),
]


def profile_by_id(pid: str) -> Dict[str, Any] | None:
    for p in CALIBRATION_PROFILES:
        if p["id"] == pid:
            return p
    return None
