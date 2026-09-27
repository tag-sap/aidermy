// lib/profile-questionnaire.ts
// Data-driven конфиг анкеты (progressive disclosure).
// UI знает только canonical IDs; backend (PROFILE_MATRIX) знает математику.

import type { StructuredProfile } from '@/lib/store'

export type QuestionOption = { id: string; label: string; hint?: string }

export type Question = {
  id: string
  label: string
  type: 'single' | 'multi'
  options: QuestionOption[]
  showWhen?: { field: 'concerns'; contains: string }[]
}

export type Branch = {
  id: string          // canonical top-level concern ID
  label: string
  shortLabel: string
  questions: Question[]
}

// Экран 1 — тип кожи (canonical IDs).
export const SKIN_TYPE_OPTIONS: QuestionOption[] = [
  { id: 'normal', label: 'Нормальная' },
  { id: 'dry', label: 'Сухая' },
  { id: 'oily', label: 'Жирная' },
  { id: 'combination', label: 'Комбинированная' },
  { id: 'sensitive', label: 'Чувствительная' },
  { id: 'unknown', label: 'Не знаю' },
]

export const AGE_OPTIONS: QuestionOption[] = [
  { id: 'under_25', label: 'До 25' },
  { id: '25_35', label: '25–35' },
  { id: '35_45', label: '35–45' },
  { id: '45_plus', label: '45+' },
]

