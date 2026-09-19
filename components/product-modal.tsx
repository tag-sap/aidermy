'use client'

import { useEffect, useState } from 'react'
import { X, Sparkles, LoaderCircle, Check, Trash2, ShieldCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarkupText } from '@/components/markup-text'
import { CABINET_META, CABINET_TITLES } from '@/lib/shelf'
import type { CheckResult } from '@/lib/store'

type ProductDetail = {
  product: {
    id: number
    name: string
    brand: string
    slug: string
    image_url: string
    category: string
    ingredients: string
    url: string
  }
  score: number | null
  analysis: {
    verdict?: string
    summary?: string
    score?: number
    safe_ingredients?: string[]
    caution_ingredients?: string[]
    active_ingredients?: { name: string; position: number; concentration: string; effectiveness: string } | null
    how_to_use?: { application: string; time: string; note?: string } | null
    expectations?: { when: string; normal: string; danger: string } | null
  } | null
  on_shelf: { shelf_id: number; cabinet: string; category: string } | null
}

function scoreColor(s: number) {
  if (s >= 80) return 'text-[#4E9F6E] bg-[#4E9F6E]/10 border-[#4E9F6E]/30'
  if (s >= 60) return 'text-[#6FBF8D] bg-[#6FBF8D]/10 border-[#6FBF8D]/30'
  if (s >= 40) return 'text-[#8B7CF6] bg-[#8B7CF6]/10 border-[#8B7CF6]/30'
  return 'text-[#B7A7F0] bg-[#B7A7F0]/10 border-[#B7A7F0]/30'
}

function guessCategory(legacyCategory: string): string {
  const map: Record<string, string> = {
    'Очищение': 'Очищение',
    'Тонер': 'Тонизация',
    'Тоник': 'Тонизация',
    'Сыворотка': 'Сыворотки',
    'Крем': 'Увлажнение',
    'SPF': 'SPF',
    'Защита': 'SPF',
    'Маска': 'Маски',
  }
  return map[legacyCategory] || ''
}

