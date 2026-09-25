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
  { key: 'face', title: 'Лицо', hasScoring: true, categories: ['Очищение', 'Тонизация', 'Сыворотки', 'Увлажнение', 'SPF', 'Маски'] },
  { key: 'hair', title: 'Волосы', hasScoring: true, categories: ['Шампуни', 'Кондиционеры', 'Маски', 'Несмываемый уход', 'Стайлинг'] },
  { key: 'body', title: 'Тело', hasScoring: true, categories: ['Гели для душа', 'Кремы / лосьоны', 'Скрабы', 'Дезодоранты'] },
  { key: 'makeup', title: 'Макияж', hasScoring: false, categories: ['Тональные средства', 'Консилеры', 'Пудры', 'Румяна', 'Тушь', 'Помады'] },
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
