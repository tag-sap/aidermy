'use client'

import { useState, useEffect } from 'react'
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

  // === АВТОКОМПЛИТ ИЗ БД ===
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setSuggestions([])
      return
    }

    setIsLoading(true)
    const fetchProducts = async () => {
      try {
        const res = await fetch(`/api/products?q=${encodeURIComponent(q)}`)
        const data = await res.json()
        setSuggestions(data.products || [])
      } catch (error) {
        console.error('Ошибка загрузки продуктов:', error)
        setSuggestions([])
      } finally {
        setIsLoading(false)
      }
    }

    const timer = setTimeout(fetchProducts, 300)
    return () => clearTimeout(timer)
  }, [query])

  const activeSkinType = profileComplete ? profile.skinType : skinType
  const canCheck = query.trim().length > 0 && activeSkinType.length > 0

  const handleCheck = () => {
    if (!canCheck) return
    onCheck(query.trim(), activeSkinType)
  }

  const getGreeting = () => {
    const name = profile.name || ''
    const base = name ? `Привет, ${name}.` : 'Привет.'
    return `${base} Что проверяем?`
  }

  return (
    <div className="flex flex-col items-center gap-6 text-center">
      {/* === ПРИВЕТСТВИЕ === */}
      <div className="w-full max-w-md min-h-[28px]">
        <WaveText
          text={getGreeting()}
          className="text-base font-semibold text-foreground"
          startDelay={200}
        />
      </div>

      {/* === БЛОК: ПОИСК === */}
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
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => setTimeout(() => setFocused(false), 150)}
                placeholder="Название средства…"
                className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
                aria-label="Название средства"
              />
            </div>
          </div>
        </div>

        {focused && suggestions.length > 0 && (
          <ul className="absolute left-0 top-[calc(100%-8px)] z-50 w-full overflow-hidden rounded-b-md border border-primary/15 bg-white shadow-xl">
            {isLoading && (
              <li className="px-4 py-2 text-sm text-muted-foreground">Загрузка...</li>
            )}
            {!isLoading &&
              suggestions.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    onMouseDown={() => {
                      setQuery(s)
                      setFocused(false)
                    }}
                    className="w-full px-4 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-primary/10"
                  >
                    {s}
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>

      {/* === БЛОК: ТИП КОЖИ === */}
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

      {/* === КНОПКА ПРОВЕРИТЬ === */}
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

      {/* === БЛОК: ПОПУЛЯРНОЕ === */}
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

      {/* === БЛОК: АНКЕТА === */}
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