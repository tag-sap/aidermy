'use client'

import { Check, Trash2 } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import type { CheckResult } from '@/lib/store'
import { cn } from '@/lib/utils'
import { useState, useEffect } from 'react'
import { useScrollLock } from '@/lib/use-scroll-lock'

function formatDate(ts: number) {
  if (!ts || ts === 0 || isNaN(ts)) {
    return 'Дата неизвестна'
  }
  try {
    const date = new Date(ts)
    if (isNaN(date.getTime())) {
      return 'Дата неизвестна'
    }
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return 'Дата неизвестна'
  }
}

export function HistoryTab({
  history,
  onClear,
  onSelect,
  onDeleteItem,
  onDeleteSelected,
}: {
  history: CheckResult[]
  onClear: () => void
  onSelect: (item: CheckResult) => void
  onDeleteItem: (id: string) => void
  onDeleteSelected: (ids: string[]) => void
}) {
  const [isVisible, setIsVisible] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [removingIds, setRemovingIds] = useState<string[]>([])
  const [pendingDeleteIds, setPendingDeleteIds] = useState<string[]>([])

  useScrollLock(pendingDeleteIds.length > 0)

  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), 50)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    setSelectedIds((prev) => prev.filter((id) => history.some((item) => item.id === id)))
  }, [history])

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((itemId) => itemId !== id) : [...prev, id]
    )
  }

  const isAllSelected = history.length > 0 && selectedIds.length === history.length

  const confirmDelete = (ids: string[]) => {
    setPendingDeleteIds(ids)
  }

  const executeDelete = (ids: string[]) => {
    if (!ids.length) return

    ids.forEach((id) => setRemovingIds((prev) => [...prev, id]))
    setTimeout(() => {
      if (ids.length === 1) {
        onDeleteItem(ids[0])
      } else {
        onDeleteSelected(ids)
      }
      setSelectedIds((prev) => prev.filter((idValue) => !ids.includes(idValue)))
      setRemovingIds((prev) => prev.filter((idValue) => !ids.includes(idValue)))
      setPendingDeleteIds([])
    }, 220)
  }

  const cardStyle = "relative overflow-hidden bg-gradient-to-br from-primary/10 via-primary/5 to-transparent rounded-2xl p-5 border border-primary/20 backdrop-blur-sm hover:shadow-md transition-shadow"

  return (
    <div className="flex flex-col gap-5 max-w-md md:max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-end gap-3">
        {history.length > 0 && (
          <div className="flex items-center gap-2">
            {selectedIds.length > 0 && (
              <button
                type="button"
                onClick={() => confirmDelete(selectedIds)}
                className="flex items-center gap-1 text-xs text-red-500 transition-colors hover:text-red-600"
              >
                <Trash2 className="size-3.5" />
                Удалить ({selectedIds.length})
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                if (isAllSelected) {
                  setSelectedIds([])
                } else {
                  setSelectedIds(history.map((item) => item.id))
                }
              }}
              className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-primary"
            >
              <Check className="size-3.5" />
              {isAllSelected ? 'Снять всё' : 'Выделить всё'}
            </button>
            <button
              type="button"
              onClick={onClear}
              aria-label="Очистить историю"
              className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-red-500"
            >
              <Trash2 className="size-4" />
              Очистить
            </button>
          </div>
        )}
      </div>

      {history.length === 0 ? (
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-1')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative text-center py-8">
            <p className="text-sm text-muted-foreground">
              Пока нет проверок. Здесь появятся результаты анализа ваших средств.
            </p>
          </div>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {history.map((item, index) => {
            const isSelected = selectedIds.includes(item.id)
            const isRemoving = removingIds.includes(item.id)

            return (
              <li
                key={item.id}
                onClick={() => onSelect(item)}
                className={cn(
                  cardStyle,
                  'cursor-pointer transition-all hover:shadow-lg active:scale-[0.98]',
                  'card-enter',
                  isVisible && `card-enter-${Math.min(index + 1, 6)}`,
                  isSelected && 'ring-2 ring-primary/60 border-primary/40',
                  isRemoving && 'pointer-events-none opacity-0 scale-[0.98] -translate-y-1'
                )}
                style={{
                  animationDelay: `${index * 0.08}s`,
                  transition: 'opacity 220ms ease, transform 220ms ease, filter 220ms ease',
                }}
              >
                <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
                <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
                <div className="relative flex items-start justify-between gap-3">
                  <button
                    type="button"
                    aria-label={isSelected ? 'Снять выделение' : 'Выделить запись'}
                    onClick={(event) => {
                      event.stopPropagation()
                      toggleSelect(item.id)
                    }}
                    className={cn(
                      'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded border transition-colors',
                      isSelected
                        ? 'border-primary bg-primary text-white'
                        : 'border-primary/40 bg-white/50 text-transparent hover:border-primary/80'
                    )}
                  >
                    {isSelected && <Check className="size-3.5" />}
                  </button>

                  {item.image_url ? (
                    <div className="mt-0.5 size-10 shrink-0 overflow-hidden rounded-lg border border-white/30 bg-white/40">
                      <img src={item.image_url} alt={item.product} className="h-full w-full object-contain p-0.5" />
                    </div>
                  ) : null}

                  <div className="min-w-0 flex-1 overflow-hidden">
                    {item.product.length > 24 ? (
                      <div className="history-marquee-wrap">
                        <div className="history-marquee-track">
                          <span>{item.product}</span>
                          <span>{item.product}</span>
                        </div>
                      </div>
                    ) : (
                      <ScrambleText
                        as="p"
                        text={item.product}
                        revealDelay={30}
                        className="block font-normal text-foreground text-sm whitespace-nowrap"
                      />
                    )}
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {item.skinType} · {formatDate(item.createdAt)}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">{item.verdict}</p>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <div className="text-right">
                      <span className="text-2xl font-normal text-primary">{item.score}%</span>
                    </div>
                    <button
                      type="button"
                      aria-label="Удалить запись"
                      onClick={(event) => {
                        event.stopPropagation()
                        confirmDelete([item.id])
                      }}
                      className="rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-500"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {pendingDeleteIds.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 backdrop-blur-sm px-4 animate-modal-backdrop">
          <div className="w-full max-w-sm rounded-2xl border border-primary/20 bg-white p-5 shadow-xl animate-modal-panel">
            <div className="mb-3 flex items-center gap-2">
              <div className="flex size-9 items-center justify-center rounded-full bg-red-500/10 text-red-500">
                <Trash2 className="size-4" />
              </div>
              <div>
                <p className="text-base font-medium text-foreground">Удалить запись?</p>
                <p className="text-xs text-muted-foreground">
                  {pendingDeleteIds.length > 1 ? `Вы удаляете ${pendingDeleteIds.length} элементов` : 'Это действие нельзя отменить'}
                </p>
              </div>
            </div>

            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={() => setPendingDeleteIds([])}
                className="flex-1 rounded-xl border border-primary/20 bg-white px-3 py-2 text-sm text-foreground transition-colors hover:bg-primary/5"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={() => {
                  executeDelete(pendingDeleteIds)
                }}
                className="flex-1 rounded-xl bg-red-500 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-red-600"
              >
                Удалить
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}