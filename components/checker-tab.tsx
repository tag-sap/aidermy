'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, ScanSearch, ArrowRight, Sparkles, Info } from 'lucide-react'
import { Chip } from '@/components/chip'
import { ScrambleText } from '@/components/scramble-text'
import { WaveText } from '@/components/wave-text'
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

  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const [popularProducts, setPopularProducts] = useState<Array<{ name: string, checks?: number, score?: number, slug?: string }>>([])
  const [popularSource, setPopularSource] = useState<'history' | 'database'>('history')

  // === АВТОКОМПЛИТ С ДЕБАУНСОМ И ОТМЕННОЙ ЗАПРОСОВ ===
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

  // === КЛАВИАТУРНАЯ НАВИГАЦИЯ ===
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!suggestions.length) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightedIndex((prev) =>
          prev < suggestions.length - 1 ? prev + 1 : prev
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : -1))
        break
      case 'Enter':
        e.preventDefault()
        if (highlightedIndex >= 0 && highlightedIndex < suggestions.length) {
          setQuery(suggestions[highlightedIndex].name)
          setSuggestions([])
          setFocused(false)
          setHighlightedIndex(-1)
        } else if (canCheck) {
          handleCheck()
        }
        break
      case 'Escape':
        setSuggestions([])
        setFocused(false)
        setHighlightedIndex(-1)
        break
    }
  }
  // === ПОПУЛЯРНЫЕ ПРОДУКТЫ ===
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

  const handleSelectSuggestion = (product: ProductSuggestion) => {
    setQuery(product.name)
    setSuggestions([])
    setFocused(false)
    setHighlightedIndex(-1)
  }

  const getGreeting = () => {
    const name = profile.name || ''
    const base = name ? `Привет, ${name}.` : 'Привет.'
    return `${base} Что проверяем?`
  }

  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <div className="w-full max-w-md min-h-[28px] flex items-center justify-between">
        <WaveText
          text={getGreeting()}
          className="text-base font-normal text-foreground"
          startDelay={200}
        />
        <button
          onClick={onInfoClick}
          className="text-xs text-muted-foreground hover:text-primary transition-colors flex items-center gap-1 flex-shrink-0"
        >
          <Info className="size-3" />
          Как это работает?
        </button>
      </div>

      <div className="relative w-full max-w-md">
        <div className="card-dense relative">
          <p className="text-xs font-normal uppercase tracking-[0.3em] text-muted-foreground">
            Поиск
          </p>
          <div className="mt-3">
            <div
              className={cn(
                'flex items-center gap-2 rounded-md border px-4 py-3 text-left transition-all',
                focused
                  ? 'border-primary/60 shadow-[0_0_20px_rgba(255,79,0,0.08)]'
                  : 'border-primary/15',
              )}
            >
              <Search className="size-4 shrink-0 text-muted-foreground" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => setFocused(true)}
                onBlur={() => setTimeout(() => setFocused(false), 150)}
                placeholder="Название средства…"
                className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
                aria-label="Название средства"
              />
              {query && (
                <button
                  type="button"
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
          </div>
        </div>

        {focused && (suggestions.length > 0 || isLoading) && (
          <ul
            ref={listRef}
            className="absolute left-0 top-[calc(100%-8px)] z-50 w-full overflow-hidden rounded-b-md border border-primary/15 bg-white shadow-xl max-h-64 overflow-y-auto"
          >
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
            {!isLoading &&
              suggestions.map((product, index) => (
                <li key={product.slug}>
                  <button
                    type="button"
                    onMouseDown={() => handleSelectSuggestion(product)}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    className={cn(
                      'w-full px-4 py-2.5 text-left text-sm text-foreground transition-colors',
                      index === highlightedIndex
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-primary/5'
                    )}
                  >
                    {highlightQuery(product.name, query)}
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>

      {/* Блок выбора типа кожи ИЛИ опросник */}
      {!profile.skinType ? (
        <section className="card-dense w-full max-w-md">
          <p className="text-xs font-normal uppercase tracking-[0.3em] text-muted-foreground">
            Выбери тип кожи
          </p>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {SKIN_TYPES.map((t) => (
              <Chip
                key={t}
                label={t}
                active={skinType === t}
                onClick={() => setSkinType(t)}
              />
            ))}
          </div>

          {/* Кнопка опросника */}
          {onStartQuiz && (
            <div className="mt-4">
              <button
                onClick={onStartQuiz}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg border-2 border-dashed border-primary/30 text-sm font-normal text-primary hover:bg-primary/5 transition-colors"
              >
                <Sparkles className="size-4" />
                Пройти опросник для точного определения
              </button>
            </div>
          )}
        </section>
      ) : (
        <div className="w-full max-w-md text-center">
          <p className="text-sm text-muted-foreground">
            Тип кожи: <span className="font-normal text-foreground">{profile.skinType}</span>
          </p>
          <p className="text-xs text-muted-foreground/70">
            {profile.skinTypeDetermined ? '✅ Определено автоматически' : '✅ Из анкеты'}
          </p>

          {/* Кнопка перепройти опросник */}
          {onStartQuiz && (
            <button
              onClick={onStartQuiz}
              className="mt-2 text-xs text-primary hover:underline"
            >
              🔄 Пройти опросник заново
            </button>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={handleCheck}
        disabled={!canCheck}
        className={cn(
          'btn-primary w-full max-w-md flex items-center justify-center gap-2',
          !canCheck && 'opacity-40 cursor-not-allowed',
        )}
      >
        <ScanSearch className="size-5" />
        Проверить
      </button>

      <section className="card-soft w-full max-w-md">
        <p className="text-[11px] font-medium uppercase tracking-[0.3em] text-muted-foreground/80">
          {popularSource === 'history' ? '⭐ Популярное' : '🏷️ Бренды'}
        </p>
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {popularProducts.map((p) => (
            <Chip
              key={p.name}
              label={p.name}
              variant="gold-outline"
              onClick={() => setQuery(p.name)}
            />
          ))}
          {popularProducts.length === 0 && (
            <p className="text-xs text-muted-foreground">Загрузка...</p>
          )}
        </div>
        {popularSource === 'history' && popularProducts.length > 0 && (
          <p className="text-[10px] text-muted-foreground/60 mt-2">
            Топ продуктов из ваших проверок
          </p>
        )}
      </section>
      {!profileComplete && (
        <button
          type="button"
          onClick={onGoToProfile}
          className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-4 py-3 text-sm font-normal text-primary transition-colors hover:bg-primary/10"
        >
          Заполни анкету кожи для точных рекомендаций
          <ArrowRight className="size-4" />
        </button>
      )}
    </div>
  )
}

// === ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОДСВЕТКИ ===
function highlightQuery(text: string, query: string) {
  if (!query.trim()) return text

  const index = text.toLowerCase().indexOf(query.toLowerCase())
  if (index === -1) return text

  return (
    <>
      {text.slice(0, index)}
      <span className="font-normal text-primary">{text.slice(index, index + query.length)}</span>
      {text.slice(index + query.length)}
    </>
  )
}