'use client'

import { useLayoutEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

type Category = { key: string; title: string }

// Позиции облачков вокруг центральной точки (внутри overlay 300×260, центр 150/130).
// Вся композиция раскрывается вправо/вверх/вниз — слева облачков нет.
const CLOUD_POS = [
  { x: 150, y: 16 },   // верх
  { x: 225, y: 46 },   // верх-право
  { x: 268, y: 95 },   // право-верх
  { x: 268, y: 165 },  // право-низ
  { x: 225, y: 214 },  // низ-право
  { x: 150, y: 244 },  // низ
]

type Line = { x1: number; y1: number; x2: number; y2: number }

export function ShelfAddNode({
  categories,
  onPick,
  onClose,
}: {
  categories: Category[]
  onPick: (cat: Category) => void
  onClose: () => void
}) {
  const rootRef = useRef<HTMLDivElement>(null)
  const dotRef = useRef<HTMLButtonElement>(null)
  const cloudRefs = useRef<(HTMLButtonElement | null)[]>([])
  const [lines, setLines] = useState<Line[]>([])

  useLayoutEffect(() => {
    const compute = () => {
      const root = rootRef.current
      if (!root) return
      const cx = root.offsetWidth / 2
      const cy = root.offsetHeight / 2
      const next: Line[] = []
      cloudRefs.current.forEach((cloud, i) => {
        const pos = CLOUD_POS[i % CLOUD_POS.length]
        if (!cloud || !pos) return
        // Реальные размеры облачка (layout-бокс, без transform).
        const halfW = cloud.offsetWidth / 2
        const halfH = cloud.offsetHeight / 2
        const dx = pos.x - cx
        const dy = pos.y - cy
        const len = Math.hypot(dx, dy) || 1
        const ux = dx / len
        const uy = dy / len
        // Пересечение луча (центр -> облачко) с границей облачка.
        const tx = ux !== 0 ? halfW / Math.abs(ux) : Infinity
        const ty = uy !== 0 ? halfH / Math.abs(uy) : Infinity
        const t = Math.min(tx, ty)
        next.push({ x1: cx, y1: cy, x2: cx + ux * t, y2: cy + uy * t })
      })
      setLines(next)
    }
    compute()
    const ro = new ResizeObserver(compute)
    cloudRefs.current.forEach((c) => c && ro.observe(c))
    window.addEventListener('resize', compute)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', compute)
    }
  }, [])

  return (
    <div
      ref={rootRef}
      className="absolute left-1/2 top-1/2 z-30 -translate-x-1/2 -translate-y-1/2"
      style={{ width: 300, height: 260 }}
    >
      <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
        {lines.map((l, i) => (
          <line
            key={i}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke="rgba(21, 21, 21, 0.2)"
            strokeWidth="1"
            strokeDasharray="3 3"
            className="animate-shelf-line"
            style={{ animationDelay: `${i * 40}ms` }}
          />
        ))}
      </svg>

      <button
        ref={dotRef}
        onClick={onClose}
        className="animate-shelf-dot absolute left-1/2 top-1/2 z-10 flex size-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
        aria-label="Закрыть"
      >
        <X className="size-3.5" />
      </button>

      {categories.map((cat, i) => {
        const pos = CLOUD_POS[i % CLOUD_POS.length]
        return (
          <button
            key={cat.key}
            ref={(el) => {
              cloudRefs.current[i] = el
            }}
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
