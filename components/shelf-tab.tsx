'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Plus, LoaderCircle, Sparkles, X, Check, ListChecks } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ShelfItem } from '@/lib/shelf'
import type { CheckResult } from '@/lib/store'
import { ShelfAddModal } from '@/components/shelf-add-modal'
import { ProductModal } from '@/components/product-modal'
import { useScrollLock } from '@/lib/use-scroll-lock'

type Category = { key: string; title: string; items: ShelfItem[]; compatibility?: number | null }
type Cabinet = {
  key: string
  title: string
  has_scoring: boolean
  compatibility: number | null
  categories: Category[]
}

type ConfirmState = { title: string; message: string; confirmLabel?: string; onConfirm: () => void }

function scoreBadge(s: number | null) {
  if (s == null) return ''
  if (s >= 80) return 'bg-[#F5C900]/25 text-[#7A5E00]'
  if (s >= 60) return 'bg-[#F5C900]/15 text-[#7A5E00]'
  if (s >= 40) return 'bg-[#8B5CF6]/10 text-[#6D28D9]'
  return 'bg-[#FF4D3D]/10 text-[#D63B2E]'
}

// --- Динамическая полка: ширина считается от количества товаров. ---
// Левый/правый торец — фиксированные, центр растягивается/сжимается.
const SHELF_CARD_W = 130 // ширина карточки (совпадает с w-[130px])
const SHELF_GAP = 10 // gap-2.5 между карточками
const SHELF_EDGE = 16 // ширина фиксированного торца
const SHELF_PAD = 16 // внутренний отступ под карточки (px-4)
const SHELF_MIN = 280 // полка не должна быть слишком маленькой
const SHELF_MAX = 720 // и не должна быть огромной (на широких экранах)

function shelfWidth(count: number) {
  const content = count * SHELF_CARD_W + Math.max(0, count - 1) * SHELF_GAP
  const desired = SHELF_EDGE * 2 + SHELF_PAD * 2 + content
  return Math.max(SHELF_MIN, Math.min(desired, SHELF_MAX))
}

function shelfOverflows(count: number) {
  const content = count * SHELF_CARD_W + Math.max(0, count - 1) * SHELF_GAP
  const desired = SHELF_EDGE * 2 + SHELF_PAD * 2 + content
  return desired > SHELF_MAX
}

