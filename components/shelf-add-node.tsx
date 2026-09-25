'use client'

import { X } from 'lucide-react'

type Category = { key: string; title: string }

// Полукруг справа от центральной точки (кнопки «Добавить»).
// Центр overlay 300×260 → (150, 130); облачка выстраиваются дугой вправо.
const ARC_RADIUS = 118

function arcPosition(index: number, total: number): { x: number; y: number } {
  if (total <= 1) return { x: 265, y: 130 }
  // Угол от -80° (верх) до +80° (низ) — дуга, повёрнутая по часовой стрелке на 90°,
  // чтобы раскрытие смотрело вправо (раньше — вверх).
  const angleDeg = total === 1 ? 0 : -80 + (160 * index) / (total - 1)
  const rad = (angleDeg * Math.PI) / 180
  const x = 150 + ARC_RADIUS * Math.cos(rad) + 14
  const y = 130 + ARC_RADIUS * Math.sin(rad)
  return { x, y }
}

export function ShelfAddNode({
  categories,
  onPick,
  onClose,
}: {
  categories: Category[]
  onPick: (cat: Category) => void
  onClose: () => void
}) {
  return (
    <div
      className="absolute left-1/2 top-1/2 z-30 -translate-x-1/2 -translate-y-1/2"
      style={{ width: 300, height: 260 }}
    >
      <button
        onClick={onClose}
        className="animate-shelf-dot absolute left-1/2 top-1/2 z-10 flex size-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
        aria-label="Закрыть"
      >
        <X className="size-3.5" />
      </button>

      {categories.map((cat, i) => {
        const pos = arcPosition(i, categories.length)
        return (
          <button
            key={cat.key}
            onClick={() => onPick(cat)}
            className="animate-shelf-cloud absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border border-gray-200 bg-white px-3 py-1.5 text-[11px] text-foreground/70 shadow-sm transition-colors hover:border-primary/40 hover:text-primary"
            style={{ left: pos.x, top: pos.y, animationDelay: `${i * 40}ms` }}
          >
            {cat.title}
          </button>
        )
      })}
    </div>
  )
}