// Экран 2 — карточки «что беспокоит» (branching point).
export const CONCERN_CARDS: Branch[] = [
  {
    id: 'acne_general', label: 'Высыпания', shortLabel: 'Высыпания',
    questions: [
      {
        id: 'acne_type', label: 'Какие именно?', type: 'multi',
        options: [
          { id: 'blackheads', label: 'Чёрные точки' },
          { id: 'closed_comedones', label: 'Закрытые комедоны' },
          { id: 'clogged_pores', label: 'Забитые поры' },
          { id: 'papules', label: 'Папулы' },
          { id: 'pustules', label: 'Пустулы' },
          { id: 'deep_inflammation', label: 'Болезненные глубокие высыпания' },
          { id: 'recurrent_breakouts', label: 'Появляются регулярно' },
          { id: 'acne_general', label: 'Не знаю / в целом акне' },
        ],
      },
    ],
  },
  {
    id: 'sebum_pores', label: 'Поры и жирность', shortLabel: 'Поры и жирность',
    questions: [
      {
        id: 'sebum_type', label: 'Что именно?', type: 'multi',
        options: [
          { id: 'excess_sebum', label: 'Кожа быстро жирнеет' },
          { id: 'oily_t_zone', label: 'Жирная Т-зона' },
          { id: 'enlarged_pores', label: 'Расширенные поры' },
          { id: 'visible_pores', label: 'Видимые поры' },
          { id: 'blackheads', label: 'Чёрные точки' },
          { id: 'sebaceous_filaments', label: 'Сальные нити' },
          { id: 'sebum_plugs', label: 'Забитые поры' },
        ],
      },
    ],
  },
  {
    id: 'dryness', label: 'Сухость / обезвоженность', shortLabel: 'Сухость',
    questions: [
      {
        id: 'dryness_type', label: 'Что замечаете?', type: 'multi',
        options: [
          { id: 'skin_tightness', label: 'Стянутость после умывания' },
          { id: 'dehydrated_skin', label: 'Обезвоженность' },
          { id: 'scaling', label: 'Шелушение' },
          { id: 'cracking', label: 'Локальные трещинки' },
          { id: 'lipid_deficiency', label: 'Недостаток липидов' },
        ],
      },
    ],
  },
  {
    id: 'sensitivity', label: 'Чувствительность', shortLabel: 'Чувствительность',
    questions: [
      {
        id: 'sensitivity_type', label: 'Как кожа обычно реагирует?', type: 'multi',
        options: [
          { id: 'redness', label: 'Часто краснеет' },
          { id: 'stinging', label: 'Щиплет от косметики' },
          { id: 'burning', label: 'Жжёт от косметики' },
          { id: 'water_reactivity', label: 'Реагирует на воду' },
          { id: 'product_reactivity', label: 'Раздражается от новых средств' },
          { id: 'irritation_prone', label: 'Очень легко раздражается' },
        ],
      },
    ],
  },
  {
    id: 'redness', label: 'Покраснения', shortLabel: 'Покраснения',
    questions: [
      {
        id: 'redness_type', label: 'Как проявляются?', type: 'multi',
        options: [
          { id: 'persistent_redness', label: 'Постоянное покраснение' },
          { id: 'flushing', label: 'Приливы / внезапное покраснение' },
          { id: 'visible_vessels', label: 'Видимые сосудики' },
          { id: 'couperose', label: 'Купероз' },
          { id: 'rosacea_burning', label: 'Жжение вместе с покраснением' },
        ],
      },
      {
        id: 'rosacea_diagnosis', label: 'Вам ставили диагноз «розацеа»?', type: 'single',
        options: [
          { id: 'no', label: 'Нет' },
          { id: 'yes', label: 'Да' },
          { id: 'dont_know', label: 'Не знаю' },
        ],
      },
      {
        id: 'rosacea_type', label: 'Что именно проявляется при розацеа?', type: 'multi',
        showWhen: [{ field: 'concerns', contains: 'redness' }],
        options: [
          { id: 'rosacea_flushing', label: 'Приливы' },
          { id: 'rosacea_burning', label: 'Жжение' },
          { id: 'rosacea_papules_pustules', label: 'Папулы / пустулы' },
          { id: 'ocular_rosacea', label: 'Раздражение в области глаз' },
        ],
      },
    ],
  {
    id: 'pigmentation', label: 'Пигментация', shortLabel: 'Пигментация',
    questions: [
      {
        id: 'pigmentation_type', label: 'Что беспокоит?', type: 'multi',
        options: [
          { id: 'pigmentation', label: 'Общая пигментация' },
          { id: 'dark_spots', label: 'Тёмные пятна' },
          { id: 'post_acne_pigmentation', label: 'Следы после акне' },
          { id: 'uneven_tone', label: 'Неровный тон' },
          { id: 'sun_pigmentation', label: 'Пигментация после солнца' },
          { id: 'melasma', label: 'Мелазма (если известен диагноз)' },
        ],
      },
    ],
  },
  {
    id: 'texture', label: 'Неровный рельеф', shortLabel: 'Рельеф',
    questions: [
      {
        id: 'texture_type', label: 'Что именно?', type: 'multi',
        options: [
          { id: 'uneven_texture', label: 'Неровная текстура' },
          { id: 'roughness', label: 'Шероховатость' },
          { id: 'thickened_skin', label: 'Грубая кожа' },
          { id: 'scaling', label: 'Шелушение' },
          { id: 'hyperkeratosis', label: 'Гиперкератоз (если известно)' },
          { id: 'keratosis_pilaris', label: 'Гусиная кожа / фолликулярный кератоз' },
          { id: 'post_acne_texture', label: 'Следы/текстура после акне' },
        ],
      },
    ],
  },
  {
    id: 'post_acne', label: 'Следы после акне', shortLabel: 'Следы после акне',
    questions: [
      {
        id: 'post_acne_type', label: 'Что осталось после высыпаний?', type: 'multi',
        options: [
          { id: 'post_inflammatory_redness', label: 'Красные следы' },
          { id: 'post_acne_pigmentation', label: 'Тёмные пятна' },
          { id: 'post_acne_texture', label: 'Неровный рельеф' },
          { id: 'atrophic_scars', label: 'Ямки / атрофические рубцы' },
          { id: 'hypertrophic_scars', label: 'Выпуклые рубцы' },
        ],
      },
    ],
  },
  {
    id: 'ageing', label: 'Возрастные изменения', shortLabel: 'Морщины',
    questions: [
      {
        id: 'ageing_type', label: 'Что замечаете?', type: 'multi',
        options: [
          { id: 'fine_lines', label: 'Мелкие морщины' },
          { id: 'deep_wrinkles', label: 'Глубокие морщины' },
          { id: 'loss_of_firmness', label: 'Снижение упругости' },
          { id: 'skin_density_loss', label: 'Потеря плотности' },
          { id: 'loss_of_elasticity', label: 'Потеря эластичности' },
          { id: 'photoaging', label: 'Фотостарение' },
        ],
      },
    ],
  },
  {
    id: 'dullness', label: 'Тусклый тон', shortLabel: 'Тусклость',
    questions: [
      {
        id: 'dullness_type', label: 'Что именно?', type: 'multi',
        options: [
          { id: 'dullness', label: 'Тусклый цвет лица' },
          { id: 'lack_of_radiance', label: 'Недостаток сияния' },
          { id: 'uneven_color', label: 'Неровный цвет' },
        ],
      },
    ],
  },
]

// Терапия (раздел 41-44).
export const THERAPY_OPTIONS: QuestionOption[] = [
  { id: 'topical_retinoid', label: 'Ретиноиды' },
  { id: 'acid_therapy', label: 'Кислоты' },
  { id: 'azelaic_acid_therapy', label: 'Азелаиновая кислота' },
  { id: 'benzoyl_peroxide', label: 'Бензоилпероксид' },
  { id: 'antibiotic', label: 'Антибиотики' },
  { id: 'rosacea_topical_therapy', label: 'Средства от розацеа' },
]

export const RETINOID_OPTIONS: QuestionOption[] = [
  { id: 'adapalene', label: 'Адапален' },
  { id: 'tretinoin', label: 'Третиноин' },
  { id: 'tazarotene', label: 'Тазаротен' },
  { id: 'systemic_isotretinoin', label: 'Изотретиноин внутрь' },
  { id: 'topical_retinoid', label: 'Другой / не знаю' },
]

export const ACID_OPTIONS: QuestionOption[] = [
  { id: 'aha_therapy', label: 'AHA' },
  { id: 'bha_therapy', label: 'BHA' },
  { id: 'pha_therapy', label: 'PHA' },
]

export const PROCEDURE_OPTIONS: QuestionOption[] = [
  { id: 'recent_laser', label: 'Лазер' },
  { id: 'recent_ipl', label: 'IPL' },
  { id: 'recent_microneedling', label: 'Микронидлинг' },
  { id: 'recent_dermabrasion', label: 'Дермабразия' },
  { id: 'recent_rfa', label: 'RF / RFA' },
  { id: 'recent_invasive_procedure', label: 'Другая процедура' },
]

export const PROCEDURE_PERIODS: QuestionOption[] = [
  { id: '<7 days', label: 'Последние 7 дней' },
  { id: '7-14 days', label: '7–14 дней' },
  { id: '14-30 days', label: '14–30 дней' },
  { id: '1-3 months', label: '1–3 месяца' },
  { id: '>3 months', label: 'Более 3 месяцев' },
]

export const INTOLERANCE_OPTIONS: QuestionOption[] = [
  { id: 'fragrance_intolerance', label: 'Отдушки' },
  { id: 'alcohol_intolerance', label: 'Спирт' },
  { id: 'essential_oil_intolerance', label: 'Эфирные масла' },
  { id: 'retinoid_intolerance', label: 'Ретиноиды' },
  { id: 'acid_intolerance', label: 'Кислоты' },
  { id: 'niacinamide_intolerance', label: 'Ниацинамид' },
]

// ---------------------------------------------------------------------------
// Восстановление состояния анкеты из StructuredProfile (round-trip).
// ---------------------------------------------------------------------------
export type StructuredQuizState = {
  skinType: string | null
  selectedCards: string[]
  answers: Record<string, Record<string, string[]>>
  therapyEnabled: boolean | null
  therapyIds: string[]
  retinoid: string | null
  acids: string[]
  procedures: Record<string, string>
  intolerances: string[]
}

const RETINOID_ID_SET = new Set(RETINOID_OPTIONS.map(o => o.id))
const ACID_ID_SET = new Set(ACID_OPTIONS.map(o => o.id))

export function structuredToQuizState(s: StructuredProfile | null | undefined): StructuredQuizState {
  const state: StructuredQuizState = {
    skinType: s?.skin_type ?? null,
    selectedCards: [],
    answers: {},
    therapyEnabled: null,
    therapyIds: [],
    retinoid: null,
    acids: [],
    procedures: {},
    intolerances: [],
  }
  if (!s) return state

  const concerns = new Set<string>(s.concerns ?? [])

  for (const branch of CONCERN_CARDS) {
    let active = concerns.has(branch.id)
    const branchAnswers: Record<string, string[]> = {}
    for (const q of branch.questions) {
      const selected = q.options.filter(o => concerns.has(o.id)).map(o => o.id)
      if (selected.length) {
        branchAnswers[q.id] = selected
        active = true
      }
    }
    if (active) state.selectedCards.push(branch.id)
    if (Object.keys(branchAnswers).length) state.answers[branch.id] = branchAnswers
  }

  for (const t of s.therapy ?? []) {
    if (RETINOID_ID_SET.has(t.id)) {
      if (!state.therapyIds.includes('topical_retinoid')) state.therapyIds.push('topical_retinoid')
      state.retinoid = t.id
    } else if (ACID_ID_SET.has(t.id)) {
      if (!state.therapyIds.includes('acid_therapy')) state.therapyIds.push('acid_therapy')
      if (!state.acids.includes(t.id)) state.acids.push(t.id)
    } else if (!state.therapyIds.includes(t.id)) {
      state.therapyIds.push(t.id)
    }
  }
  if (state.therapyIds.length) state.therapyEnabled = true

  for (const pr of s.procedures ?? []) {
    if (pr?.id) state.procedures[pr.id] = pr.period ?? '<7 days'
  }

  for (const it of s.intolerances ?? []) {
    if (typeof it === 'string' && !state.intolerances.includes(it)) state.intolerances.push(it)
  }

  return state
}