function asList(v: unknown): string[] {
  if (Array.isArray(v)) return v as string[]
  if (typeof v === 'string') {
    try {
      const p = JSON.parse(v)
      if (Array.isArray(p)) return p.map(String)
    } catch {
      /* ignore */
    }
    return v.trim() ? [v] : []
  }
  return []
}
export function ProductModal({
  slug,
  onClose,
  onChanged,
  onOpenReport,
}: {
  slug: string | null
  onClose: () => void
  onChanged: () => void
  onOpenReport?: (result: CheckResult) => void
}) {
  const [data, setData] = useState<ProductDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [showPicker, setShowPicker] = useState(false)
  const [pickCabinet, setPickCabinet] = useState('face')
  const [pickCategory, setPickCategory] = useState('')

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  useEffect(() => {
    if (!slug) return
    setLoading(true)
    setError('')
    setShowPicker(false)
    fetch(`/api/products/${encodeURIComponent(slug)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error('Не удалось загрузить продукт')
        return res.json()
      })
      .then((d) => {
        setData(d)
        setPickCategory('')
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Ошибка загрузки'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  if (!slug) return null

  const product = data?.product

  const refreshDetail = async () => {
    if (!product) return
    const res = await fetch(`/api/products/${encodeURIComponent(product.slug)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (res.ok) setData(await res.json())
  }

  const addToShelf = async () => {
    if (!product) return
    const category = pickCategory || guessCategory(data?.product.category || '')
    setBusy(true)
    try {
      const res = await fetch('/api/shelf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug: product.slug, cabinet: pickCabinet, category }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Не удалось добавить')
      }
      setShowPicker(false)
      onChanged()
      await refreshDetail()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось добавить')
    } finally {
      setBusy(false)
    }
  }

  const removeFromShelf = async () => {
    if (!data?.on_shelf) return
    setBusy(true)
    try {
      const res = await fetch(`/api/shelf/${data.on_shelf.shelf_id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('Не удалось убрать с полки')
      setData((prev) => (prev ? { ...prev, on_shelf: null } : prev))
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось убрать с полки')
    } finally {
      setBusy(false)
    }
  }

  const checkCompatibility = async () => {
    if (!product || checking) return
    setChecking(true)
    setError('')
    try {
      const res = await fetch('/api/shelf/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug: product.slug }),
      })
      const d = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(d.detail || 'Не удалось выполнить анализ')
      setData((prev) =>
        prev
          ? {
              ...prev,
              score: d.score ?? prev.score,
              analysis: d.analysis ?? prev.analysis,
            }
          : prev,
      )
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось выполнить анализ')
    } finally {
      setChecking(false)
    }
  }

  const openFullReport = () => {
    if (!data || !product || !data.analysis || !onOpenReport) return
    const a = data.analysis
    const result: CheckResult = {
      id: String(product.id),
      product: product.name,
      skinType: 'Нормальная',
      score: data.score ?? 0,
      verdict: a.verdict || '',
      summary: a.summary || '',
      safe_ingredients: asList(a.safe_ingredients),
      caution_ingredients: asList(a.caution_ingredients),
      slug: product.slug,
      image_url: product.image_url,
      createdAt: Date.now(),
      active_ingredients: a.active_ingredients ?? undefined,
      how_to_use: a.how_to_use ?? undefined,
      expectations: a.expectations ?? undefined,
    }
    onOpenReport(result)
  }

  const meta = CABINET_META.find((c) => c.key === pickCabinet) || CABINET_META[0]
  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-black/30 backdrop-blur-sm sm:items-center sm:p-4" onClick={onClose}>
      <div
        className="no-scrollbar max-h-[92dvh] w-full max-w-md max-w-[100vw] overflow-y-auto overflow-x-hidden rounded-t-2xl bg-white p-4 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <LoaderCircle className="size-6 animate-spin text-primary" />
          </div>
        ) : error && !product ? (
          <div className="py-10 text-center text-sm text-muted-foreground/60">{error}</div>
        ) : product ? (
          <>
            <div className="mb-3 flex items-start justify-between gap-3">
              <h2 className="text-base font-normal text-foreground">Продукт</h2>
              <button type="button" onClick={onClose} className="relative z-10 shrink-0 text-muted-foreground hover:text-foreground">
                <X className="size-4" />
              </button>
            </div>

            <div className="flex gap-3">
              <div className="flex size-20 shrink-0 flex-col items-center justify-center overflow-hidden rounded-2xl bg-gray-50">
                {product.image_url ? (
                  <img src={product.image_url} alt="" className="h-full w-full object-contain p-1" />
                ) : (
                  <>
                    <Sparkles className="size-6 text-muted-foreground/30" />
                    <span className="mt-1 text-[8px] text-muted-foreground/40">Изображение недоступно</span>
                  </>
                )}
              </div>
              <div className="min-w-0 flex-1">
                {product.brand && <p className="text-[10px] uppercase tracking-wide text-muted-foreground/50">{product.brand}</p>}
                <p className="text-sm font-medium leading-snug text-foreground/90">{product.name}</p>
                {data?.score != null ? (
                  <span className={cn('mt-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium', scoreColor(data.score))}>
                    {data.score}% совместимость
                  </span>
                ) : (
                  <span className="mt-2 inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-xs text-muted-foreground/60">
                    Не проверен
                  </span>
                )}
              </div>
            </div>

            {product.category && (
              <p className="mt-3 text-xs text-muted-foreground/60">Категория: {product.category}</p>
            )}

            <div className="mt-3">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground/50">Состав (INCI)</p>
              {product.ingredients ? (
                <div className="max-h-32 overflow-y-auto break-words rounded-xl border border-gray-100 bg-gray-50/60 p-2.5 text-[11px] leading-relaxed text-foreground/60">
                  {product.ingredients}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-gray-200/70 py-3 text-center text-[11px] text-muted-foreground/40">
                  Состав пока не найден
                </div>
              )}
            </div>

            {data?.analysis ? (
              <div className="mt-3 rounded-xl border border-primary/15 bg-primary/5 p-3">
                <div className="flex items-center gap-1.5">
                  <ShieldCheck className="size-3.5 text-primary" />
                  <span className="text-xs font-medium text-foreground/80">{data.analysis.verdict || 'Проверено'}</span>
                </div>
                {data.analysis.summary && (
                  <p className="mt-1 break-words text-[11px] leading-relaxed text-foreground/60"><MarkupText text={data.analysis.summary} /></p>
                )}
                {(asList(data.analysis.safe_ingredients).length > 0 || asList(data.analysis.caution_ingredients).length > 0) && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {asList(data.analysis.safe_ingredients).slice(0, 4).map((i) => (
                      <span key={i} className="rounded-full bg-white/70 px-1.5 py-0.5 text-[9px] text-foreground/60">{i}</span>
                    ))}
                    {asList(data.analysis.caution_ingredients).slice(0, 4).map((i) => (
                      <span key={i} className="rounded-full bg-red-50 px-1.5 py-0.5 text-[9px] text-red-500">{i}</span>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-3 rounded-xl border border-dashed border-gray-200/70 py-3 text-center text-[11px] text-muted-foreground/40">
                Анализ ещё не выполнен
              </div>
            )}

            {data?.analysis && onOpenReport && (
              <button
                onClick={openFullReport}
                className="mt-2 w-full rounded-xl border border-primary/20 bg-white py-2 text-xs text-primary transition-colors hover:bg-primary/5"
              >
                Открыть полный отчёт
              </button>
            )}

            {error && product && <p className="mt-2 text-[11px] text-red-500">{error}</p>}

            {showPicker && (
              <div className="mt-3 space-y-2 rounded-xl border border-gray-100 p-3">
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-wide text-muted-foreground/50">Шкаф</label>
                  <select value={pickCabinet} onChange={(e) => { setPickCabinet(e.target.value); setPickCategory('') }} className="w-full rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-2 text-xs focus:border-primary/40 focus:outline-none">
                    {CABINET_META.map((c) => <option key={c.key} value={c.key}>{c.title}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-[10px] uppercase tracking-wide text-muted-foreground/50">Категория</label>
                  <select value={pickCategory} onChange={(e) => setPickCategory(e.target.value)} className="w-full rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-2 text-xs focus:border-primary/40 focus:outline-none">
                    <option value="">Выбрать категорию</option>
                    {meta.categories.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <button onClick={addToShelf} disabled={busy} className="w-full rounded-lg bg-primary py-2 text-xs text-white transition-colors hover:bg-primary/90 disabled:opacity-40">
                  {busy ? 'Добавляем…' : 'Подтвердить'}
                </button>
              </div>
            )}
            <div className="mt-4 flex flex-col gap-2">
              <button
                onClick={checkCompatibility}
                disabled={checking}
                className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-primary/30 bg-primary/5 py-2.5 text-sm text-primary transition-colors hover:bg-primary/10 disabled:opacity-60"
              >
                {checking ? <LoaderCircle className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                {checking ? 'Анализ выполняется…' : 'Проверить совместимость'}
              </button>

              {data?.on_shelf ? (
                <>
                  <div className="flex items-center gap-1.5 rounded-xl border border-gray-100 bg-gray-50/60 px-3 py-2 text-xs text-foreground/70">
                    <Check className="size-3.5 text-primary" />
                    На полке: {CABINET_TITLES[data.on_shelf.cabinet] || data.on_shelf.cabinet} → {data.on_shelf.category}
                  </div>
                  <button
                    onClick={removeFromShelf}
                    disabled={busy}
                    className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-red-100 py-2.5 text-sm text-red-500 transition-colors hover:bg-red-50 disabled:opacity-40"
                  >
                    <Trash2 className="size-4" />
                    Убрать с полки
                  </button>
                </>
              ) : (
                <button
                  onClick={() => setShowPicker((v) => !v)}
                  className="w-full rounded-xl bg-primary py-2.5 text-sm text-white transition-colors hover:bg-primary/90"
                >
                  Добавить на полку
                </button>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  )
}




