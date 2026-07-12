export type SkinProfile = {
  name?: string
  skinType: string
  age: string
  concerns: string[]
  allergies: string[]
  customText?: string
}

export type CheckResult = {
  id: string
  product: string
  skinType: string
  score: number
  verdict: string
  summary: string
  safe_ingredients?: string[]   // ← добавил
  caution_ingredients?: string[] // ← добавил
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
}

export function loadProfile(): SkinProfile {
  if (typeof window === 'undefined') return emptyProfile
  try {
    const raw = window.localStorage.getItem(PROFILE_KEY)
    if (!raw) return emptyProfile
    return { ...emptyProfile, ...(JSON.parse(raw) as SkinProfile) }
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
  return Boolean(p.skinType && p.age)
}

const VERDICTS: { min: number; verdict: string; summary: string }[] = [
  {
    min: 85,
    verdict: 'Отличный выбор',
    summary:
      'Средство хорошо подходит под твой профиль кожи. Состав сбалансирован, риск раздражения минимален.',
  },
  {
    min: 65,
    verdict: 'Подходит с оговорками',
    summary:
      'В целом совместимо с твоей кожей, но следи за реакцией в первые дни использования.',
  },
  {
    min: 45,
    verdict: 'Нейтрально',
    summary:
      'Средство не идеально под твой тип кожи. Возможен подбор более точной альтернативы.',
  },
  {
    min: 0,
    verdict: 'Лучше поискать альтернативу',
    summary:
      'Состав может конфликтовать с твоими особенностями кожи. Рекомендуем проконсультироваться.',
  },
]

export function mockCheck(product: string, skinType: string): CheckResult {
  const score = Math.floor(Math.random() * 61) + 40 // 40–100
  const match = VERDICTS.find((v) => score >= v.min) ?? VERDICTS[VERDICTS.length - 1]
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    product,
    skinType,
    score,
    verdict: match.verdict,
    summary: match.summary,
    safe_ingredients: [],
    caution_ingredients: [],
    createdAt: Date.now(),
  }
}