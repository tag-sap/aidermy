cat > components/checker-tab.tsx << 'EOF'
'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, ScanSearch, Sparkles, Info, ArrowRight, Gem } from 'lucide-react'
import { Chip } from '@/components/chip'
import { SKIN_TYPES } from '@/lib/products'
import { cn } from '@/lib/utils'
import type { SkinProfile } from '@/lib/store'

interface ProductSuggestion {
  name: string
  slug: string
}

// === БЕГУЩИЙ ТЕКСТ ===
function MarqueeText({ text, className }: { text: string; className?: string }) {
  const [isOverflowing, setIsOverflowing] = useState(false)
  const textRef = useRef<HTMLSpanElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (textRef.current && containerRef.current) {
      setIsOverflowing(textRef.current.scrollWidth > containerRef.current.clientWidth)
    }
  }, [text])

  return (
    <div ref={containerRef} className={cn('overflow-hidden relative w-full', className)}>
      <div className={cn(
        'whitespace-nowrap inline-block',
        isOverflowing && 'animate-marquee'
      )}>
        <span ref={textRef}>{text}</span>
        {isOverflowing && <span className="ml-8">{text}</span>}
      </div>
    </div>
  )
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
  const [popularProducts, setPopularProducts] = useState<Array<{name: string, checks?: number, score?: number, slug?: string}>>([])
  const [popularSource, setPopularSource] = useState<'history' | 'database'>('history')
  const [isVisible, setIsVisible] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Анимация появления
  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), 50)
    return () => clearTimeout(timer)
  }, [])

  // Автокомплит
  useEffect(() => {
    const q = query.trim()
    if (q.length < 2) {
      setSuggestions([])
      setHighlightedIndex(-1)
      return
    }

    if (abortControllerRef.current) abortControllerRef.current.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller
    setIsLoading(true)

    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/products?q=${encodeURIComponent(q)}`, { signal: controller.signal })
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
      if (abortControllerRef.current) abortControllerRef.current.abort()
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

  const cardStyle = "relative overflow-hidden bg-gradient-to-br from-primary/10 via-primary/5 to-transparent rounded-2xl p-5 border border-primary/20 backdrop-blur-sm hover:shadow-md transition-shadow"

  return (
    <div className="flex flex-col gap-5 max-w-md mx-auto">
      {/* КАРТОЧКА 1 - ПРИВЕТСТВИЕ */}
      <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-1')}>
        <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
        <div className="relative">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-normal text-foreground tracking-tight">{getGreeting()}</h1>
            <button onClick={onInfoClick} className="px-3 py-1.5 rounded-full bg-white/50 text-xs text-muted-foreground hover:text-primary hover:bg-white transition-colors border border-gray-200/50 backdrop-blur-sm">
              <Info className="inline size-3 mr-1" />Как это работает
            </button>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">AI проанализирует состав и скажет, подходит ли он тебе</p>
        </div>
      </div>

      {/* КАРТОЧКА 2 - ПОИСК */}
      <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-2')}>
        <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
        <div className="relative">
          <label className="block text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground mb-3">Найти средство</label>
          <div className="relative">
            <div className={cn(
              'flex items-center gap-3 rounded-xl border px-4 py-3 bg-white/50 transition-all',
              focused ? 'border-primary/50 bg-white shadow-[0_0_30px_rgba(108,60,225,0.06)]' : 'border-gray-200/50 hover:border-gray-300'
            )}>
              <Search className="size-4 shrink-0 text-muted-foreground" />
              <input ref={inputRef} value={query} onChange={(e) => setQuery(e.target.value)} onFocus={() => setFocused(true)} onBlur={() => setTimeout(() => setFocused(false), 150)} placeholder="Введи название или состав..." className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/60 focus:outline-none text-sm" />
              {query && <button onClick={() => { setQuery(''); setSuggestions([]); inputRef.current?.focus() }} className="p-1 rounded-full hover:bg-gray-100 transition-colors">✕</button>}
            </div>
            {focused && (suggestions.length > 0 || isLoading) && (
              <ul className="absolute left-0 top-full mt-2 z-50 w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl max-h-60 overflow-y-auto">
                {isLoading && <li className="px-4 py-3 text-sm text-muted-foreground text-center"><span className="inline-block animate-spin mr-2">⟳</span>Загрузка...</li>}
                {!isLoading && suggestions.length === 0 && query.trim().length >= 2 && <li className="px-4 py-3 text-sm text-muted-foreground text-center">Ничего не найдено</li>}
                {!isLoading && suggestions.map((product, index) => (
                  <li key={product.slug}>
                    <button onMouseDown={() => { setQuery(product.name); setSuggestions([]); setFocused(false) }} onMouseEnter={() => setHighlightedIndex(index)} className={cn('w-full px-4 py-3 text-left text-sm transition-colors', index === highlightedIndex ? 'bg-primary/5 text-primary' : 'hover:bg-gray-50')}>{product.name}</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {/* КАРТОЧКА 3 - ТИП КОЖИ */}
      <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-3')}>
        <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
        <div className="relative">
          <label className="block text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground mb-3">{profile.skinType ? 'Твой тип кожи' : 'Выбери тип кожи'}</label>
          {!profile.skinType ? (
            <div className="flex flex-wrap gap-2">
              {SKIN_TYPES.map((t) => <Chip key={t} label={t} active={skinType === t} onClick={() => setSkinType(t)} />)}
              {onStartQuiz && <button onClick={onStartQuiz} className="px-4 py-1.5 rounded-full text-sm text-primary border border-primary/30 hover:bg-primary/5 transition-colors flex items-center gap-1 bg-white/50 backdrop-blur-sm"><Sparkles className="size-3" />Опросник</button>}
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <span className="text-sm font-normal">{profile.skinType}</span>
              {onStartQuiz && <button onClick={onStartQuiz} className="text-xs text-primary hover:underline flex items-center gap-1"><Sparkles className="size-3" />Обновить</button>}
            </div>
          )}
        </div>
      </div>

      {/* КАРТОЧКА 4 - КНОПКА ПРОВЕРИТЬ */}
      <div className={cn('card-enter', isVisible && 'card-enter-4')}>
        <button onClick={handleCheck} disabled={!canCheck} className={cn('w-full py-4 rounded-2xl text-white font-normal text-base transition-all', canCheck ? 'bg-gradient-to-r from-primary to-primary/80 hover:shadow-lg hover:shadow-primary/30 active:scale-[0.98]' : 'bg-gray-200/70 text-gray-400 cursor-not-allowed backdrop-blur-sm')}>
          <ScanSearch className="inline size-4 mr-2" />Проверить
        </button>
      </div>

      {/* КАРТОЧКА 5 - ПОПУЛЯРНОЕ */}
      <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-5')}>
        <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
        <div className="relative">
          <div className="flex items-center justify-between mb-3">
            <label className="text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground flex items-center gap-1.5"><Gem className="size-3 text-primary" />{popularSource === 'history' ? 'Популярное' : 'Бренды'}</label>
            {popularSource === 'history' && popularProducts.length > 0 && <span className="text-[10px] text-muted-foreground/60">{popularProducts.length} продуктов</span>}
          </div>
          <div className="flex flex-col gap-2 w-full">
            {popularProducts.map((p) => (
              <div key={p.name} onClick={() => setQuery(p.name)} className="w-full px-4 py-2.5 rounded-xl border cursor-pointer transition-all border-primary/10 hover:border-primary/30 hover:bg-primary/5 bg-white/30 backdrop-blur-sm">
                <MarqueeText text={p.name} className="text-sm" />
              </div>
            ))}
            {popularProducts.length === 0 && <p className="text-sm text-muted-foreground py-2">Загрузка...</p>}
          </div>
          {popularSource === 'history' && popularProducts.length > 0 && <p className="text-[10px] text-muted-foreground/50 mt-3">Топ из твоих проверок</p>}
        </div>
      </div>

      {/* КАРТОЧКА 6 - ЗАПОЛНИТЬ АНКЕТУ */}
      {!profileComplete && (
        <div className={cn('card-enter', isVisible && 'card-enter-6')}>
          <button onClick={onGoToProfile} className="w-full text-sm text-primary hover:text-primary/80 transition-colors flex items-center gap-1 justify-center py-3 bg-gradient-to-br from-primary/10 via-primary/5 to-transparent rounded-2xl border border-primary/20 backdrop-blur-sm px-4">
            Заполни анкету для точных рекомендаций <ArrowRight className="size-4" />
          </button>
        </div>
      )}
    </div>
  )
}