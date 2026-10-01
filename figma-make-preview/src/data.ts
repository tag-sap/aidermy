// Aidermy V3 — данные и типы (mock, для визуального preview).
// Реальная логика (scoring, Match, Report) живёт в backend V1 и сюда НЕ подключена.

export type Page = "home" | "shelf" | "scan" | "catalog" | "report" | "profile"
export type ProductState = "using" | "want" | "finished"
export type Verdict = "Подходит" | "С осторожностью" | "Не подходит"

export type Product = {
  id: number
  brand: string
  name: string
  category: string
  score: number | null
  verdict: Verdict | null
  image: string
  tags: string[]
  state?: ProductState
  checked?: boolean   // есть Match
  report?: boolean    // есть сгенерированный Report
}

export const CATEGORIES = ["Очищение", "Тонер", "Сыворотка", "Увлажнение", "Защита", "Эксфолиант"] as const

const IMG = (n: string) => `https://images.unsplash.com/${n}?auto=format&fit=crop&w=520&q=85`

export const products: Product[] = [
  { id: 1, brand: "CeraVe", name: "Hydrating Facial Cleanser", category: "Очищение", score: 88, verdict: "Подходит", image: IMG("photo-1567721913486-6585f069b332"), tags: ["Церамиды", "Мягкое"], state: "using", checked: true, report: true },
  { id: 2, brand: "La Roche-Posay", name: "Toleriane Caring Wash", category: "Очищение", score: 90, verdict: "Подходит", image: IMG("photo-1608248543803-ba4f8c70ae0b"), tags: ["Без отдушки"], state: "want", checked: true },
  { id: 3, brand: "Some By Mi", name: "AHA BHA PHA 30 Days Miracle Toner", category: "Тонер", score: 34, verdict: "Не подходит", image: IMG("photo-1739980155900-36562bcb7857"), tags: ["Кислоты", "Отдушка"], state: "finished", checked: true, report: true },
  { id: 4, brand: "Pyunkang Yul", name: "Essence Toner", category: "Тонер", score: 78, verdict: "С осторожностью", image: IMG("photo-1620916566398-39f1143ab7be"), tags: ["Увлажнение"], state: "using", checked: true },
  { id: 5, brand: "The Ordinary", name: "Niacinamide 10% + Zinc 1%", category: "Сыворотка", score: 71, verdict: "С осторожностью", image: IMG("photo-1580870069867-74c57ee1bb07"), tags: ["Ниацинамид"], state: "using", checked: true },
  { id: 6, brand: "COSRX", name: "Advanced Snail 96 Mucin Power Essence", category: "Сыворотка", score: 92, verdict: "Подходит", image: IMG("photo-1616750819456-5cdee9b85d22"), tags: ["Восстановление"], state: "using", checked: true, report: true },
  { id: 7, brand: "Beauty of Joseon", name: "Glow Serum: Propolis + Niacinamide", category: "Сыворотка", score: 84, verdict: "Подходит", image: IMG("photo-1608248597279-f99d160bfcbc"), tags: ["Сияние"], state: "want", checked: true },
  { id: 8, brand: "The Ordinary", name: "Hyaluronic Acid 2% + B5", category: "Сыворотка", score: 82, verdict: "Подходит", image: IMG("photo-1620916566882-33a4d2b0e0c7"), tags: ["Гиалурон"], state: "finished", checked: true },
  { id: 9, brand: "COSRX", name: "Advanced Snail 92 All in one Cream", category: "Увлажнение", score: 89, verdict: "Подходит", image: IMG("photo-1601049676869-702ea24cfd58"), tags: ["Питание"], state: "using", checked: true, report: true },
  { id: 10, brand: "CeraVe", name: "Moisturizing Cream", category: "Увлажнение", score: 86, verdict: "Подходит", image: IMG("photo-1608248543803-ba4f8c70ae0b"), tags: ["Церамиды"], state: "using", checked: true },
  { id: 11, brand: "Beauty of Joseon", name: "Relief Sun Rice + Probiotics SPF50+", category: "Защита", score: 86, verdict: "Подходит", image: IMG("photo-1585652757141-8837d676fac8"), tags: ["SPF", "Без отдушки"], state: "using", checked: true },
  { id: 12, brand: "La Roche-Posay", name: "Anthelios UVMune 400 SPF50+", category: "Защита", score: 91, verdict: "Подходит", image: IMG("photo-1556228720-195a672e8a03"), tags: ["SPF", "UVA"], state: "want", checked: true },
  { id: 13, brand: "Paula's Choice", name: "Skin Perfecting 2% BHA Liquid", category: "Эксфолиант", score: 58, verdict: "С осторожностью", image: IMG("photo-1613803745799-ba6c10aace85"), tags: ["BHA"], state: "want", checked: true },
  { id: 14, brand: "The Ordinary", name: "AHA 30% + BHA 2% Peeling Solution", category: "Эксфолиант", score: 44, verdict: "Не подходит", image: IMG("photo-1608571423902-eed4a5ad8108"), tags: ["Кислоты"], checked: true },
  { id: 15, brand: "Innisfree", name: "Green Tea Seed Serum", category: "Сыворотка", score: null, verdict: null, image: IMG("photo-1605371924599-2d036cd08ff3"), tags: ["Антиоксиданты"], checked: false },
  { id: 16, brand: "Klairs", name: "Supple Preparation Facial Toner", category: "Тонер", score: null, verdict: null, image: IMG("photo-1605371924599-2d036cd08ff3"), tags: ["Успокоение"], state: "want", checked: false },
]

