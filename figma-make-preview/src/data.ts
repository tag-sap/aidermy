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
  checked?: boolean
}

export const CATEGORIES = [
  "Очищение",
  "Тонер",
  "Сыворотка",
  "Увлажнение",
  "Защита",
  "Эксфолиант",
] as const

const IMG = (n: string) =>
  `https://images.unsplash.com/${n}?auto=format&fit=crop&w=520&q=85`

export const products: Product[] = [
  { id: 1, brand: "CeraVe", name: "Hydrating Facial Cleanser", category: "Очищение", score: 88, verdict: "Подходит", image: IMG("photo-1567721913486-6585f069b332"), tags: ["Церамиды", "Мягкое"], state: "using", checked: true },
  { id: 2, brand: "La Roche-Posay", name: "Toleriane Caring Wash", category: "Очищение", score: 90, verdict: "Подходит", image: IMG("photo-1608248543803-ba4f8c70ae0b"), tags: ["Без отдушки"], state: "want", checked: true },
  { id: 3, brand: "Some By Mi", name: "AHA BHA PHA 30 Days Miracle Toner", category: "Тонер", score: 34, verdict: "Не подходит", image: IMG("photo-1739980155900-36562bcb7857"), tags: ["Кислоты", "Отдушка"], state: "finished", checked: true },
  { id: 4, brand: "Pyunkang Yul", name: "Essence Toner", category: "Тонер", score: 78, verdict: "С осторожностью", image: IMG("photo-1620916566398-39f1143ab7be"), tags: ["Увлажнение"], state: "using", checked: true },
  { id: 5, brand: "The Ordinary", name: "Niacinamide 10% + Zinc 1%", category: "Сыворотка", score: 71, verdict: "С осторожностью", image: IMG("photo-1580870069867-74c57ee1bb07"), tags: ["Ниацинамид"], state: "using", checked: true },
  { id: 6, brand: "COSRX", name: "Advanced Snail 96 Mucin Power Essence", category: "Сыворотка", score: 92, verdict: "Подходит", image: IMG("photo-1616750819456-5cdee9b85d22"), tags: ["Восстановление"], state: "using", checked: true },
  { id: 7, brand: "Beauty of Joseon", name: "Glow Serum: Propolis + Niacinamide", category: "Сыворотка", score: 84, verdict: "Подходит", image: IMG("photo-1608248597279-f99d160bfcbc"), tags: ["Сияние"], state: "want", checked: true },
  { id: 8, brand: "The Ordinary", name: "Hyaluronic Acid 2% + B5", category: "Сыворотка", score: 82, verdict: "Подходит", image: IMG("photo-1620916566882-33a4d2b0e0c7"), tags: ["Гиалурон"], state: "finished", checked: true },
  { id: 9, brand: "COSRX", name: "Advanced Snail 92 All in one Cream", category: "Увлажнение", score: 89, verdict: "Подходит", image: IMG("photo-1601049676869-702ea24cfd58"), tags: ["Питание"], state: "using", checked: true },
  { id: 10, brand: "CeraVe", name: "Moisturizing Cream", category: "Увлажнение", score: 86, verdict: "Подходит", image: IMG("photo-1608248543803-ba4f8c70ae0b"), tags: ["Церамиды"], state: "using", checked: true },
  { id: 11, brand: "Beauty of Joseon", name: "Relief Sun Rice + Probiotics SPF50+", category: "Защита", score: 86, verdict: "Подходит", image: IMG("photo-1585652757141-8837d676fac8"), tags: ["SPF", "Без отдушки"], state: "using", checked: true },
  { id: 12, brand: "La Roche-Posay", name: "Anthelios UVMune 400 SPF50+", category: "Защита", score: 91, verdict: "Подходит", image: IMG("photo-1556228720-195a672e8a03"), tags: ["SPF", "UVA"], state: "want", checked: true },
  { id: 13, brand: "Paula's Choice", name: "Skin Perfecting 2% BHA Liquid", category: "Эксфолиант", score: 58, verdict: "С осторожностью", image: IMG("photo-1613803745799-ba6c10aace85"), tags: ["BHA"], state: "want", checked: true },
  { id: 14, brand: "The Ordinary", name: "AHA 30% + BHA 2% Peeling Solution", category: "Эксфолиант", score: 44, verdict: "Не подходит", image: IMG("photo-1608571423902-eed4a5ad8108"), tags: ["Кислоты"], checked: true },
  { id: 15, brand: "Innisfree", name: "Green Tea Seed Serum", category: "Сыворотка", score: null, verdict: null, image: IMG("photo-1605371924599-2d036cd08ff3"), tags: ["Антиоксиданты"], checked: false },
  { id: 16, brand: "Klairs", name: "Supple Preparation Facial Toner", category: "Тонер", score: null, verdict: null, image: IMG("photo-1605371924599-2d036cd08ff3"), tags: ["Успокоение"], state: "want", checked: false },
]

