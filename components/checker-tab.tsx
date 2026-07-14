'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, ScanSearch, ArrowRight } from 'lucide-react'
import { Chip } from '@/components/chip'
import { ScrambleText } from '@/components/scramble-text'
import { WaveText } from '@/components/wave-text'
import { QUICK_PRODUCTS, SKIN_TYPES } from '@/lib/products'
import { cn } from '@/lib/utils'
import type { SkinProfile } from '@/lib/store'

export function CheckerTab({
  profile,
  profileComplete,
  onCheck,
  onGoToProfile,
}: {
  profile: SkinProfile
  profileComplete: boolean
  onCheck: (product: string, skinType: string) => void
  onGoToProfile: () => void
}) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)
  const [skinType, setSkinType] = useState(profile.skinType || '')
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)

  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // === АВТОКОМПЛИТ С ДЕБАУНСОМ И ОТМЕННОЙ ЗАПРОСОВ ===
  useEffect(() => {
    const q = query.trim()

    // 1. Не показываем подсказки, если меньше 2 символов
    if (q.length < 2) {
      setSuggestions([])
      setHighlightedIndex(-1)
      return
    }

    // 2. Отменяем предыдущий запрос
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    // 3. Создаём новый контроллер
    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsLoading(true)

    // 4. Дебаунс — ждём 250ms после последнего ввода
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/products?q=${encodeURIComponent(q)}`, {
          signal: controller.signal,
        })

        if (!res.ok) throw new Error('Ошибка загрузки')

        const data = await res.json()

        // 5. Сортируем по релевантности
        const sorted = (data.products || []).sort((a: string, b: string) => {
          const aLower = a.toLowerCase()
          const bLower = b.toLowerCase()
          const qLower = q.toLowerCase()

          // Сначала те, что начинаются с запроса
          const aStarts = aLower.startsWith(qLower)
          const bStarts = bLower.startsWith(qLower)
          if (aStarts && !bStarts) return -1
          if (!aStarts && bStarts) return 1

          // Потом по длине (короткие названия выше)
          return a.length - b.length
        })

        // 6. Ограничиваем количество (не больше 8)
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
          setQuery(suggestions[highlightedIndex])
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

  const activeSkinType = profileComplete ? profile.skinType : skinType
  const canCheck = query.trim().length > 0 && activeSkinType.length > 0

  const handleCheck = () => {
    if (!canCheck) return
    onCheck(query.trim(), activeSkinType)
    setSuggestions([])
    setFocused(false)
  }

  const handleSelectSuggestion = (s: string) => {
    setQuery(s)
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
      <div className="w-full max-w-md min-h-[28px]">
        <WaveText
          text={getGreeting()}
          className="text-base font-semibold text-foreground"
          startDelay={200}
        />
      </div>

      <div className="relative w-full max-w-md">
        <div className="card-dense relative">
          <div className="bubble-1 bubble" />
          <div className="bubble-2 bubble" />
          <div className="bubble-3 bubble" />
          <div className="bubble-4 bubble" />
          <div className="bubble-5 bubble" />
          <div className="bubble-6 bubble" />

          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
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
              suggestions.map((s, index) => (
                <li key={s}>
                  <button
                    type="button"
                    onMouseDown={() => handleSelectSuggestion(s)}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    className={cn(
                      'w-full px-4 py-2.5 text-left text-sm text-foreground transition-colors',
                      index === highlightedIndex
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-primary/5'
                    )}
                  >
                    {highlightQuery(s, query)}
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>

      {!profile.skinType && (
        <section className="card-dense w-full max-w-md">
          <div className="bubble-1 bubble" />
          <div className="bubble-2 bubble" />
          <div className="bubble-3 bubble" />
          <div className="bubble-4 bubble" />
          <div className="bubble-5 bubble" />
          <div className="bubble-6 bubble" />

          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
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
        </section>
      )}

      {profile.skinType && (
        <div className="w-full max-w-md text-center">
          <p className="text-sm text-muted-foreground">
            Тип кожи: <span className="font-semibold text-foreground">{profile.skinType}</span>
          </p>
          <p className="text-xs text-muted-foreground/70">
            (из анкеты)
          </p>
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
        <div className="bubble-1 bubble" />
        <div className="bubble-2 bubble" />
        <div className="bubble-3 bubble" />

        <p className="text-[11px] font-medium uppercase tracking-[0.3em] text-muted-foreground/80">
          Популярное
        </p>
        <div className="mt-3 flex flex-wrap justify-center gap-2">
          {QUICK_PRODUCTS.map((p) => (
            <Chip
              key={p}
              label={p}
              variant="gold-outline"
              onClick={() => setQuery(p)}
            />
          ))}
        </div>
      </section>

      {!profileComplete && (
        <button
          type="button"
          onClick={onGoToProfile}
          className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
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
      <span className="font-bold text-primary">{text.slice(index, index + query.length)}</span>
      {text.slice(index + query.length)}
    </>
  )
}