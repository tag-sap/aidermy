'use client'

import { useState, useEffect } from 'react'
import { Plus, X, Trash2, Sparkles, Search } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ShelfItem = {
  id: number
  product_id: number
  category: string
  notes?: string
  name: string
  brand: string
  image_url: string
  slug: string
  ingredients: string
  score: number
}

const CATEGORIES = ['Очищение', 'Тонер', 'Сыворотка', 'Крем', 'SPF', 'Маска']

export function ShelfTab({ onCheck }: { onCheck: (product: string) => void }) {
  const [items, setItems] = useState<ShelfItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<any | null>(null)
  const [category, setCategory] = useState('')
  const [feedback, setFeedback] = useState('')
  const [analysis, setAnalysis] = useState<any | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const loadShelf = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/shelf', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const data = await res.json()
        setItems(data.items || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadShelf()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const searchProducts = async (q: string) => {
    setQuery(q)
    if (q.trim().length < 2) {
      setResults([])
      return
    }
    setSearching(true)
    try {
      const res = await fetch(`/api/catalog?search=${encodeURIComponent(q.trim())}&limit=8`)
      const data = await res.json()
      setResults(data.products || [])
    } catch (e) {
      console.error(e)
    } finally {
      setSearching(false)
    }
  }

  const openAdd = () => {
    setSelected(null)
    setQuery('')
    setResults([])
    setCategory('')
    setFeedback('')
    setShowAdd(true)
  }

  const addToShelf = async () => {
    if (!selected) return
    try {
      const res = await fetch('/api/shelf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug: selected.slug, category }),
      })
      const data = await res.json()
      if (res.ok) {
        setFeedback(data.duplicate ? 'Этот продукт уже на полке' : 'Добавлено на полку')
        setShowAdd(false)
        loadShelf()
      } else {
        setFeedback(data.detail || 'Не удалось добавить')
      }
    } catch (e) {
      console.error(e)
    }
  }

  const removeItem = async (id: number) => {
    setItems((prev) => prev.filter((i) => i.id !== id))
    await fetch(`/api/shelf/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
  }

  const changeCategory = async (id: number, cat: string) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, category: cat } : i)))
    await fetch(`/api/shelf/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ category: cat }),
    })
  }

  const runAnalysis = async () => {
    setAnalyzing(true)
    try {
      const res = await fetch('/api/shelf/analysis', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) setAnalysis(await res.json())
    } catch (e) {
      console.error(e)
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="flex-shrink-0 pb-1">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-light text-foreground">Моя полка</h1>
            <p className="text-xs text-muted-foreground/70">Ваша косметика и то, как она работает вместе</p>
          </div>
          <button onClick={openAdd} className="flex shrink-0 items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-[11px] text-primary-foreground transition-colors hover:bg-primary/90">
            <Plus className="size-3.5" />
            Добавить
          </button>
        </div>
      </div>

      <div className="no-scrollbar flex-1 min-h-0 overflow-y-auto pr-0.5">
        {feedback && <div className="mb-2 rounded-lg bg-primary/10 px-3 py-2 text-[11px] text-primary">{feedback}</div>}

        {loading ? (
          <div className="py-10 text-center text-sm text-muted-foreground/50">Загрузка…</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="mb-3 flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Sparkles className="size-6" strokeWidth={1.5} />
            </div>
            <p className="text-sm text-muted-foreground/60">Полка пока пуста</p>
            <button onClick={openAdd} className="mt-3 text-xs text-primary hover:underline">Добавить первый продукт</button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 lg:grid-cols-4">
              {items.map((item) => (
                <div key={item.id} className="group relative rounded-2xl border border-white/40 bg-white/40 p-3 backdrop-blur-sm transition-all hover:border-primary/20 hover:bg-white/60">
                  <button onClick={() => removeItem(item.id)} className="absolute right-2 top-2 z-10 rounded-full bg-white/80 p-1 text-muted-foreground/60 opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100">
                    <Trash2 className="size-3" />
                  </button>
                  <button onClick={() => onCheck(item.name)} className="block w-full cursor-pointer text-left">
                    <div className="mb-2 flex aspect-square items-center justify-center overflow-hidden rounded-xl bg-white/60">
                      {item.image_url ? <img src={item.image_url} alt={item.name} className="h-full w-full object-contain p-2" /> : <Sparkles className="size-6 text-muted-foreground/30" />}
                    </div>
                    <p className="line-clamp-2 text-[11px] font-medium leading-snug text-foreground/80">{item.name}</p>
                    <p className="mt-0.5 text-[9px] text-muted-foreground/50">{item.brand}</p>
                    {item.notes && <span className="mt-1 inline-block max-w-full truncate rounded-full bg-primary/10 px-2 py-0.5 text-[9px] text-primary">{item.notes}</span>}
                    {item.score > 0 && <span className="mt-1.5 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[9px] text-primary">{item.score}%</span>}
                  </button>
                  <select value={item.category} onChange={(e) => changeCategory(item.id, e.target.value)} className="mt-2 w-full rounded-lg border border-white/30 bg-white/40 px-1.5 py-1 text-[9px] text-foreground/60 focus:outline-none">
                    <option value="">Категория…</option>
                    {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
                  </select>
                </div>
              ))}
            </div>

            <div className="mt-5 rounded-2xl border border-primary/15 bg-white/30 p-4 backdrop-blur-sm">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-normal text-foreground">Анализ моей полки</h2>
                <button onClick={runAnalysis} disabled={analyzing} className="rounded-full bg-primary/10 px-3 py-1 text-[10px] text-primary transition-colors hover:bg-primary/20 disabled:opacity-50">
                  {analyzing ? 'Анализируем…' : 'Анализировать'}
                </button>
              </div>
              {analysis && (
                <div className="mt-3 space-y-3">
                  <div className="flex items-baseline gap-2">
                    <span className="text-3xl font-light text-primary">{analysis.overall_score}%</span>
                    <span className="text-[10px] text-muted-foreground/60">общая совместимость рутины</span>
                  </div>
                  {analysis.products?.length > 0 && (
                    <div className="space-y-1">
                      {analysis.products.map((p: any) => (
                        <div key={p.name} className="flex items-center justify-between gap-2 text-[10px]">
                          <span className="truncate text-muted-foreground/70">{p.name}</span>
                          <span className="shrink-0 text-foreground/70">{p.score}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {analysis.duplicate_actives?.length > 0 && (
                    <p className="text-[10px] text-muted-foreground/70">Дублируются активы: {analysis.duplicate_actives.slice(0, 5).map((d: any) => d.ingredient).join(', ')}</p>
                  )}
                  {analysis.conflicts?.length > 0 && (
                    <p className="text-[10px] text-red-500/80">Возможные конфликты: {analysis.conflicts.map((c: any) => `${c.a.join('/')} + ${c.b.join('/')}`).join('; ')}</p>
                  )}
                </div>
              )}
            </div>
          </>
        )}
        <div className="h-24" />
      </div>

      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/30 backdrop-blur-sm sm:items-center sm:p-4" onClick={() => setShowAdd(false)}>
          <div className="w-full max-w-md rounded-t-2xl bg-white p-4 sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-normal text-foreground">Добавить продукт</h2>
              <button onClick={() => setShowAdd(false)} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
            </div>
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground/40" />
              <input value={query} onChange={(e) => searchProducts(e.target.value)} placeholder="Поиск продукта…" className="w-full rounded-xl border border-gray-200/60 bg-gray-50/50 py-2 pl-8 pr-3 text-sm focus:border-primary/40 focus:outline-none" />
            </div>
            {selected ? (
              <div className="mb-3 flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 p-2">
                {selected.image_url && <img src={selected.image_url} alt="" className="size-10 rounded-lg bg-white/60 object-contain" />}
                <div className="min-w-0 flex-1"><p className="truncate text-xs font-medium">{selected.name}</p></div>
                <button onClick={() => setSelected(null)} className="text-muted-foreground/50 hover:text-foreground"><X className="size-3.5" /></button>
              </div>
            ) : (
              <div className="mb-3 max-h-56 overflow-y-auto rounded-xl border border-gray-100">
                {searching ? (
                  <div className="p-3 text-center text-xs text-muted-foreground/50">Поиск…</div>
                ) : (
                  results.map((p) => (
                    <button key={p.slug} onClick={() => setSelected(p)} className="flex w-full items-center gap-2 border-b border-gray-50 p-2 text-left transition-colors hover:bg-gray-50">
                      {p.image_url && <img src={p.image_url} alt="" className="size-9 rounded-lg bg-white/60 object-contain" />}
                      <span className="min-w-0 flex-1 truncate text-xs">{p.name}</span>
                    </button>
                  ))
                )}
                {!searching && results.length === 0 && query.trim().length >= 2 && <div className="p-3 text-center text-xs text-muted-foreground/50">Ничего не найдено</div>}
              </div>
            )}
            {selected && (
              <div className="mb-3 flex flex-wrap gap-1.5">
                {CATEGORIES.map((c) => (
                  <button key={c} onClick={() => setCategory(c)} className={cn('rounded-full border px-2.5 py-1 text-[10px] transition-colors', category === c ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-muted-foreground/70 hover:border-primary/30')}>{c}</button>
                ))}
              </div>
            )}
            <button onClick={addToShelf} disabled={!selected} className="w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40">Добавить на полку</button>
          </div>
        </div>
      )}
    </div>
  )
}