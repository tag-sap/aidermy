'use client'

import { useState, useEffect } from 'react'
import { Plus, X, Trash2, Sparkles, Search, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ShelfItem = {
  id: number
  product_id: number
  category: string
  name: string
  brand: string
  image_url: string
  slug: string
  ingredients: string
  score: number | null
}

type ShelfRoutine = {
  id: number
  name: string
  created_at: string
  compatibility: {
    overall_score: number
    conflicts: { a: string[]; b: string[] }[]
    duplicate_actives: { ingredient: string; count: number }[]
    repeated_ingredients: { ingredient: string; count: number }[]
    coverage: { present: string[]; missing: string[] }
  }
  items: ShelfItem[]
}

const CATEGORIES = ['Очищение', 'Тонер', 'Сыворотка', 'Крем', 'SPF', 'Маска']

export function ShelfTab({ onCheck }: { onCheck: (product: string) => void }) {
  const [routines, setRoutines] = useState<ShelfRoutine[]>([])
  const [individual, setIndividual] = useState<ShelfItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<any | null>(null)
  const [category, setCategory] = useState('')
  const [feedback, setFeedback] = useState('')
  const [openRoutine, setOpenRoutine] = useState<number | null>(null)
  const [showAnalysis, setShowAnalysis] = useState<number | null>(null)

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const loadShelf = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/shelf', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const data = await res.json()
        setRoutines(data.routines || [])
        setIndividual(data.individual || [])
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
    setRoutines((prev) => prev.map((r) => ({ ...r, items: r.items.filter((i) => i.id !== id) })))
    setIndividual((prev) => prev.filter((i) => i.id !== id))
    await fetch(`/api/shelf/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
    loadShelf()
  }

  const changeCategory = async (id: number, cat: string) => {
    setRoutines((prev) => prev.map((r) => ({ ...r, items: r.items.map((i) => (i.id === id ? { ...i, category: cat } : i)) })))
    setIndividual((prev) => prev.map((i) => (i.id === id ? { ...i, category: cat } : i)))
    await fetch(`/api/shelf/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ category: cat }),
    })
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
        ) : routines.length === 0 && individual.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="mb-3 flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Sparkles className="size-6" strokeWidth={1.5} />
            </div>
            <p className="text-sm text-muted-foreground/60">Полка пока пуста</p>
            <button onClick={openAdd} className="mt-3 text-xs text-primary hover:underline">Добавить первый продукт</button>
          </div>
        ) : (
          <div className="space-y-5">
            {routines.length > 0 && (
              <div className="space-y-2.5">
                {routines.map((r) => {
                  const open = openRoutine === r.id
                  const showA = showAnalysis === r.id
                  return (
                    <div key={r.id} className="rounded-2xl border border-white/40 bg-white/40 backdrop-blur-sm">
                      <button onClick={() => setOpenRoutine(open ? null : r.id)} className="flex w-full items-center gap-3 p-3 text-left">
                        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                          <Sparkles className="size-5" strokeWidth={1.5} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-foreground/90">{r.name}</p>
                          <p className="text-[10px] text-muted-foreground/50">{r.items.length} продукт(ов)</p>
                        </div>
                        <span className="shrink-0 text-xl font-light text-primary">{r.compatibility.overall_score}%</span>
                        <ChevronDown className={cn('size-4 shrink-0 text-muted-foreground/50 transition-transform', open && 'rotate-180')} />
                      </button>
                      {open && (
                        <div className="border-t border-gray-100 px-3 pb-3">
                          <div className="mt-2 space-y-1.5">
                            {r.items.map((item) => (
                              <div key={item.id} className="flex items-center gap-2 rounded-xl border border-white/40 bg-white/50 p-2">
                                <button onClick={() => onCheck(item.name)} className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white/70">
                                  {item.image_url ? <img src={item.image_url} alt="" className="h-full w-full object-contain p-1" /> : <Sparkles className="size-3.5 text-muted-foreground/30" />}
                                </button>
                                <div className="min-w-0 flex-1">
                                  <p className="truncate text-[11px] font-medium text-foreground/80">{item.name}</p>
                                  <p className="truncate text-[9px] text-muted-foreground/50">{item.brand}</p>
                                </div>
                                <select value={item.category} onChange={(e) => changeCategory(item.id, e.target.value)} className="max-w-[90px] rounded-lg border border-white/30 bg-white/40 px-1 py-0.5 text-[9px] text-foreground/60 focus:outline-none">
                                  <option value="">Категория…</option>
                                  {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
                                </select>
                                <button onClick={() => removeItem(item.id)} className="shrink-0 text-muted-foreground/50 hover:text-red-500">
                                  <Trash2 className="size-3.5" />
                                </button>
                              </div>
                            ))}
                          </div>
                          <button onClick={() => setShowAnalysis(showA ? null : r.id)} className="mt-2 w-full rounded-xl border border-primary/20 bg-primary/5 py-2 text-[11px] text-primary transition-colors hover:bg-primary/10">
                            {showA ? 'Скрыть анализ' : 'Анализ подбора'}
                          </button>
                          {showA && (
                            <div className="mt-2 space-y-1.5 rounded-xl bg-white/40 p-2.5 text-[10px]">
                              {r.compatibility.conflicts?.length > 0 && (
                                <p className="text-red-500/80">⚠ Конфликты: {r.compatibility.conflicts.map((c) => `${c.a.join('/')} + ${c.b.join('/')}`).join('; ')}</p>
                              )}
                              {r.compatibility.duplicate_actives?.length > 0 && (
                                <p className="text-amber-600/80">Дублируются активы: {r.compatibility.duplicate_actives.map((d) => d.ingredient).join(', ')}</p>
                              )}
                              {r.compatibility.repeated_ingredients?.length > 0 && (
                                <p className="text-muted-foreground/60">Повторяются ингредиенты: {r.compatibility.repeated_ingredients.slice(0, 5).map((d) => d.ingredient).join(', ')}</p>
                              )}
                              {(r.compatibility.coverage?.missing || []).length > 0 && (
                                <p className="text-muted-foreground/60">Не хватает шагов: {r.compatibility.coverage.missing.join(', ')}</p>
                              )}
                              {r.compatibility.conflicts?.length === 0 && r.compatibility.duplicate_actives?.length === 0 && (
                                <p className="text-emerald-600/70">Состав сочетается хорошо</p>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {individual.length > 0 && (
              <div>
                <h2 className="mb-2 text-[11px] font-medium text-muted-foreground/60">Отдельные продукты</h2>
                <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 lg:grid-cols-4">
                  {individual.map((item) => (
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
                        {item.score != null && item.score > 0 && <span className="mt-1.5 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[9px] text-primary">Проверено: {item.score}%</span>}
                      </button>
                      <select value={item.category} onChange={(e) => changeCategory(item.id, e.target.value)} className="mt-2 w-full rounded-lg border border-white/30 bg-white/40 px-1.5 py-1 text-[9px] text-foreground/60 focus:outline-none">
                        <option value="">Категория…</option>
                        {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
                      </select>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
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