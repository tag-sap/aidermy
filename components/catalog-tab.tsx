'use client'

import { useEffect, useRef, useState } from 'react'
import { Search, SlidersHorizontal, X, LoaderCircle, Sparkles, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

type Product = { name: string; brand: string; slug: string; image_url: string; category: string }
type Section = { key: string; title: string; products: Product[] }

export function CatalogTab({ onCheck }: { onCheck: (product: string) => void }) {
  const [sections, setSections] = useState<Section[]>([])
  const [loading, setLoading] = useState(true)
  const [showFilters, setShowFilters] = useState(false)
  const [category, setCategory] = useState('')
  const [brand, setBrand] = useState('')
  const [search, setSearch] = useState('')
  const [filtered, setFiltered] = useState<Product[]>([])
  const [filteredLoading, setFilteredLoading] = useState(false)
  const [categories, setCategories] = useState<string[]>([])
  const [brands, setBrands] = useState<string[]>([])
  const scrollRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const loadSections = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/catalog/sections')
      const data = await res.json()
      setSections(data.sections || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const loadMeta = async () => {
    try {
      const res = await fetch('/api/categories')
      const data = await res.json()
      setCategories(data.categories || [])
      setBrands(data.brands || [])
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    loadSections()
    loadMeta()
  }, [])

  const applyFilters = async () => {
    setFilteredLoading(true)
    try {
      const params = new URLSearchParams({ limit: '40' })
      if (category) params.append('category', category)
      if (brand) params.append('brand', brand)
      if (search.trim()) params.append('search', search.trim())
      const res = await fetch(`/api/catalog?${params}`)
      const data = await res.json()
      setFiltered((data.products || []).map((p: any) => {
        const parts = (p.name || '').split('\n').filter((x: string) => x.trim())
        return {
          name: parts.length > 1 ? parts.slice(1).join(' ') : (p.name || ''),
          brand: parts.length > 1 ? parts[0] : (p.brand || ''),
          slug: p.slug,
          image_url: p.image_url,
          category: p.category,
        }
      }))
    } catch (e) {
      console.error(e)
    } finally {
      setFilteredLoading(false)
    }
  }

  useEffect(() => {
    if (!search.trim()) {
      setFiltered([])
      return
    }
    const t = setTimeout(() => applyFilters(), 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search])

  const clearFilters = () => {
    setCategory('')
    setBrand('')
    setSearch('')
    setFiltered([])
  }

  const hasFilter = !!(category || brand || search.trim())

  const scroll = (key: string, dir: number) => {
    const el = scrollRefs.current[key]
    el?.scrollBy({ left: dir * 280, behavior: 'smooth' })
  }

  const ProductCard = ({ p }: { p: Product }) => (
    <button
      onClick={() => onCheck(p.name)}
      className="w-[150px] shrink-0 overflow-hidden rounded-2xl border border-white/40 bg-white/40 text-left backdrop-blur-sm transition-all hover:border-primary/30 hover:bg-white/60"
    >
      <div className="flex aspect-square items-center justify-center bg-white/50 p-2">
        {p.image_url ? (
          <img src={p.image_url} alt={p.name} className="h-full w-full object-contain" />
        ) : (
          <Sparkles className="size-5 text-muted-foreground/30" />
        )}
      </div>
      <div className="p-2.5">
        <p className="line-clamp-2 text-[11px] font-medium leading-snug text-foreground/80">{p.name}</p>
        <p className="mt-0.5 truncate text-[9px] text-muted-foreground/50">{p.brand}</p>
      </div>
    </button>
  )

  return (
    <div className="no-scrollbar h-full overflow-y-auto py-4">
      <div className="mb-3">
        <h1 className="text-xl font-light text-foreground">Проверить продукт</h1>
        <p className="mt-0.5 text-xs text-muted-foreground/70">Выберите средство — покажем, подходит ли оно вашей коже</p>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-gray-200/60 bg-white/50 px-3 py-2">
          <Search className="size-4 text-muted-foreground/40" />
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
            'flex shrink-0 items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-medium transition-colors',
            category || brand ? 'bg-primary text-white shadow-sm' : 'bg-primary/10 text-primary hover:bg-primary/20'
          )}
        >
          <SlidersHorizontal className="size-4" />
          Фильтры
        </button>
      </div>

      {hasFilter ? (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs text-muted-foreground/60">Результаты</span>
            <button onClick={clearFilters} className="text-[11px] text-primary hover:underline">Сбросить</button>
          </div>
          {filteredLoading ? (
            <div className="flex justify-center py-10"><LoaderCircle className="size-5 animate-spin text-primary" /></div>
          ) : filtered.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground/50">Ничего не найдено</div>
          ) : (
            <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 lg:grid-cols-4">
              {filtered.map((p) => <ProductCard key={p.slug} p={p} />)}
            </div>
          )}
        </div>
      ) : loading ? (
        <div className="flex justify-center py-16"><LoaderCircle className="size-6 animate-spin text-primary" /></div>
      ) : (
        <div className="space-y-6">
          {sections.map((s) => (
            <div key={s.key}>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-medium text-foreground/90">{s.title}</h2>
                <div className="flex gap-1">
                  <button onClick={() => scroll(s.key, -1)} className="rounded-full border border-gray-200 p-1 text-muted-foreground/50 transition-colors hover:text-primary"><ChevronLeft className="size-4" /></button>
                  <button onClick={() => scroll(s.key, 1)} className="rounded-full border border-gray-200 p-1 text-muted-foreground/50 transition-colors hover:text-primary"><ChevronRight className="size-4" /></button>
                </div>
              </div>
              <div ref={(el) => { scrollRefs.current[s.key] = el }} className="no-scrollbar flex gap-2.5 overflow-x-auto pb-1">
                {s.products.map((p) => <ProductCard key={p.slug} p={p} />)}
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="h-24" />

      {showFilters && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" onClick={() => setShowFilters(false)} />
          <div className="relative w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-base font-normal text-foreground">Фильтры</h3>
              <button onClick={() => setShowFilters(false)} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground/60">Категория</label>
                <select value={category} onChange={(e) => setCategory(e.target.value)} className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:border-primary/40 focus:outline-none">
                  <option value="">Все категории</option>
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground/60">Бренд</label>
                <select value={brand} onChange={(e) => setBrand(e.target.value)} className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:border-primary/40 focus:outline-none">
                  <option value="">Все бренды</option>
                  {brands.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
              <button onClick={() => { setShowFilters(false); applyFilters() }} className="w-full rounded-xl bg-primary py-2.5 text-sm text-white transition-colors hover:bg-primary/90">
                Применить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
