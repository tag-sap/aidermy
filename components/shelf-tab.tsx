'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Plus, LoaderCircle, Sparkles, X, Check, ListChecks, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ShelfItem } from '@/lib/shelf'
import type { CheckResult } from '@/lib/store'
import { ShelfAddModal } from '@/components/shelf-add-modal'
import { ShelfAddNode } from '@/components/shelf-add-node'
import { ProductModal } from '@/components/product-modal'
import { ProductCard } from '@/components/product-card'
import { useScrollLock } from '@/lib/use-scroll-lock'

type Category = { key: string; title: string; items: ShelfItem[]; compatibility?: number | null }
type Cabinet = {
  key: string
  title: string
  has_scoring: boolean
  compatibility: number | null
  compatibility_details?: {
    base: number | null
    conflicts: { label: string; products: string[]; a: string[]; b: string[] }[]
    duplicate_actives: { ingredient: string; count: number }[]
    coverage: { present: string[]; missing: string[] }
  } | null
  categories: Category[]
}

type ConfirmState = { title: string; message: string; confirmLabel?: string; onConfirm: () => void }

// Ширина фиксированного торца полки (левый/правый край).
const SHELF_EDGE = 16

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
  const [compatInfoOpen, setCompatInfoOpen] = useState(false)
  const [addNodeOpen, setAddNodeOpen] = useState(false)
  const [checkingSlugs, setCheckingSlugs] = useState<Set<string>>(new Set())
  const [recheckErrors, setRecheckErrors] = useState<Map<string, string>>(new Map())

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const processedSlugsRef = useRef<Set<string>>(new Set())
  const recheckCancelledRef = useRef(false)

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

  // Закрытие интерактивного узла «+» при клике вне его.
  useEffect(() => {
    if (!addNodeOpen) return
    const onDown = (e: MouseEvent) => {
      const el = (e.target as Element | null)?.closest?.('[data-shelf-add-node]')
      if (!el) setAddNodeOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [addNodeOpen])

  const currentCabinet = cabinets.find((c) => c.key === activeCabinet) || null

  const currentItems = useMemo(() => {
    if (!currentCabinet) return []
    return currentCabinet.categories.flatMap((c) => c.items)
  }, [currentCabinet])

  const isRecheckingActive = useMemo(() => {
    if (!currentCabinet?.has_scoring) return false
    return currentItems.some(
      (it) => checkingSlugs.has(it.slug) || (Boolean(it.needs_recheck) && !recheckErrors.has(it.slug)),
    )
  }, [currentItems, currentCabinet, checkingSlugs, recheckErrors])

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

  const checkShelfProduct = async (slug: string) => {
    setCheckingSlugs((prev) => new Set(prev).add(slug))
    try {
      const res = await fetch('/api/shelf/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug }),
      })
      if (res.ok) {
        await refreshShelf()
      }
    } catch {
      /* ignore */
    } finally {
      setCheckingSlugs((prev) => {
        const next = new Set(prev)
        next.delete(slug)
        return next
      })
    }
  }

  const getDescription = async (slug: string) => {
    try {
      const res = await fetch('/api/analysis/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug }),
      })
      if (res.ok) {
        await refreshShelf()
      }
    } catch {
      /* ignore */
    }
  }

  // ===== АВТОМАТИЧЕСКАЯ ПЕРЕПРОВЕРКА ПОЛКИ (без LLM) =====
  const collectStaleItems = (cabinets: Cabinet[]): ShelfItem[] =>
    cabinets.flatMap((cab) => cab.categories.flatMap((cat) => cat.items.filter((it) => it.needs_recheck)))

  const updateItemBySlug = (cabinets: Cabinet[], slug: string, patch: Partial<ShelfItem>): Cabinet[] =>
    cabinets.map((cab) => ({
      ...cab,
      categories: cab.categories.map((cat) => ({
        ...cat,
        items: cat.items.map((it) => (it.slug === slug ? { ...it, ...patch } : it)),
      })),
    }))

  const recheckProduct = async (item: ShelfItem) => {
    setCheckingSlugs((prev) => new Set(prev).add(item.slug))
    try {
      const res = await fetch(`/api/shelf/recheck/${item.product_id}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      const d = await res.json().catch(() => ({}))
      if (!res.ok || typeof d.score !== 'number') {
        setRecheckErrors((prev) => new Map(prev).set(item.slug, d.detail || 'Не удалось перепроверить'))
        return
      }
      setCabinets((prev) =>
        updateItemBySlug(prev, item.slug, {
          score: d.score,
          has_report: Boolean(d.analysis?.report),
          needs_recheck: false,
        }),
      )
      setRecheckErrors((prev) => {
        const next = new Map(prev)
        next.delete(item.slug)
        return next
      })
    } catch {
      setRecheckErrors((prev) => new Map(prev).set(item.slug, 'Не удалось перепроверить'))
    } finally {
      setCheckingSlugs((prev) => {
        const next = new Set(prev)
        next.delete(item.slug)
        return next
      })
    }
  }

  const retryRecheck = async (item: ShelfItem) => {
    setRecheckErrors((prev) => {
      const next = new Map(prev)
      next.delete(item.slug)
      return next
    })
    await recheckProduct(item)
    await fetchShelf(true)
  }

  // Запускаем перепроверку неактуальных Analysis после первой загрузки полки.
  useEffect(() => {
    recheckCancelledRef.current = false
    return () => {
      recheckCancelledRef.current = true
    }
  }, [])

  useEffect(() => {
    if (loading) return
    const stale = collectStaleItems(cabinets).filter((it) => !processedSlugsRef.current.has(it.slug))
    if (stale.length === 0) return
    stale.forEach((it) => processedSlugsRef.current.add(it.slug))

    const run = async () => {
      for (const item of stale) {
        if (recheckCancelledRef.current) return
        await recheckProduct(item)
      }
      if (!recheckCancelledRef.current) {
        // После завершения всех проверок пересчитываем общий процент полки.
        await fetchShelf(true)
      }
    }
    run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cabinets, loading])

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
                <div className="min-w-[190px] max-w-[260px] flex-1 sm:flex-none">
                  <div className="flex items-center justify-end gap-1">
                    <p className="text-[9px] uppercase tracking-wide text-muted-foreground/50">Совместимость ухода</p>
                    <button
                      onClick={() => setCompatInfoOpen((v) => !v)}
                      className="relative flex size-4 items-center justify-center rounded-full text-muted-foreground/40 transition-colors hover:text-primary"
                      aria-label="Что такое совместимость ухода"
                    >
                      <Info className="size-3.5" />
                      {compatInfoOpen && currentCabinet.compatibility_details && (
                        <div
                          className="absolute right-0 top-5 z-30 w-64 rounded-xl border border-gray-200 bg-white p-3 text-left shadow-xl animate-modal-panel"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <p className="text-[11px] font-medium text-foreground">Совместимость ухода</p>
                          <p className="mt-0.5 text-[10px] leading-relaxed text-muted-foreground/70">
                            Насколько продукты сочетаются между собой, а не с вашей кожей.
                          </p>
                          {currentCabinet.compatibility_details.conflicts.length > 0 && (
                            <div className="mt-2 border-t border-gray-100 pt-2">
                              {currentCabinet.compatibility_details.conflicts.map((c, i) => (
                                <p key={i} className="mt-1 text-[10px] text-foreground/70">
                                  <span className="text-red-500">⚠</span> {c.label}
                                </p>
                              ))}
                            </div>
                          )}
                          {currentCabinet.compatibility_details.duplicate_actives.length > 0 && (
                            <p className="mt-1.5 text-[10px] text-muted-foreground/70">
                              Повторяются: {currentCabinet.compatibility_details.duplicate_actives.slice(0, 4).map((d) => d.ingredient).join(', ')}
                            </p>
                          )}
                        </div>
                      )}
                    </button>
                  </div>
                  {isRecheckingActive ? (
                    <div className="mt-1 flex items-center justify-end gap-1.5">
                      <LoaderCircle className="size-3.5 animate-spin text-primary" />
                      <span className="text-xs text-muted-foreground/70">Обновляем анализ полки...</span>
                    </div>
                  ) : (
                    <>
                      <div className="mt-1 flex items-center gap-2">
                        <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-gray-200/60">
                          <div
                            className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out"
                            style={{ width: `${currentCabinet.compatibility ?? 0}%` }}
                          />
                        </div>
                        <span className={cn('text-lg font-light tabular-nums', currentCabinet.compatibility != null ? 'text-primary' : 'text-muted-foreground/40')}>
                          {currentCabinet.compatibility != null ? `${currentCabinet.compatibility}%` : '—'}
                        </span>
                      </div>
                      <p className="mt-0.5 text-right text-[9px] text-muted-foreground/40">Как сочетаются между собой</p>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          {currentItems.length === 0 && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-white/40 px-6 py-12 text-center">
              <Sparkles className="size-8 text-primary/30" />
              <p className="mt-3 text-base font-normal text-foreground/80">На полке пока нет продуктов</p>
              <p className="mt-1 max-w-xs text-xs leading-relaxed text-muted-foreground/60">
                Добавьте продукт из каталога, по названию, по ссылке или по фото — и он появится здесь.
              </p>
              <button
                onClick={() => setAddContext({ cabinet: currentCabinet.key, category: '' })}
                className="mt-4 flex items-center gap-1.5 rounded-xl bg-primary px-5 py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90"
              >
                <Plus className="size-4" />
                Добавить продукт
              </button>
            </div>
          )}

          {/* Одна динамическая физическая полка на зону: ширина плавно растёт/сужается
              вместе с содержимым, при переполнении flex-wrap переносит на новую строку. */}
          <div className="relative mx-auto w-fit min-w-[280px] max-w-full transition-[width] duration-300 ease-out">
            <div className={cn('flex flex-wrap gap-x-5 gap-y-6 px-4 pb-9 pt-3', currentItems.length === 0 && 'justify-center')}>
                {currentCabinet.categories.map((cat) => {
                  if (cat.items.length === 0) return null
                  return (
                    <div key={cat.key} className="relative">
                      <span className="absolute -top-2.5 left-2 z-10 rounded-full bg-background px-2 text-[9px] font-medium uppercase tracking-[0.18em] text-muted-foreground/50">
                        {cat.title}
                      </span>
                      <div className="flex flex-wrap gap-2.5 rounded-2xl border border-dashed border-gray-300/70 p-2">
                        {cat.items.map((item, idx) => {
                          const isSelected = selected.has(item.id)
                          return (
                            <div key={item.id} className="animate-shelf-card group relative w-[160px] shrink-0" style={{ animationDelay: `${idx * 35}ms` }}>
                              <div className={cn('rounded-2xl transition-all', selectionMode && isSelected && 'ring-2 ring-primary/20')}>
                                <ProductCard
                                  name={item.name}
                                  brand={item.brand}
                                  imageUrl={item.image_url}
                                  category={item.category}
                                  score={item.score}
                                  hasReport={item.has_report}
                                  scoring={currentCabinet.has_scoring}
                                  checking={checkingSlugs.has(item.slug) || (Boolean(item.needs_recheck) && !recheckErrors.has(item.slug))}
                                  error={recheckErrors.get(item.slug)}
                                  onOpen={() => (selectionMode ? toggleSelect(item.id) : openDetail(item.slug, item.cabinet, item.category))}
                                  onCheck={() => checkShelfProduct(item.slug)}
                                  onGetDescription={() => getDescription(item.slug)}
                                  onViewAnalysis={() => openDetail(item.slug, item.cabinet, item.category)}
                                  onRetry={() => retryRecheck(item)}
                                />
                              </div>

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
                                  className="absolute right-1.5 top-1.5 flex size-6 items-center justify-center rounded-full border border-gray-200/60 bg-white/80 text-muted-foreground/60 hover:text-red-500"
                                  aria-label="Удалить продукт"
                                >
                                  <X className="size-3.5" />
                                </button>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}

                {/* Интерактивный узел «+» — последний пустой слот */}
                <div data-shelf-add-node className="relative">
                  <div className="rounded-2xl border border-dashed border-gray-300/70 p-2">
                    <button
                      onClick={() => setAddNodeOpen(true)}
                      className="flex h-[180px] w-[130px] items-center justify-center text-muted-foreground/40 transition-colors hover:text-primary"
                      aria-label="Добавить продукт"
                    >
                      <Plus className={cn('size-6 transition-transform', addNodeOpen && 'animate-shelf-plus-collapse')} />
                    </button>
                  </div>

                  {/* Раскрытый узел: абсолютный overlay, не влияет на ширину полки */}
                  {addNodeOpen && (
                    <ShelfAddNode
                      categories={currentCabinet.categories}
                      onClose={() => setAddNodeOpen(false)}
                      onPick={(cat) => { setAddNodeOpen(false); setAddContext({ cabinet: currentCabinet.key, category: cat.key }) }}
                    />
                  )}
                </div>
              </div>

            {/* Полка: [ левый торец ][ центр ][ правый торец ] (без дублирующего названия зоны) */}
            <div className="shelf-plank pointer-events-none absolute inset-x-0 bottom-0 flex h-7 rounded-full">
              <div className="shelf-surface h-full rounded-l-full" style={{ width: SHELF_EDGE }} />
              <div className="shelf-surface h-full flex-1" />
              <div className="shelf-surface h-full rounded-r-full" style={{ width: SHELF_EDGE }} />
            </div>
          </div>
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
