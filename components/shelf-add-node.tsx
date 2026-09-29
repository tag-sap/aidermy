'use client'

import { X } from 'lucide-react'

type Category = { key: string; title: string }

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
    <>
      {/* Затемнение-подложка (клик закрывает) */}
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} aria-hidden />

      {/* Панель выбора категории */}
      <div className="fixed left-1/2 top-1/2 z-50 w-[320px] max-w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-gray-200 bg-white p-4 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-medium text-foreground">Категория</span>
          <button
            onClick={onClose}
            className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm transition-transform hover:scale-105"
            aria-label="Закрыть"
          >
            <X className="size-3.5" />
          </button>
        </div>

        <div className="grid max-h-[60vh] grid-cols-2 gap-2 overflow-y-auto pr-1">
          {categories.map((cat) => (
            <button
              key={cat.key}
              onClick={() => onPick(cat)}
              className="rounded-lg border border-gray-200 bg-white px-2.5 py-2 text-left text-[12px] leading-tight text-foreground/80 transition-colors hover:border-primary/40 hover:bg-gray-50 hover:text-primary"
            >
              {cat.title}
            </button>
          ))}
        </div>
      </div>
    </>
  )
}