export const skinProfile = {
  name: "Ольга",
  initials: "ОЛ",
  skinType: "Комбинированная, чувствительная",
  age: "25–35",
  goals: ["Барьер", "Увлажнение"],
  concerns: ["Сухость", "Чувствительность"],
  sensitivity: "Повышенная",
  avoid: ["Отдушки", "Спирт"],
  therapy: ["Ретиноид — адапален"],
  procedures: ["—"],
  intolerances: ["Отдушки", "Эфирные масла", "Спирт"],
}
// ===== Опросник кожи (полный сценарий из V1, data-driven) =====
export type QuizOption = { id: string; label: string }
export type QuizQuestion = { id: string; label: string; type: "single" | "multi"; options: QuizOption[] }
export type QuizBranch = { id: string; label: string; shortLabel: string; questions: QuizQuestion[] }

export const SKIN_TYPE_OPTIONS: QuizOption[] = [
  { id: "normal", label: "Нормальная" },
  { id: "dry", label: "Сухая" },
  { id: "oily", label: "Жирная" },
  { id: "combination", label: "Комбинированная" },
  { id: "sensitive", label: "Чувствительная" },
  { id: "unknown", label: "Не знаю" },
]

export const AGE_OPTIONS: QuizOption[] = [
  { id: "under_25", label: "До 25" },
  { id: "25_35", label: "25–35" },
  { id: "35_45", label: "35–45" },
  { id: "45_plus", label: "45+" },
]

