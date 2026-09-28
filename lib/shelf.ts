// lib/shelf.ts — UI-метаданные «Моей полки» (шкафы и категории).
// Зеркалит структуру CABINETS на бэкенде (backend/app/shelf_service.py),
// используется только для отображения и выбора категорий на клиенте.

export type CabinetKey = 'face' | 'hair' | 'body' | 'makeup' | 'fragrance'

export type CabinetMeta = {
  key: CabinetKey
  title: string
  hasScoring: boolean
  categories: string[]
}

export const CABINET_META: CabinetMeta[] = [
  { key: 'face', title: 'Уход для лица', hasScoring: true, categories: ['Для кожи вокруг глаз', 'Уход для губ', 'Очищение и демакияж', 'Тонизирование', 'Сыворотки', 'Маски', 'Патчи', 'Пэды', 'Скрабы и пилинги', 'Кремы', 'Увлажнение и питание', 'Специальный уход', 'Антивозрастной уход'] },
  { key: 'body', title: 'Уход для тела', hasScoring: true, categories: ['Основной уход', 'Для душа и ванны', 'Для рук', 'Для ног', 'Кремы для тела', 'Скрабы и пилинги', 'Корректирующие средства', 'Дезодоранты', 'Масла для тела', 'Депиляция и эпиляция', 'Мыло', 'Мочалки и губки', 'Массажёры и щётки'] },
  { key: 'hair', title: 'Волосы', hasScoring: true, categories: ['Шампуни', 'Бальзамы и кондиционеры', 'Сухие шампуни', 'Маски', 'Скрабы', 'Масла'] },
  { key: 'makeup', title: 'Макияж', hasScoring: false, categories: ['Тональные средства', 'Консилеры', 'Пудры', 'Румяна', 'Тушь', 'Помады', 'Для глаз'] },
  { key: 'fragrance', title: 'Парфюмерия', hasScoring: false, categories: ['Парфюм', 'Парфюмерная вода', 'Туалетная вода'] },
]

export const CABINET_TITLES: Record<string, string> = Object.fromEntries(
  CABINET_META.map((c) => [c.key, c.title] as const),
)

export type ShelfItem = {
  id: number
  shelf_id: number
  product_id: number
  cabinet: string
  category: string
  added_at: string
  name: string
  brand: string
  image_url: string
  slug: string
  ingredients: string
  score: number | null
  has_report?: boolean
  needs_recheck?: boolean
  rating?: number | null
  rating_count?: number
}
