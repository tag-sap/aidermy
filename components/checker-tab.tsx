'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, ScanSearch, Sparkles, Info, ArrowRight } from 'lucide-react'
import { Chip } from '@/components/chip'
import { QUICK_PRODUCTS, SKIN_TYPES } from '@/lib/products'
import { cn } from '@/lib/utils'
import type { SkinProfile } from '@/lib/store'

interface ProductSuggestion {
  name: string
  slug: string
}

export function CheckerTab({
  profile,
  profileComplete,
  onCheck,
  onGoToProfile,
  onStartQuiz,
  onInfoClick,
}: {
  profile: SkinProfile
  profileComplete: boolean
  onCheck: (product: string, skinType: string) => void
  onGoToProfile: () => void
  onStartQuiz?: () => void
  onInfoClick?: () => void
}) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)
  const [skinType, setSkinType] = useState(profile.skinType || '')
  const [suggestions, setSuggestions] = useState<ProductSuggestion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [popularProducts, setPopularProducts] = useState<Array<{ name: string, checks?: number, score?: number, slug?: string }>>([])
  const [popularSource, setPopularSource] = useState<'history' | 'database'>('history')

  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Автокомплит
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setSuggestions([])
      setHighlightedIndex(-1)
      return
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    const controller = new AbortController()
    abortControllerRef.current = controller
    setIsLoading(true)

    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/products?q=${encodeURIComponent(q)}`, {
          signal: controller.signal,
        })
        if (!res.ok) throw new Error('Ошибка загрузки')
        const data = await res.json()
        const sorted = (data.products || []).sort((a: ProductSuggestion, b: ProductSuggestion) => {
          const aLower = a.name.toLowerCase()
          const bLower = b.name.toLowerCase()
          const qLower = q.toLowerCase()
          const aStarts = aLower.startsWith(qLower)
          const bStarts = bLower.startsWith(qLower)
          if (aStarts && !bStarts) return -1
          if (!aStarts && bStarts) return 1
          return a.name.length - b.name.length
        })
        setSuggestions(sorted.slice(0, 8))
        setHighlightedIndex(-1)
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          console.error('Ошибка загрузки продуктов:', error)
          setSuggestions([])
        }
      } finally {
        setIsLoading(false)
      }
    }, 250)

    return () => {
      clearTimeout(timer)
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [query])

  // Популярные продукты
  useEffect(() => {
    const fetchPopular = async () => {
      try {
        const res = await fetch('/api/popular-products')
        if (res.ok) {
          const data = await res.json()
          setPopularProducts(data.products)
          setPopularSource(data.source)
        }
      } catch (error) {
        console.error('Ошибка загрузки популярных продуктов:', error)
      }
    }
    fetchPopular()
  }, [])

  const activeSkinType = profileComplete ? profile.skinType : skinType
  const canCheck = query.trim().length > 0 && activeSkinType.length > 0

  const handleCheck = () => {
    if (!canCheck) return
    onCheck(query.trim(), activeSkinType)
    setSuggestions([])
    setFocused(false)
  }

  const getGreeting = () => {
    const name = profile.name || ''
    const base = name ? `Привет, ${name}.` : 'Привет.'
    return `${base} Что проверяем?`
  }

  return (
    <div className="flex flex-col gap-4">
      {/* ЗАГОЛОВОК */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-normal text-foreground">
          {getGreeting()}
        </h1>
        <button
          onClick={onInfoClick}
          className="text-xs text-muted-foreground hover:text-primary transition-colors flex items-center gap-1"
        >
          <Info className="size-3" />
          Как это работает?
        </button>
      </div>

      {/* ПОИСК */}
      <section className="bg-white rounded-xl p-6 border border-gray-200">
        <h2 className="mb-3 text-sm font-normal uppercase tracking-[0.08em] text-muted-foreground">
          Поиск
        </h2>
        <div className="relative">
          <div className={cn(
            'flex items-center gap-2 rounded-xl border px-4 py-3 bg-white/50 transition-all',
            focused
              ? 'border-primary/60 shadow-[0_0_20px_rgba(108,60,225,0.08)]'
              : 'border-gray-200'
          )}>
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setTimeout(() => setFocused(false), 150)}
              placeholder="Название средства или состав..."
              className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
            />
            {query && (
              <button
                onClick={() => {
                  setQuery('')
                  setSuggestions([])
                  inputRef.current?.focus()
                }}
                className="text-muted-foreground/50 hover:text-foreground"
              >
                ✕
              </button>
            )}
          </div>

          {/* Подсказки */}
          {focused && (suggestions.length > 0 || isLoading) && (
            <ul className="absolute left-0 top-full mt-1 z-50 w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl max-h-64 overflow-y-auto">
              {isLoading && (
                <li className="px-4 py-2 text-sm text-muted-foreground text-center">
                  Загрузка...
                </li>
              )}
              {!isLoading && suggestions.length === 0 && query.trim().length >= 2 && (
                <li className="px-4 py-2 text-sm text-muted-foreground text-center">
                  Ничего не найдено
                </li>
              )}
              {!isLoading && suggestions.map((product, index) => (
                <li key={product.slug}>
                  <button
                    onMouseDown={() => {
                      setQuery(product.name)
                      setSuggestions([])
                      setFocused(false)
                    }}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    className={cn(
                      'w-full px-4 py-2.5 text-left text-sm transition-colors',
                      index === highlightedIndex
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-gray-50'
                    )}
                  >
                    {product.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* ТИП КОЖИ */}
      <section className="bg-white rounded-xl p-6 border border-gray-200">
        <h2 className="mb-3 text-sm font-normal uppercase tracking-[0.08em] text-muted-foreground">
          {profile.skinType ? 'Твой тип кожи' : 'Выбери тип кожи'}
        </h2>
        {!profile.skinType ? (
          <div className="flex flex-wrap gap-2">
            {SKIN_TYPES.map((t) => (
              <Chip
                key={t}
                label={t}
                active={skinType === t}
                onClick={() => setSkinType(t)}
              />
            ))}
            {onStartQuiz && (
              <button
                onClick={onStartQuiz}
                className="text-sm text-primary hover:underline ml-2"
              >
                <Sparkles className="inline size-3 mr-1" />
                Пройти опросник
              </button>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <span className="text-sm font-normal">{profile.skinType}</span>
            {onStartQuiz && (
              <button
                onClick={onStartQuiz}
                className="text-xs text-primary hover:underline"
              >
                Обновить
              </button>
            )}
          </div>
        )}
      </section>

      {/* КНОПКА ПРОВЕРИТЬ */}
      <button
        onClick={handleCheck}
        disabled={!canCheck}
        className={cn(
          'w-full py-3 rounded-xl bg-primary text-white font-normal transition-all',
          canCheck
            ? 'hover:bg-primary/90 active:scale-[0.98]'
            : 'opacity-40 cursor-not-allowed'
        )}
      >
        <ScanSearch className="inline size-4 mr-2" />
        Проверить
      </button>

      {/* ПОПУЛЯРНОЕ */}
      <section className="bg-white rounded-xl p-6 border border-gray-200">
        <h2 className="mb-3 text-sm font-normal uppercase tracking-[0.08em] text-muted-foreground">
          {popularSource === 'history' ? '⭐ Популярное' : '🏷️ Бренды'}
        </h2>
        <div className="flex flex-wrap gap-2">
          {popularProducts.map((p) => (
            <Chip
              key={p.name}
              label={p.name}
              variant="gold-outline"
              onClick={() => setQuery(p.name)}
            />
          ))}
          {popularProducts.length === 0 && (
            <p className="text-sm text-muted-foreground">Загрузка...</p>
          )}
        </div>
        {popularSource === 'history' && popularProducts.length > 0 && (
          <p className="text-[10px] text-muted-foreground/60 mt-2">
            Топ продуктов из ваших проверок
          </p>
        )}
      </section>

      {/* ЗАПОЛНИТЬ АНКЕТУ */}
      {!profileComplete && (
        <button
          onClick={onGoToProfile}
          className="flex items-center gap-2 text-sm text-primary hover:underline"
        >
          Заполни анкету для точных рекомендаций
          <ArrowRight className="size-4" />
        </button>
      )}
    </div>
  )
}