export const CONCERN_CARDS: QuizBranch[] = [
  { id: "acne_general", label: "Высыпания", shortLabel: "Высыпания", questions: [
    { id: "acne_type", label: "Какие именно?", type: "multi", options: [
      { id: "blackheads", label: "Чёрные точки" }, { id: "closed_comedones", label: "Закрытые комедоны" },
      { id: "clogged_pores", label: "Забитые поры" }, { id: "papules", label: "Папулы" },
      { id: "pustules", label: "Пустулы" }, { id: "deep_inflammation", label: "Болезненные глубокие высыпания" },
      { id: "recurrent_breakouts", label: "Появляются регулярно" },
    ] },
  ] },
  { id: "sebum_pores", label: "Поры и жирность", shortLabel: "Поры и жирность", questions: [
    { id: "sebum_type", label: "Что именно?", type: "multi", options: [
      { id: "excess_sebum", label: "Кожа быстро жирнеет" }, { id: "oily_t_zone", label: "Жирная Т-зона" },
      { id: "enlarged_pores", label: "Расширенные поры" }, { id: "visible_pores", label: "Видимые поры" },
      { id: "blackheads", label: "Чёрные точки" }, { id: "sebaceous_filaments", label: "Сальные нити" },
    ] },
  ] },
  { id: "dryness", label: "Сухость / обезвоженность", shortLabel: "Сухость", questions: [
    { id: "dryness_type", label: "Что замечаете?", type: "multi", options: [
      { id: "skin_tightness", label: "Стянутость после умывания" }, { id: "dehydrated_skin", label: "Обезвоженность" },
      { id: "scaling", label: "Шелушение" }, { id: "cracking", label: "Локальные трещинки" },
      { id: "lipid_deficiency", label: "Недостаток липидов" },
    ] },
  ] },
  { id: "sensitivity", label: "Чувствительность", shortLabel: "Чувствительность", questions: [
    { id: "sensitivity_type", label: "Как кожа обычно реагирует?", type: "multi", options: [
      { id: "redness", label: "Часто краснеет" }, { id: "stinging", label: "Щиплет от косметики" },
      { id: "burning", label: "Жжёт от косметики" }, { id: "water_reactivity", label: "Реагирует на воду" },
      { id: "product_reactivity", label: "Раздражается от новых средств" }, { id: "irritation_prone", label: "Очень легко раздражается" },
    ] },
  ] },
  { id: "redness", label: "Покраснения", shortLabel: "Покраснения", questions: [
    { id: "redness_type", label: "Как проявляются?", type: "multi", options: [
      { id: "persistent_redness", label: "Постоянное покраснение" }, { id: "flushing", label: "Приливы / внезапное покраснение" },
      { id: "visible_vessels", label: "Видимые сосудики" }, { id: "couperose", label: "Купероз" },
    ] },
  ] },
  { id: "pigmentation", label: "Пигментация", shortLabel: "Пигментация", questions: [
    { id: "pigmentation_type", label: "Что беспокоит?", type: "multi", options: [
      { id: "pigmentation", label: "Общая пигментация" }, { id: "dark_spots", label: "Тёмные пятна" },
      { id: "post_acne_pigmentation", label: "Следы после акне" }, { id: "uneven_tone", label: "Неровный тон" },
      { id: "sun_pigmentation", label: "Пигментация после солнца" }, { id: "melasma", label: "Мелазма" },
    ] },
  ] },
  { id: "texture", label: "Неровный рельеф", shortLabel: "Рельеф", questions: [
    { id: "texture_type", label: "Что именно?", type: "multi", options: [
      { id: "uneven_texture", label: "Неровная текстура" }, { id: "roughness", label: "Шероховатость" },
      { id: "thickened_skin", label: "Грубая кожа" }, { id: "scaling", label: "Шелушение" },
      { id: "post_acne_texture", label: "Следы после акне" },
    ] },
  ] },
  { id: "post_acne", label: "Следы после акне", shortLabel: "Следы после акне", questions: [
    { id: "post_acne_type", label: "Что осталось?", type: "multi", options: [
      { id: "post_inflammatory_redness", label: "Красные следы" }, { id: "post_acne_pigmentation", label: "Тёмные пятна" },
      { id: "post_acne_texture", label: "Неровный рельеф" }, { id: "atrophic_scars", label: "Ямки / атрофические рубцы" },
    ] },
  ] },
  { id: "ageing", label: "Возрастные изменения", shortLabel: "Морщины", questions: [
    { id: "ageing_type", label: "Что замечаете?", type: "multi", options: [
      { id: "fine_lines", label: "Мелкие морщины" }, { id: "deep_wrinkles", label: "Глубокие морщины" },
      { id: "loss_of_firmness", label: "Снижение упругости" }, { id: "skin_density_loss", label: "Потеря плотности" },
      { id: "photoaging", label: "Фотостарение" },
    ] },
  ] },
  { id: "dullness", label: "Тусклый тон", shortLabel: "Тусклость", questions: [
    { id: "dullness_type", label: "Что именно?", type: "multi", options: [
      { id: "dullness", label: "Тусклый цвет лица" }, { id: "lack_of_radiance", label: "Недостаток сияния" },
      { id: "uneven_color", label: "Неровный цвет" },
    ] },
  ] },
]

