'use client'

import { useCallback, useEffect, useState } from 'react'
import { Plus, LoaderCircle, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ShelfItem } from '@/lib/shelf'
import { ShelfAddModal } from '@/components/shelf-add-modal'
import { ProductModal } from '@/components/product-modal'

type Category = { key: string; title: string; items: ShelfItem[] }
type Cabinet = {
  key: string
  title: string
  has_scoring: boolean
  compatibility: number | null
  categories: Category[]
}

function scoreBadge(s: number | null) {
  if (s == null) return ''
  if (s >= 80) return 'bg-[#4E9F6E]/10 text-[#4E9F6E]'
  if (s >= 60) return 'bg-[#6FBF8D]/15 text-[#4E9F6E]'
  if (s >= 40) return 'bg-[#8B7CF6]/10 text-[#6B5CD6]'
  return 'bg-[#B7A7F0]/15 text-[#8B7CF6]'
}

export function ShelfTab({ onCheck }: { onCheck: (product: string) => void }) {
  const [cabinets, setCabinets] = useState<Cabinet[]>([])
  const [loading, setLoading] = useState(true)
  const [addContext, setAddContext] = useState<{ cabinet: string; category: string } | null>(null)
  const [detailSlug, setDetailSlug] = useState<string | null>(null)

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const loadShelf = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/shelf', { headers: { Authorization: `Bearer ${token}` } })
      if (res.ok) {
        const data = await res.json()
        setCabinets(data.cabinets || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    loadShelf()
  }, [loadShelf])

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoaderCircle className="size-6 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="no-scrollbar h-full overflow-y-auto px-1 py-5 pb-28">
      <header className="mb-6">
        <h1 className="text-3xl font-light text-foreground">Моя полка</h1>
        <p className="mt-1 text-sm text-muted-foreground/60">Твоя персональная система косметики</p>
      </header>

      <div className="space-y-8">
        {cabinets.map((cab) => (
          <section key={cab.key}>
            <div className="mb-3 flex items-end justify-between gap-3">
              <h2 className="text-xl font-light text-foreground/90">{cab.title}</h2>
              {cab.has_scoring && (
                <div className="text-right">
                  <p className="text-[9px] uppercase tracking-wide text-muted-foreground/50">Совместимость ухода</p>
                  <p className={cn('text-lg font-light', cab.compatibility != null ? 'text-primary' : 'text-muted-foreground/40')}>
                    {cab.compatibility != null ? `${cab.compatibility}%` : '—'}
                  </p>
                </div>
              )}
            </div>

            <div className="space-y-4">
              {cab.categories.map((cat) => (
                <div key={cat.key}>
                  <div className="mb-2 flex items-center justify-between">
                    <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground/60">{cat.title}</h3>
                    <button
                      onClick={() => setAddContext({ cabinet: cab.key, category: cat.key })}
                      className="flex size-6 items-center justify-center rounded-full border border-gray-200 text-muted-foreground/60 transition-colors hover:border-primary/40 hover:text-primary"
                      aria-label={`Добавить в ${cat.title}`}
                    >
                      <Plus className="size-3.5" />
                    </button>
                  </div>

                  {cat.items.length === 0 ? (
                    <button
                      onClick={() => setAddContext({ cabinet: cab.key, category: cat.key })}
                      className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-gray-200/70 py-4 text-xs text-muted-foreground/40 transition-colors hover:border-primary/30 hover:text-primary/60"
                    >
                      <Plus className="size-3.5" />
                      Добавить продукт
                    </button>
                  ) : (
                    <div className="no-scrollbar flex gap-2.5 overflow-x-auto pb-1">
                      {cat.items.map((item) => (
                        <button
                          key={item.id}
                          onClick={() => setDetailSlug(item.slug)}
                          className="w-[130px] shrink-0 overflow-hidden rounded-2xl border border-white/40 bg-white/60 text-left transition-transform hover:-translate-y-0.5"
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
                            {item.score != null && (
                              <span className={cn('mt-1.5 inline-block rounded-full px-1.5 py-0.5 text-[10px] font-medium', scoreBadge(item.score))}>
                                {item.score}%
                              </span>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      {addContext && (
        <ShelfAddModal
          cabinet={addContext.cabinet}
          category={addContext.category}
          onClose={() => setAddContext(null)}
          onAdded={loadShelf}
        />
      )}

      {detailSlug && (
        <ProductModal
          slug={detailSlug}
          onClose={() => setDetailSlug(null)}
          onCheck={onCheck}
          onChanged={loadShelf}
        />
      )}
    </div>
  )
}
