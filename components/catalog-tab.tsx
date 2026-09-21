'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Search, X, LoaderCircle, Sparkles, ArrowUp, SlidersHorizontal } from 'lucide-react'
import { cn, capitalizeFirst } from '@/lib/utils'

type Product = { name: string; brand: string; slug: string; image_url: string; category: string }

const PAGE = 40

function normalize(p: any): Product {
  const parts = (p.name || '').split('\n').filter((x: string) => x.trim())
  return {
    name: capitalizeFirst(parts.length > 1 ? parts.slice(1).join(' ') : (p.name || '').trim()),
    brand: capitalizeFirst(parts.length > 1 ? parts[0] : (p.brand || '')),
    slug: p.slug || '',
    image_url: p.image_url || '',
    category: p.category || '',
  }
}

export function CatalogTab({
  onOpenProduct,
  initialBrand,
  initialCat,
  filterKey,
}: {
  onOpenProduct: (slug: string) => void
  initialBrand?: string
  initialCat?: string
  filterKey?: number
}) {
  const [products, setProducts] = useState<Product[]>([])
  const [letters, setLetters] = useState<string[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [activeLetter, setActiveLetter] = useState('')
  const [category, setCategory] = useState('')
  const [brand, setBrand] = useState('')
  const [cat, setCat] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [showScrollTop, setShowScrollTop] = useState(false)
  const [showFilters, setShowFilters] = useState(false)

  const rootRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const offsetRef = useRef(0)
  const loadingRef = useRef(false)
  const requestIdRef = useRef(0)

  useEffect(() => {
    fetch('/api/catalog/letters')
      .then((r) => r.json())
      .then((d) => setLetters(d.letters || []))
      .catch(() => {})
    fetch('/api/categories')
      .then((r) => r.json())
      .then((d) => setCategories(d.categories || []))
      .catch(() => {})
  }, [])

  const buildParams = (offset: number) => {
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset), sort: 'alpha' })
    if (category) params.append('category', category)
    if (brand) params.append('brand', brand)
    if (cat) params.append('cat', cat)
    if (activeLetter) params.append('letter', activeLetter)
    if (search.trim()) params.append('search', search.trim())
    return params
  }

  // Внешний фильтр (переход по бренду/категории из карточки товара).
  useEffect(() => {
    setBrand(initialBrand || '')
    setCat(initialCat || '')
    setCategory('')
    setActiveLetter('')
    setSearch('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey])

  useEffect(() => {
    const requestId = ++requestIdRef.current
    loadingRef.current = true
    setLoading(true)
    offsetRef.current = 0
    setHasMore(true)

    fetch(`/api/catalog?${buildParams(0)}`)
      .then((r) => r.json())
      .then((data) => {
        if (requestId !== requestIdRef.current) return
        const items = (data.products || []).map(normalize)
        setProducts(items)
        offsetRef.current = items.length
        setHasMore(items.length === PAGE)
      })
      .catch(() => {})
      .finally(() => {
        if (requestId === requestIdRef.current) {
          loadingRef.current = false
          setLoading(false)
        }
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLetter, category, search, brand, cat])

  const loadMore = useCallback(() => {
    if (loadingRef.current || !hasMore) return
    loadingRef.current = true
    setLoadingMore(true)

    fetch(`/api/catalog?${buildParams(offsetRef.current)}`)
      .then((r) => r.json())
      .then((data) => {
        const items = (data.products || []).map(normalize)
        setProducts((prev) => [...prev, ...items])
        offsetRef.current += items.length
        setHasMore(items.length === PAGE)
      })
      .catch(() => {})
      .finally(() => {
        loadingRef.current = false
        setLoadingMore(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLetter, category, search, hasMore, brand, cat])

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) loadMore()
      },
      { rootMargin: '300px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [loadMore])

  useEffect(() => {
    const main = rootRef.current?.closest('main')
    if (!main) return
    const onScroll = () => setShowScrollTop(main.scrollTop > 400)
    main.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => main.removeEventListener('scroll', onScroll)
  }, [])

  const scrollToTop = () => {
    rootRef.current?.closest('main')?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const toggleLetter = (letter: string) => {
    setActiveLetter((prev) => (prev === letter ? '' : letter))
  }

  const grouped: { letter: string; items: Product[] }[] = []
  for (const p of products) {
    const letter = (p.name.trim().charAt(0) || '#').toUpperCase()
    const last = grouped[grouped.length - 1]
    if (last && last.letter === letter) {
      last.items.push(p)
    } else {
      grouped.push({ letter, items: [p] })
    }
  }

  return (
    <div ref={rootRef} className="relative">
      {/* Поиск + алфавит — фиксированы под заголовком «Каталог» */}
      <div className="sticky top-[48px] z-10 -mx-4 border-b border-gray-200/50 bg-background px-4 pb-2 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-xl border border-gray-200/60 bg-white/60 px-3 py-2">
            <Search className="size-4 shrink-0 text-muted-foreground/40" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по названию…"
              className="w-full bg-transparent text-sm focus:outline-none"
            />
            {search && (
              <button onClick={() => setSearch('')} className="text-muted-foreground/40 hover:text-foreground">
                <X className="size-3.5" />
              </button>
            )}
          </div>
          <button
            onClick={() => setShowFilters(true)}
            className={cn(
              'flex shrink-0 items-center gap-1.5 rounded-xl border px-3 py-2 text-sm font-medium transition-colors',
              category || activeLetter || brand || cat
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-gray-200/60 bg-white/60 text-muted-foreground/70 hover:text-primary',
            )}
          >
            <SlidersHorizontal className="size-4" />
            Фильтр
            {(category || activeLetter || brand || cat) && (
              <span className="flex size-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">
                1
              </span>
            )}
          </button>
        </div>

        {(category || activeLetter || brand || cat) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {brand && (
              <button onClick={() => setBrand('')} className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">
                Бренд: {brand} <X className="size-3" />
              </button>
            )}
            {cat && (
              <button onClick={() => setCat('')} className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">
                {cat} <X className="size-3" />
              </button>
            )}
            {category && (
              <button onClick={() => setCategory('')} className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">
                {category} <X className="size-3" />
              </button>
            )}
            {activeLetter && (
              <button onClick={() => setActiveLetter('')} className="flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs text-primary">
                Буква: {activeLetter.toUpperCase()} <X className="size-3" />
              </button>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <LoaderCircle className="size-6 animate-spin text-primary" />
        </div>
      ) : products.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground/50">
          {search || activeLetter || category || brand || cat ? 'Ничего не найдено' : 'В каталоге пока нет продуктов'}
        </div>
      ) : (
        <div className="pt-3">
          {grouped.map((group) => (
            <div key={group.letter}>
              <div className="px-2 py-1 text-xs font-semibold text-primary">{group.letter}</div>
              <div className="grid grid-cols-1 gap-2 pb-3 md:grid-cols-2 lg:grid-cols-3">
                {group.items.map((p) => (
                  <button
                    key={p.slug}
                    onClick={() => onOpenProduct(p.slug)}
                    className="flex w-full min-w-0 items-center gap-3 rounded-2xl border border-gray-100 bg-white p-2.5 text-left transition-colors hover:border-primary/30 hover:bg-primary/5"
                  >
                    <div className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-gray-50">
                      {p.image_url ? (
                        <img src={p.image_url} alt="" className="h-full w-full object-contain p-1" />
                      ) : (
                        <Sparkles className="size-5 text-muted-foreground/30" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      {p.brand && <p className="truncate text-[10px] uppercase tracking-wide text-muted-foreground/50">{p.brand}</p>}
                      <p className="truncate text-sm font-normal text-foreground">{p.name}</p>
                      {p.category && <p className="truncate text-xs text-muted-foreground/50">{p.category}</p>}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div ref={sentinelRef} className="h-4" />
      {loadingMore && (
        <div className="flex justify-center py-4">
          <LoaderCircle className="size-5 animate-spin text-primary" />
        </div>
      )}

      {showScrollTop && (
        <button
          onClick={scrollToTop}
          aria-label="Наверх"
          className="fixed bottom-24 right-4 z-40 flex size-11 items-center justify-center rounded-full border border-primary/20 bg-white text-primary shadow-lg transition-colors hover:bg-primary/5"
        >
          <ArrowUp className="size-5" />
        </button>
      )}

      {showFilters && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={() => setShowFilters(false)}>
          <div className="max-h-[85dvh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-4 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-normal text-foreground">Фильтр</h3>
              <button onClick={() => setShowFilters(false)} className="text-muted-foreground hover:text-foreground">
                <X className="size-4" />
              </button>
            </div>

            <p className="mb-1.5 text-xs font-medium text-muted-foreground/70">Категория</p>
            <div className="mb-3 flex flex-wrap gap-1.5">
              <button
                onClick={() => setCategory('')}
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                  category === '' ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-200 text-muted-foreground hover:border-primary/40',
                )}
              >
                Все
              </button>
              {categories.map((c) => (
                <button
                  key={c}
                  onClick={() => setCategory(c)}
                  className={cn(
                    'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                    category === c ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-200 text-muted-foreground hover:border-primary/40',
                  )}
                >
                  {c}
                </button>
              ))}
            </div>

            <p className="mb-1.5 text-xs font-medium text-muted-foreground/70">Буква</p>
            <div className="mb-3 flex flex-wrap gap-1.5">
              <button
                onClick={() => setActiveLetter('')}
                className={cn(
                  'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                  activeLetter === '' ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-200 text-muted-foreground hover:border-primary/40',
                )}
              >
                Все
              </button>
              {letters.map((letter) => (
                <button
                  key={letter}
                  onClick={() => setActiveLetter(letter)}
                  className={cn(
                    'rounded-full border px-2.5 py-1 text-xs font-medium transition-colors',
                    activeLetter === letter ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-200 text-muted-foreground hover:border-primary/40',
                  )}
                >
                  {letter.toUpperCase()}
                </button>
              ))}
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  setCategory('')
                  setActiveLetter('')
                  setShowFilters(false)
                }}
                className="flex-1 rounded-xl border border-gray-200 py-2.5 text-sm text-foreground/70 transition-colors hover:bg-gray-50"
              >
                Сбросить
              </button>
              <button onClick={() => setShowFilters(false)} className="flex-1 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90">
                Применить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