export const THERAPY_OPTIONS: QuizOption[] = [
  { id: "topical_retinoid", label: "Ретиноиды" },
  { id: "acid_therapy", label: "Кислоты" },
  { id: "azelaic_acid_therapy", label: "Азелаиновая кислота" },
  { id: "benzoyl_peroxide", label: "Бензоилпероксид" },
  { id: "antibiotic", label: "Антибиотики" },
  { id: "none", label: "Ничего не использую" },
]

export const RETINOID_OPTIONS: QuizOption[] = [
  { id: "adapalene", label: "Адапален" },
  { id: "tretinoin", label: "Третиноин" },
  { id: "tazarotene", label: "Тазаротен" },
  { id: "systemic_isotretinoin", label: "Изотретиноин внутрь" },
  { id: "other_retinoid", label: "Другой / не знаю" },
]

export const ACID_OPTIONS: QuizOption[] = [
  { id: "aha_therapy", label: "AHA" },
  { id: "bha_therapy", label: "BHA" },
  { id: "pha_therapy", label: "PHA" },
]

export const PROCEDURE_OPTIONS: QuizOption[] = [
  { id: "recent_laser", label: "Лазер" },
  { id: "recent_ipl", label: "IPL" },
  { id: "recent_microneedling", label: "Микронидлинг" },
  { id: "recent_dermabrasion", label: "Дермабразия" },
  { id: "recent_rfa", label: "RF / RFA" },
  { id: "none", label: "Ничего не было" },
]

export const PROCEDURE_PERIODS: QuizOption[] = [
  { id: "<7", label: "Последние 7 дней" },
  { id: "7-14", label: "7–14 дней" },
  { id: "14-30", label: "14–30 дней" },
  { id: "1-3m", label: "1–3 месяца" },
  { id: ">3m", label: "Более 3 месяцев" },
]

export const INTOLERANCE_OPTIONS: QuizOption[] = [
  { id: "fragrance_intolerance", label: "Отдушки" },
  { id: "alcohol_intolerance", label: "Спирт" },
  { id: "essential_oil_intolerance", label: "Эфирные масла" },
  { id: "retinoid_intolerance", label: "Ретиноиды" },
  { id: "acid_intolerance", label: "Кислоты" },
  { id: "niacinamide_intolerance", label: "Ниацинамид" },
]

export const GOALS_OPTIONS: QuizOption[] = [
  { id: "barrier", label: "Восстановить барьер" },
  { id: "hydration", label: "Увлажнение" },
  { id: "sebum", label: "Себорегуляция" },
  { id: "brightening", label: "Осветление тона" },
  { id: "anti_age", label: "Антивозраст" },
  { id: "calm", label: "Успокоение" },
]

// ===== Отчёт (сводка полки). График = «средняя совместимость полки» по мере
// проверки продуктов (кумулятивно). Каждая точка — явно структурирована, чтобы
// после подключения API было понятно, откуда приходит показатель.
export const shelfReport = {
  average: 82,
  compatibilityHistory: [
    { step: 1, label: "CeraVe Cleanser", shelfAverage: 88 },
    { step: 2, label: "+ Essence Toner", shelfAverage: 83 },
    { step: 3, label: "+ Snail 96 Essence", shelfAverage: 86 },
    { step: 4, label: "+ Niacinamide 10%", shelfAverage: 82 },
    { step: 5, label: "+ Snail 92 Cream", shelfAverage: 83 },
    { step: 6, label: "+ Relief Sun SPF", shelfAverage: 84 },
  ],
  good: [
    "Базовый уход подобран удачно — очищение и увлажнение совместимы.",
    "В полке нет конфликтующих активов: ретиноид не пересекается с кислотами.",
    "SPF-защита присутствует — барьер защищён днём.",
  ],
  attention: [
    "Пилинг AHA/BHA и ретиноид лучше развести по разным вечерам.",
    "В тонере Pyunkang Yul есть след отдушки — при чувствительности следите за реакцией.",
    "Ниацинамид 10% может пощипывать на фоне ретиноида в первые недели.",
  ],
}