export const skinProfile = {
  name: "Анна",
  initials: "АК",
  skinType: "Комбинированная, чувствительная",
  goals: ["Барьер", "Увлажнение"],
  sensitivity: "Повышенная",
  avoid: ["Отдушки", "Спирт"],
  therapy: ["Ретиноид — адапален (вечер)"],
  procedures: ["—"],
  intolerances: ["Отдушки", "Эфирные масла", "Спирт"],
}

export const shelfReport = {
  average: 82,
  trend: [76, 78, 79, 80, 82],
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

// Опросник: глубокая ветвящаяся структура (mock-конфиг, логика та же, что в V1).
export type QuizOption = { id: string; label: string }
export type QuizStep = {
  id: string
  title: string
  hint?: string
  type: "single" | "multi"
  options: QuizOption[]
}

export const QUIZ: QuizStep[] = [
  {
    id: "skin_type",
    title: "Какой у вас тип кожи?",
    hint: "Можно выбрать «Не знаю» — разберёмся по дальнейшим ответам.",
    type: "single",
    options: [
      { id: "normal", label: "Нормальная" },
      { id: "dry", label: "Сухая" },
      { id: "oily", label: "Жирная" },
      { id: "combination", label: "Комбинированная" },
      { id: "sensitive", label: "Чувствительная" },
      { id: "unknown", label: "Не знаю" },
    ],
  },
  {
    id: "concerns",
    title: "Что беспокоит кожу?",
    hint: "Выберите всё, что актуально. По каждому пункту зададим уточняющий вопрос.",
    type: "multi",
    options: [
      { id: "acne", label: "Высыпания" },
      { id: "pores", label: "Поры и жирность" },
      { id: "dryness", label: "Сухость / обезвоженность" },
      { id: "sensitivity", label: "Чувствительность / краснота" },
      { id: "pigment", label: "Пигментация / тон" },
      { id: "aging", label: "Возрастные изменения" },
      { id: "none", label: "Ничего из этого" },
    ],
  },
  {
    id: "concern_detail",
    title: "Уточним про состояние",
    hint: "Это помогает точнее подобрать активы и ограничения.",
    type: "multi",
    options: [
      { id: "breakouts", label: "Появляются регулярно" },
      { id: "oily_tzone", label: "Жирная Т-зона" },
      { id: "tightness", label: "Стянутость после умывания" },
      { id: "redness", label: "Кожа часто краснеет" },
      { id: "dark_spots", label: "Тёмные пятна / следы" },
      { id: "fine_lines", label: "Первые морщинки" },
    ],
  },
  {
    id: "therapy",
    title: "Используете ли активное лечение?",
    hint: "Ретиноиды, кислоты или аптечные средства.",
    type: "multi",
    options: [
      { id: "retinoid", label: "Ретиноид" },
      { id: "acids", label: "Кислоты (AHA/BHA/PHA)" },
      { id: "azelaic", label: "Азелаиновая кислота" },
      { id: "antibiotic", label: "Антибактериальное средство" },
      { id: "none", label: "Ничего не использую" },
    ],
  },
  {
    id: "procedures",
    title: "Были ли недавно процедуры?",
    hint: "Лазер, пилинги, микронидлинг за последний месяц.",
    type: "single",
    options: [
      { id: "laser", label: "Лазер / IPL" },
      { id: "peeling", label: "Химический пилинг" },
      { id: "microneedling", label: "Микронидлинг" },
      { id: "none", label: "Ничего не было" },
    ],
  },
  {
    id: "intolerances",
    title: "Есть ли непереносимости?",
    hint: "Что кожа обычно не принимает.",
    type: "multi",
    options: [
      { id: "fragrance", label: "Отдушки" },
      { id: "alcohol", label: "Спирт" },
      { id: "essential_oils", label: "Эфирные масла" },
      { id: "niacinamide", label: "Ниацинамид" },
      { id: "none", label: "Ничего такого" },
    ],
  },
  {
    id: "goals",
    title: "Какие цели ухода?",
    hint: "Главное, к чему хотите прийти.",
    type: "multi",
    options: [
      { id: "barrier", label: "Восстановить барьер" },
      { id: "hydration", label: "Увлажнение" },
      { id: "sebum", label: "Себорегуляция" },
      { id: "brightening", label: "Осветление тона" },
      { id: "anti_age", label: "Антивозраст" },
      { id: "calm", label: "Успокоение" },
    ],
  },
]