export function ShelfTab({
  onOpenReport,
  onOpenBrand,
  onOpenCategory,
}: {
  onOpenReport?: (result: CheckResult) => void
  onOpenBrand?: (brand: string) => void
  onOpenCategory?: (category: string) => void
}) {
  const [cabinets, setCabinets] = useState<Cabinet[]>([])
  const [loading, setLoading] = useState(true)
  const [activeCabinet, setActiveCabinet] = useState('face')
  const [selectionMode, setSelectionMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [addContext, setAddContext] = useState<{ cabinet: string; category: string } | null>(null)
  const [detailSlug, setDetailSlug] = useState<string | null>(null)
  const [detailContext, setDetailContext] = useState<{ cabinet: string; category: string } | null>(null)
  const [confirm, setConfirm] = useState<ConfirmState | null>(null)
  const [busy, setBusy] = useState(false)
  const [removalTarget, setRemovalTarget] = useState<ShelfItem | null>(null)
  const [removalReason, setRemovalReason] = useState('')
  const [removalNote, setRemovalNote] = useState('')
  const [removing, setRemoving] = useState(false)

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  useScrollLock(!!confirm)

  const fetchShelf = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = await fetch('/api/shelf', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const data = await res.json()
        setCabinets(data.cabinets || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [token])

  const loadShelf = useCallback(() => fetchShelf(false), [fetchShelf])
  const refreshShelf = useCallback(() => fetchShelf(true), [fetchShelf])

  useEffect(() => {
    loadShelf()
  }, [loadShelf])

  const currentCabinet = cabinets.find((c) => c.key === activeCabinet) || null

  const currentItems = useMemo(() => {
    if (!currentCabinet) return []
    return currentCabinet.categories.flatMap((c) => c.items)
  }, [currentCabinet])

  const exitSelection = () => {
    setSelectionMode(false)
    setSelected(new Set())
  }

  const switchCabinet = (key: string) => {
    setActiveCabinet(key)
    exitSelection()
  }

  const deleteIds = async (ids: number[]) => {
    setBusy(true)
    try {
      const res = await fetch('/api/shelf/delete-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ids }),
      })
      if (!res.ok) throw new Error('Не удалось удалить')
      setSelected(new Set())
      await refreshShelf()
    } catch (e) {
      console.error(e)
    } finally {
      setBusy(false)
    }
  }

  const submitRemoval = async () => {
    if (!removalTarget || !removalReason || removing) return
    setRemoving(true)
    try {
      // Сохраняем причину (для истории предпочтений), затем удаляем.
      await fetch('/api/shelf/removal-feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug: removalTarget.slug, reason: removalReason, note: removalNote }),
      }).catch(() => {})
      await deleteIds([removalTarget.id])
    } finally {
      setRemoving(false)
      setRemovalTarget(null)
      setRemovalReason('')
      setRemovalNote('')
    }
  }

  const clearShelf = async (cabinet: string, category: string) => {
    setBusy(true)
    try {
      const res = await fetch('/api/shelf/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ cabinet, category }),
      })
      if (!res.ok) throw new Error('Не удалось очистить')
      setSelected(new Set())
      await refreshShelf()
    } catch (e) {
      console.error(e)
    } finally {
      setBusy(false)
    }
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const openDetail = (slug: string, cabinet: string, category: string) => {
    setDetailContext({ cabinet, category })
    setDetailSlug(slug)
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoaderCircle className="size-6 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="px-1 py-2 pb-28" data-tour="shelves">
      <div className="mb-4 flex items-center justify-end">
        <button
          onClick={() => (selectionMode ? exitSelection() : setSelectionMode(true))}
          className={cn(
            'flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors',
            selectionMode ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-200 text-muted-foreground/70 hover:border-primary/40 hover:text-primary',
          )}
        >
          <ListChecks className="size-3.5" />
          {selectionMode ? 'Готово' : 'Управление'}
        </button>
      </div>

      <div className="no-scrollbar -mx-1 mb-4 flex gap-1.5 overflow-x-auto border-b border-gray-200/60 px-1">
        {cabinets.map((cab) => (
          <button
            key={cab.key}
            onClick={() => switchCabinet(cab.key)}
            className={cn(
              'shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors',
              activeCabinet === cab.key
                ? 'border-primary font-medium text-primary'
                : 'border-transparent text-muted-foreground/60 hover:text-foreground',
            )}
          >
            {cab.title}
          </button>
        ))}
      </div>

      {selectionMode && (
        <div className="sticky top-0 z-10 mb-4 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-primary/20 bg-white/90 p-3 shadow-sm backdrop-blur">
          <span className="text-sm text-foreground/80">Выбрано: {selected.size}</span>
          <div className="flex items-center gap-1.5">
            <button onClick={() => setSelected(new Set(currentItems.map((i) => i.id)))} className="rounded-full px-2.5 py-1 text-xs text-primary hover:bg-primary/5">
              Выбрать всё
            </button>
            <button onClick={() => setSelected(new Set())} className="rounded-full px-2.5 py-1 text-xs text-muted-foreground/70 hover:bg-gray-50">
              Снять
            </button>
            <button
              onClick={() => setConfirm({ title: 'Удалить выбранные продукты?', message: `Выбрано продуктов: ${selected.size}. Они будут убраны с полки.`, onConfirm: () => deleteIds(Array.from(selected)) })}
              disabled={selected.size === 0 || busy}
              className="rounded-full bg-red-500 px-3 py-1 text-xs text-white transition-colors hover:bg-red-600 disabled:opacity-40"
            >
              Удалить
            </button>
          </div>
        </div>
      )}

      {currentCabinet && (
        <section key={activeCabinet} className="tab-content">
          <div className="mb-3 flex items-end justify-between gap-3">
            <h2 className="text-xl font-light text-foreground/90">{currentCabinet.title}</h2>
            <div className="flex items-center gap-3">
              {currentItems.length > 0 && (
                <button
                  onClick={() => setConfirm({ title: `Очистить шкаф «${currentCabinet.title}»?`, message: 'Удалить все продукты из этого шкафа?', confirmLabel: 'Очистить', onConfirm: () => clearShelf(currentCabinet.key, '') })}
                  className="text-[11px] text-muted-foreground/50 transition-colors hover:text-red-500"
                >
                  Очистить шкаф
                </button>
              )}
              {currentCabinet.has_scoring && (
                <div className="text-right">
                  <p className="text-[9px] uppercase tracking-wide text-muted-foreground/50">Совместимость ухода</p>
                  <p className={cn('text-lg font-light', currentCabinet.compatibility != null ? 'text-primary' : 'text-muted-foreground/40')}>
                    {currentCabinet.compatibility != null ? `${currentCabinet.compatibility}%` : '—'}
                  </p>
                </div>
              )}
            </div>
          </div>

          {currentItems.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-gray-200/70 px-4 py-10 text-center">
              <Sparkles className="mx-auto mb-3 size-7 text-muted-foreground/30" />
              <p className="text-sm text-foreground/70">Ваш шкаф пока пуст</p>
              <p className="mt-1 text-xs text-muted-foreground/50">Соберите здесь свой уход.</p>
              <p className="mt-6 mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground/50">С чего начнём?</p>
              <div className="flex flex-wrap justify-center gap-2">
                {currentCabinet.categories.map((cat) => (
                  <button
                    key={cat.key}
                    onClick={() => setAddContext({ cabinet: currentCabinet.key, category: cat.key })}
                    className="rounded-full border border-gray-200 px-3.5 py-1.5 text-xs text-foreground/70 transition-colors hover:border-primary/40 hover:text-primary"
                  >
                    {cat.title}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {currentCabinet.categories.map((cat) => (
                <div key={cat.key}>
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground/60">{cat.title}</h3>
                      {currentCabinet.has_scoring && cat.compatibility != null && (
                        <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] text-primary">{cat.compatibility}%</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {cat.items.length > 0 && (
                        <button
                          onClick={() => setConfirm({ title: `Очистить «${cat.title}»?`, message: 'Удалить все продукты из этой категории?', confirmLabel: 'Очистить', onConfirm: () => clearShelf(currentCabinet.key, cat.key) })}
                          className="text-[10px] text-muted-foreground/40 transition-colors hover:text-red-500"
                        >
                          Очистить
                        </button>
                      )}
                      <button
                        onClick={() => setAddContext({ cabinet: currentCabinet.key, category: cat.key })}
                        className="flex size-6 items-center justify-center rounded-full border border-gray-200 text-muted-foreground/60 transition-colors hover:border-primary/40 hover:text-primary"
                        aria-label={`Добавить в ${cat.title}`}
                      >
                        <Plus className="size-3.5" />
                      </button>
                    </div>
                  </div>

                  {cat.items.length === 0 ? (
                    <button
                      onClick={() => setAddContext({ cabinet: currentCabinet.key, category: cat.key })}
                      className="flex w-full flex-col items-center gap-1.5 rounded-2xl border border-dashed border-gray-200/70 py-6 text-center transition-colors hover:border-primary/30"
                    >
                      <span className="text-xs text-foreground/60">Здесь пока ничего нет</span>
                      <span className="text-[10px] text-muted-foreground/40">Добавьте продукт из базы, по ссылке или подберите автоматически</span>
                      <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-[11px] text-primary">
                        <Plus className="size-3" /> Добавить продукт
                      </span>
                    </button>
                  ) : (
                    <div
                      className="relative mx-auto max-w-full"
                      style={{
                        width: shelfWidth(cat.items.length),
                        transition: 'width 0.55s cubic-bezier(0.16, 1, 0.3, 1)',
                      }}
                    >
                      {/* Карточки — отдельные UI-элементы, лежат поверх полки */}
                      <div className={cn(
                        'no-scrollbar relative z-10 flex gap-2.5 overflow-x-auto px-4 pb-[14px] pt-1',
                        shelfOverflows(cat.items.length) ? 'justify-start' : 'justify-center',
                      )}>
                        {cat.items.map((item, idx) => {
                          const isSelected = selected.has(item.id)
                          return (
                            <div key={item.id} className="animate-shelf-card group relative w-[130px] shrink-0" style={{ animationDelay: `${idx * 35}ms` }}>
                              <button
                                onClick={() => (selectionMode ? toggleSelect(item.id) : openDetail(item.slug, item.cabinet, item.category))}
                                className={cn(
                                  'w-full overflow-hidden rounded-2xl border text-left transition-all',
                                  selectionMode && isSelected
                                    ? 'border-primary/70 bg-primary/5 ring-2 ring-primary/20'
                                    : 'border-white/40 bg-white/60',
                                  !selectionMode && 'hover:-translate-y-0.5',
                                )}
                              >
                                <div className="flex h-[110px] items-center justify-center bg-gray-50/60 p-2">
                                  {item.image_url ? (
                                    <img src={item.image_url} alt="" className="h-full w-full object-contain" />
                                  ) : (
                                    <Sparkles className="size-5 text-muted-foreground/30" />
                                  )}
                                </div>
                                <div className="p-2">
                                  {item.brand && <p className="truncate text-[9px] uppercase tracking-wide text-muted-foreground/40">{item.brand}</p>}
                                  <p className="line-clamp-2 text-[11px] font-medium leading-tight text-foreground/80">{item.name}</p>
                                  {currentCabinet.has_scoring &&
                                    (item.score != null ? (
                                      <span className={cn('mt-1.5 inline-block rounded-full px-1.5 py-0.5 text-[10px] font-medium', scoreBadge(item.score))}>
                                        {item.score}%
                                      </span>
                                    ) : (
                                      <span className="mt-1.5 inline-block rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] text-muted-foreground/50">
                                        Не проверен
                                      </span>
                                    ))}
                                </div>
                              </button>

                              {selectionMode && (
                                <span
                                  className={cn(
                                    'absolute left-1.5 top-1.5 flex size-5 items-center justify-center rounded-full border bg-white/95 transition-colors',
                                    isSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-300 text-transparent',
                                  )}
                                >
                                  <Check className="size-3" strokeWidth={3} />
                                </span>
                              )}

                              {!selectionMode && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setRemovalTarget(item); setRemovalReason(''); setRemovalNote('')
                                  }}
                                  className="absolute right-1.5 top-1.5 flex size-6 items-center justify-center rounded-full border border-gray-200/60 bg-white/80 text-muted-foreground/50 opacity-0 transition-opacity group-hover:opacity-100 hover:text-red-500"
                                  aria-label="Удалить продукт"
                                >
                                  <X className="size-3.5" />
                                </button>
                              )}
                            </div>
                          )
                        })}
                      </div>

                      {/* Полка: [ левый торец ][ центр — динамическая ширина ][ правый торец ] */}
                      <div className="shelf-plank pointer-events-none absolute inset-x-0 bottom-0 flex h-[14px] rounded-full">
                        <div className="shelf-surface rounded-l-full" style={{ width: SHELF_EDGE }} />
                        <div className="shelf-surface flex-1" />
                        <div className="shelf-surface rounded-r-full" style={{ width: SHELF_EDGE }} />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {addContext && (
        <ShelfAddModal
          cabinet={addContext.cabinet}
          category={addContext.category}
          onClose={() => setAddContext(null)}
          onAdded={refreshShelf}
          onOpenProduct={(slug) => {
            setDetailContext({ cabinet: addContext.cabinet, category: addContext.category })
            // Не закрываем ShelfAddModal: карточка товара открывается поверх (z-70),
            // а при закрытии пользователь возвращается к выбору из трёх.
            setDetailSlug(slug)
          }}
        />
      )}

      {detailSlug && (
        <ProductModal
          slug={detailSlug}
          shelfContext={detailContext}
          onClose={() => setDetailSlug(null)}
          onChanged={refreshShelf}
          onOpenReport={onOpenReport}
          onOpenBrand={(brand) => {
            setDetailSlug(null)
            onOpenBrand?.(brand)
          }}
          onOpenCategory={(cat) => {
            setDetailSlug(null)
            onOpenCategory?.(cat)
          }}
        />
      )}

      {confirm && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={() => setConfirm(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white p-4 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-normal text-foreground">{confirm.title}</h2>
              <button onClick={() => setConfirm(null)} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
            </div>
            <p className="mb-4 text-sm text-muted-foreground/70">{confirm.message}</p>
            <div className="flex gap-2">
              <button onClick={() => setConfirm(null)} className="flex-1 rounded-xl border border-gray-200 py-2.5 text-sm text-foreground/70 transition-colors hover:bg-gray-50">
                Отмена
              </button>
              <button
                onClick={() => { const fn = confirm.onConfirm; setConfirm(null); fn() }}
                disabled={busy}
                className="flex-1 rounded-xl bg-red-500 py-2.5 text-sm text-white transition-colors hover:bg-red-600 disabled:opacity-40"
              >
                {confirm.confirmLabel || 'Удалить'}
              </button>
            </div>
          </div>
        </div>
      )}

      {removalTarget && (
        <div className="fixed inset-0 z-[85] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={() => setRemovalTarget(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white p-4 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-normal text-foreground">Почему вы убираете этот продукт?</h2>
              <button onClick={() => setRemovalTarget(null)} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
            </div>
            <div className="space-y-1.5">
              {[
                { key: 'complications', label: 'Вызвал осложнения' },
                { key: 'unused', label: 'Не использовался' },
                { key: 'variety', label: 'Хочу попробовать новое' },
                { key: 'other', label: 'Другое' },
              ].map((r) => (
                <button
                  key={r.key}
                  onClick={() => setRemovalReason(r.key)}
                  className={cn(
                    'w-full rounded-xl border px-3 py-2.5 text-left text-sm transition-colors',
                    removalReason === r.key ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-foreground/80 hover:border-primary/30',
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>
            {removalReason === 'other' && (
              <textarea
                value={removalNote}
                onChange={(e) => setRemovalNote(e.target.value)}
                placeholder="Уточните причину…"
                className="mt-2 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:border-primary/40 focus:outline-none resize-none"
                rows={2}
              />
            )}
            <button
              onClick={submitRemoval}
              disabled={!removalReason || removing}
              className="mt-3 w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
            >
              {removing ? 'Удаляем…' : 'Удалить с полки'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
