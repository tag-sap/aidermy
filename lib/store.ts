// lib/store.ts

export type SkinProfile = {
  name?: string
  skinType: string
  age: string
  concerns: string[]
  allergies: string[]
  customText?: string
  // Новые поля для опросника
  quizAnswers?: Record<string, string>  // Ответы на опросник
  skinTypeDetermined?: string           // Определенный тип кожи
}

export type CheckResult = {
  id: string
  product: string
  skinType: string
  score: number
  verdict: string
  summary: string
  safe_ingredients?: string[]
  caution_ingredients?: string[]
  stats?: Record<string, number>
  skin_type_recommendation?: string
  slug?: string
  image_url?: string
  createdAt: number
}

const PROFILE_KEY = 'aidermy:profile'
const HISTORY_KEY = 'aidermy:history'

export const emptyProfile: SkinProfile = {
  name: '',
  skinType: '',
  age: '',
  concerns: [],
  allergies: [],
  customText: '',
  quizAnswers: {},
  skinTypeDetermined: '',
}

export function loadProfile(): SkinProfile {
  if (typeof window === 'undefined') return emptyProfile
  try {
    const raw = window.localStorage.getItem(PROFILE_KEY)
    if (!raw) return emptyProfile
    const parsed = JSON.parse(raw)
    // Совместимость со старыми версиями
    return { ...emptyProfile, ...parsed }
  } catch {
    return emptyProfile
  }
}

export function saveProfile(profile: SkinProfile) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
}

export function loadHistory(): CheckResult[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    return JSON.parse(raw) as CheckResult[]
  } catch {
    return []
  }
}

export function saveHistory(history: CheckResult[]) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history))
}

export function isProfileComplete(p: SkinProfile): boolean {
  // Проверяем: заполнен ли тип кожи ИЛИ пройден ли опросник
  return Boolean(p.skinType || (p.quizAnswers && Object.keys(p.quizAnswers).length > 0))
}

// Функция для определения типа кожи из ответов опросника
export function determineSkinTypeFromAnswers(answers: Record<string, string>): string {
  const feel = answers.feel_after_wash || ''
  const reaction = answers.skin_reaction || ''
  const moisture = answers.moisture_level || ''
  const pores = answers.pores || ''

  if (feel === 'tight' && moisture === 'always') return 'Сухая'
  if (feel === 'oily' && moisture === 'oily') return 'Жирная'
  if (feel === 'mixed' && moisture === 'sometimes') return 'Комбинированная'
  if (reaction === 'sensitive') return 'Чувствительная'
  if (feel === 'normal' && moisture === 'rarely') return 'Нормальная'
  if (feel === 'tight' && reaction === 'sensitive') return 'Сухая чувствительная'
  if (feel === 'oily' && pores === 'large') return 'Жирная с расширенными порами'
  
  return 'Нормальная'
}

// Мок-функция для проверки (оставляем для совместимости)
export function mockCheck(product: string, skinType: string): CheckResult {
  const score = Math.floor(Math.random() * 61) + 40
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    product,
    skinType,
    score,
    verdict: score >= 70 ? 'Отличный выбор' : score >= 40 ? 'Подходит с оговорками' : 'Лучше поискать альтернативу',
    summary: 'Анализ продукта на основе вашего профиля...',
    safe_ingredients: [],
    caution_ingredients: [],
    stats: {},
    skin_type_recommendation: '',
    slug: undefined,
    createdAt: Date.now(),
  }
}