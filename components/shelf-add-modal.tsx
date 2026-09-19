'use client'

import { useEffect, useState } from 'react'
import { X, Search, Link2, Wand2, LoaderCircle, Sparkles, ChevronLeft } from 'lucide-react'
import { CABINET_TITLES, CABINET_META } from '@/lib/shelf'

type Mode = 'menu' | 'base' | 'url' | 'recommend'

type SearchProduct = {
  slug: string
  name: string
  brand: string
  image_url: string
  category: string
}

type Recommendation = {
  slug: string
  name: string
  brand: string
  image_url: string
  score: number | null
  reason: string
}

function splitName(name: string): { brand: string; title: string } {
  const parts = (name || '').split('\n').filter((x) => x.trim())
  if (parts.length >= 2) return { brand: parts[0], title: parts.slice(1).join(' ') }
  return { brand: '', title: (name || '').trim() }
}

export function ShelfAddModal({
  cabinet,
  category,
  onClose,
  onAdded,
  onOpenProduct,
}: {
  cabinet: string
  category: string
  onClose: () => void
  onAdded: () => void
  onOpenProduct?: (slug: string) => void
}) {
  const [mode, setMode] = useState<Mode>('menu')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchProduct[]>([])
  const [searching, setSearching] = useState(false)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [recs, setRecs] = useState<Recommendation[]>([])
  const [recLoading, setRecLoading] = useState(false)
  const [analyzing, setAnalyzing] = useState<Set<string>>(new Set())

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const isScoring = CABINET_META.find((c) => c.key === cabinet)?.hasScoring ?? false

  const search = async (q: string) => {
    setQuery(q)
    if (q.trim().length < 2) {
      setResults([])
      return
    }
    setSearching(true)
    try {
      const res = await fetch(`/api/catalog?search=${encodeURIComponent(q.trim())}&limit=10`)
      const data = await res.json()
      setResults(
        (data.products || []).map((p: any) => {
          const { brand, title } = splitName(p.name || '')
          return {
            slug: p.slug,
            name: title,
            brand: brand || p.brand || '',
            image_url: p.image_url || '',
            category: p.category || '',
          }
        }),
      )
    } catch (e) {
      console.error(e)
    } finally {
      setSearching(false)
    }
  }

  const addBySlug = async (slug: string) => {
    setBusy(true)
    setStatus('')
    try {
      const res = await fetch('/api/shelf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug, cabinet, category }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        if (res.status === 422) {
          throw new Error(`Этот продукт не подходит для выбранной категории. ${data.detail || ''}`)
        }
        throw new Error(data.detail || 'Не удалось добавить')
      }
      if (data.duplicate) setStatus('Этот продукт уже на полке')
      onAdded()
      onClose()
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось добавить')
    } finally {
      setBusy(false)
    }
  }

  const addByUrl = async () => {
    if (!url.trim() || busy) return
    setBusy(true)
    setStatus('Загружаем страницу…')
    try {
      const imp = await fetch('/api/products/import-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() }),
      })
      const impData = await imp.json().catch(() => ({}))
      if (!imp.ok) throw new Error(impData.detail || 'Не удалось получить товар')
      const slug = impData.product?.slug
      if (!slug) throw new Error('Товар на странице не найден')
      setStatus('Добавляем на полку…')
      await addBySlug(slug)
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось получить товар')
      setBusy(false)
    }
  }

  const analyzeRecommendation = async (slug: string) => {
    setAnalyzing((prev) => new Set(prev).add(slug))
    try {
      const res = await fetch('/api/shelf/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug }),
      })
      const data = await res.json().catch(() => ({}))
      setRecs((prev) =>
        prev.map((r) =>
          r.slug === slug
            ? {
                ...r,
                score: res.ok && data.score != null ? data.score : r.score,
                reason: res.ok && data.analysis?.summary ? data.analysis.summary : r.reason,
              }
            : r,
        ),
      )
    } catch (e) {
      console.error(e)
    } finally {
      setAnalyzing((prev) => {
        const next = new Set(prev)
        next.delete(slug)
        return next
      })
    }
  }

  const loadRecommendations = async () => {
    setRecLoading(true)
    setStatus('')
    try {
      const res = await fetch('/api/shelf/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ cabinet, category }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Не удалось подобрать')
      const recommendations = data.recommendations || []
      setRecs(recommendations)
      // Автоматически анализируем все три продукта (для скоринговых шкафов)
      if (isScoring) {
        recommendations.forEach((r) => analyzeRecommendation(r.slug))
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось подобрать')
    } finally {
      setRecLoading(false)
    }
  }

  useEffect(() => {
    if (mode === 'recommend') loadRecommendations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])
  const title = `${CABINET_TITLES[cabinet] || cabinet} → ${category}`

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/30 backdrop-blur-sm sm:items-center sm:p-4" onClick={onClose}>
      <div className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-4 sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {mode !== 'menu' && (
              <button onClick={() => { setMode('menu'); setStatus('') }} className="text-muted-foreground hover:text-foreground">
                <ChevronLeft className="size-4" />
              </button>
            )}
            <h2 className="text-base font-normal text-foreground">
              {mode === 'menu' ? 'Добавить продукт' : mode === 'base' ? 'Выбрать из базы' : mode === 'url' ? 'Добавить по ссылке' : 'Подобрать автоматически'}
            </h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
        </div>

        {mode !== 'menu' && <p className="mb-3 text-[11px] text-muted-foreground/60">В полку: {title}</p>}

        {mode === 'menu' && (
          <div className="space-y-2">
            <button onClick={() => setMode('base')} className="flex w-full items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 text-left transition-colors hover:bg-gray-50">
              <Search className="size-4 text-primary" />
              <div><p className="text-sm text-foreground">Выбрать из базы</p><p className="text-[10px] text-muted-foreground/60">Найти уже существующий продукт</p></div>
            </button>
            <button onClick={() => setMode('url')} className="flex w-full items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 text-left transition-colors hover:bg-gray-50">
              <Link2 className="size-4 text-primary" />
              <div><p className="text-sm text-foreground">Добавить по ссылке</p><p className="text-[10px] text-muted-foreground/60">Импортировать товар по URL</p></div>
            </button>
            <button onClick={() => setMode('recommend')} className="flex w-full items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 text-left transition-colors hover:bg-gray-50">
              <Wand2 className="size-4 text-primary" />
              <div><p className="text-sm text-foreground">Подобрать автоматически</p><p className="text-[10px] text-muted-foreground/60">Aidermy предложит 3 варианта</p></div>
            </button>
          </div>
        )}
        {mode === 'base' && (
          <div>
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground/40" />
              <input value={query} onChange={(e) => search(e.target.value)} placeholder="Название, бренд или категория…" className="w-full rounded-xl border border-gray-200/60 bg-gray-50/50 py-2 pl-8 pr-3 text-sm focus:border-primary/40 focus:outline-none" />
            </div>
            <div className="max-h-72 overflow-y-auto rounded-xl border border-gray-100">
              {searching ? (
                <div className="p-3 text-center text-xs text-muted-foreground/50">Поиск…</div>
              ) : results.length === 0 ? (
                <div className="p-3 text-center text-xs text-muted-foreground/50">{query.trim().length >= 2 ? 'Ничего не найдено' : 'Введите запрос'}</div>
              ) : (
                results.map((p) => (
                  <button key={p.slug} onClick={() => addBySlug(p.slug)} disabled={busy} className="flex w-full items-center gap-2 border-b border-gray-50 p-2 text-left transition-colors hover:bg-gray-50 disabled:opacity-50">
                    {p.image_url ? <img src={p.image_url} alt="" className="size-9 rounded-lg bg-white object-contain" /> : <Sparkles className="size-9 rounded-lg bg-gray-50 p-2 text-muted-foreground/30" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs text-foreground/80">{p.brand}</span>
                      <span className="block truncate text-[11px] text-muted-foreground/60">{p.name}</span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        )}

        {mode === 'url' && (
          <div>
            <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addByUrl()} placeholder="Вставьте ссылку на товар…" className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none" />
            <button onClick={addByUrl} disabled={!url.trim() || busy} className="mt-2 w-full rounded-xl bg-primary py-2.5 text-sm text-white transition-colors hover:bg-primary/90 disabled:opacity-40">
              {busy ? <LoaderCircle className="mx-auto size-4 animate-spin" /> : 'Импортировать'}
            </button>
          </div>
        )}

        {mode === 'recommend' && (
          <div>
            {recLoading ? (
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground/50">
                <LoaderCircle className="mb-2 size-6 animate-spin text-primary" />
                <span className="text-xs">Подбираем варианты…</span>
              </div>
            ) : recs.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground/50">В базе пока нет подходящих продуктов для этой категории</div>
            ) : (
              <div className="space-y-2">
                {recs.map((r) => (
                  <div key={r.slug} className="rounded-xl border border-gray-200 p-2.5">
                    <div className="flex gap-2.5">
                      <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-gray-50">
                        {r.image_url ? <img src={r.image_url} alt="" className="h-full w-full object-contain p-1" /> : <Sparkles className="size-5 text-muted-foreground/30" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        {r.brand && <p className="text-[9px] uppercase tracking-wide text-muted-foreground/50">{r.brand}</p>}
                        <p className="truncate text-xs font-medium text-foreground/90">{r.name}</p>
                        {r.score != null ? (
                          <p className="text-sm font-light text-primary">{r.score}%</p>
                        ) : isScoring ? (
                          analyzing.has(r.slug) ? (
                            <p className="text-[10px] text-muted-foreground/50">Анализ выполняется…</p>
                          ) : (
                            <p className="text-[10px] text-muted-foreground/50">Анализ ещё не выполнен</p>
                          )
                        ) : null}
                      </div>
                    </div>
                    {r.reason && <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground/60">{r.reason}</p>}
                    <div className="mt-2 flex gap-1.5">
                      {onOpenProduct && (
                        <button
                          onClick={() => onOpenProduct(r.slug)}
                          className="flex-1 rounded-lg border border-gray-200 py-1.5 text-xs text-foreground/70 transition-colors hover:bg-gray-50"
                        >
                          Подробнее
                        </button>
                      )}
                      <button onClick={() => addBySlug(r.slug)} disabled={busy} className="flex-1 rounded-lg bg-primary py-1.5 text-xs text-white transition-colors hover:bg-primary/90 disabled:opacity-40">
                        Выбрать
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {status && <p className="mt-2 text-[11px] text-muted-foreground/60">{status}</p>}
      </div>
    </div>
  )
}


