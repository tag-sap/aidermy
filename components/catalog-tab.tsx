'use client'

import { useState, useEffect, useRef, memo } from 'react'
import { Search, X, Sparkles, ArrowRight, Compass, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SKIN_TYPES } from '@/lib/products'
import type { SkinProfile } from '@/lib/store'

interface Product {
    name: string
    slug: string
    image_url: string | null
    ingredients: string | null
    category: string | null
    brand: string | null
}

const CatalogTabComponent = ({
    onCheck,
    profile,
    onGoToProfile,
    onStartQuiz,
    onInfoClick,
}: {
    onCheck?: (product: string, skinType: string) => void
    profile?: SkinProfile
    onGoToProfile?: () => void
    onStartQuiz?: () => void
    onInfoClick?: () => void
}) => {
    const [products, setProducts] = useState<Product[]>([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [category, setCategory] = useState('')
    const [brand, setBrand] = useState('')
    const [sort, setSort] = useState('popular')
    const [offset, setOffset] = useState(0)
    const [categories, setCategories] = useState<string[]>([])
    const [brands, setBrands] = useState<string[]>([])
    const [showFilters, setShowFilters] = useState(false)
    const [searchTimeout, setSearchTimeout] = useState<NodeJS.Timeout | null>(null)
    const [isFocused, setIsFocused] = useState(false)
    const [hoveredId, setHoveredId] = useState<string | null>(null)
    const [isVisible, setIsVisible] = useState(false)

    const isMounted = useRef(false)
    const abortControllerRef = useRef<AbortController | null>(null)
    const animationTimerRef = useRef<NodeJS.Timeout | null>(null)
    const scrollContainerRef = useRef<HTMLDivElement>(null)

    const limit = 6

    useEffect(() => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollTop = 0
        }
    }, [offset])

    useEffect(() => {
        if (animationTimerRef.current) {
            clearTimeout(animationTimerRef.current)
            animationTimerRef.current = null
        }

        if (!loading && products.length > 0 && isMounted.current) {
            setIsVisible(false)
            animationTimerRef.current = setTimeout(() => {
                if (isMounted.current) {
                    setIsVisible(true)
                }
            }, 50)
        }
        return () => {
            if (animationTimerRef.current) {
                clearTimeout(animationTimerRef.current)
                animationTimerRef.current = null
            }
        }
    }, [loading, products.length, offset])

    const fetchCategories = async () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort()
        }
        abortControllerRef.current = new AbortController()

        try {
            const res = await fetch('/api/categories', {
                signal: abortControllerRef.current.signal
            })
            const data = await res.json()
            if (isMounted.current) {
                setCategories(data.categories || [])
                setBrands(data.brands || [])
            }
        } catch (error) {
            if ((error as Error).name === 'AbortError') return
            console.error('Ошибка загрузки категорий:', error)
        }
    }

    const fetchProducts = async () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort()
        }
        abortControllerRef.current = new AbortController()

        setLoading(true)
        setIsVisible(false)
        try {
            const params = new URLSearchParams({
                limit: String(limit),
                offset: String(offset),
                sort
            })
            if (category) params.append('category', category)
            if (brand) params.append('brand', brand)
            if (search) params.append('search', search)

            const res = await fetch(`/api/catalog?${params}`, {
                signal: abortControllerRef.current.signal
            })
            const data = await res.json()

            if (isMounted.current) {
                setProducts(data.products || [])
                setTotal(data.total || 0)
            }
        } catch (error) {
            if ((error as Error).name === 'AbortError') return
            console.error('Ошибка загрузки каталога:', error)
        } finally {
            if (isMounted.current) {
                setLoading(false)
            }
        }
    }

    useEffect(() => {
        isMounted.current = true
        fetchCategories()
        fetchProducts()

        return () => {
            isMounted.current = false
            if (abortControllerRef.current) {
                abortControllerRef.current.abort()
            }
            if (animationTimerRef.current) {
                clearTimeout(animationTimerRef.current)
                animationTimerRef.current = null
            }
        }
    }, [])

    useEffect(() => {
        if (isMounted.current) {
            fetchProducts()
        }
    }, [category, brand, sort, offset, search])

    useEffect(() => {
        if (searchTimeout) clearTimeout(searchTimeout)
        const timeout = setTimeout(() => {
            if (isMounted.current) {
                setOffset(0)
            }
        }, 400)
        setSearchTimeout(timeout)
        return () => clearTimeout(timeout)
    }, [search])

    const totalPages = Math.ceil(total / limit)
    const currentPage = Math.floor(offset / limit) + 1

    const handlePageChange = (page: number) => {
        if (isMounted.current) {
            setOffset((page - 1) * limit)
        }
    }

    const triggerCheck = (productName: string) => {
        if (onCheck && profile) {
            onCheck(productName, profile.skinType || 'Нормальная')
        }
    }

    const getGreeting = () => {
        const name = profile?.name || ''
        const time = new Date().getHours()
        let greeting = 'Добрый вечер'
        if (time < 12) greeting = 'Доброе утро'
        else if (time < 18) greeting = 'Добрый день'
        return name ? `${greeting}, ${name}` : greeting
    }

    const clearFilters = () => {
        setCategory('')
        setBrand('')
        setSort('popular')
        setOffset(0)
        setShowFilters(false)
    }

    const FilterPopup = () => {
        if (!showFilters) return null
        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" onClick={() => setShowFilters(false)} />
                <div className="relative w-full max-w-sm bg-white/30 backdrop-blur-xl border border-white/30 rounded-2xl shadow-2xl p-6 max-h-[80vh] overflow-y-auto">
                    <div className="flex items-center justify-between mb-5">
                        <h3 className="text-base font-light text-foreground/80">Фильтры</h3>
                        <button onClick={() => setShowFilters(false)} className="p-1.5 hover:bg-white/20 rounded-full transition-colors">
                            <X className="size-4" />
                        </button>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <label className="text-xs text-muted-foreground/60 block mb-1.5">Категория</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full rounded-xl bg-white/20 backdrop-blur-sm border border-white/20 px-3.5 py-2.5 text-sm text-foreground/80 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all"
                            >
                                <option value="">Все категории</option>
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-muted-foreground/60 block mb-1.5">Бренд</label>
                            <select
                                value={brand}
                                onChange={(e) => setBrand(e.target.value)}
                                className="w-full rounded-xl bg-white/20 backdrop-blur-sm border border-white/20 px-3.5 py-2.5 text-sm text-foreground/80 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all"
                            >
                                <option value="">Все бренды</option>
                                {brands.map(b => <option key={b} value={b}>{b}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-muted-foreground/60 block mb-1.5">Сортировка</label>
                            <select
                                value={sort}
                                onChange={(e) => setSort(e.target.value)}
                                className="w-full rounded-xl bg-white/20 backdrop-blur-sm border border-white/20 px-3.5 py-2.5 text-sm text-foreground/80 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all"
                            >
                                <option value="popular">По популярности</option>
                                <option value="score">По оценке</option>
                                <option value="name">По названию</option>
                            </select>
                        </div>
                        <button
                            onClick={clearFilters}
                            className="w-full py-2.5 rounded-xl border border-white/20 text-sm text-muted-foreground/60 hover:bg-white/20 transition-colors"
                        >
                            Сбросить все
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    const SkeletonCard = () => (
        <div className="bg-white/20 backdrop-blur-sm rounded-2xl border border-white/20 overflow-hidden animate-pulse">
            <div className="w-full aspect-square bg-white/10" />
            <div className="p-3 space-y-2">
                <div className="h-3.5 bg-white/10 rounded-full w-3/4" />
                <div className="h-2.5 bg-white/10 rounded-full w-1/2" />
            </div>
        </div>
    )

    // Стеклянная карточка с обычным скруглением
    const glassCardStyle = cn(
        'bg-white/20 backdrop-blur-xl',
        'border border-white/20',
        'shadow-[0_8px_32px_rgba(108,60,225,0.06)]',
        'hover:shadow-[0_12px_48px_rgba(108,60,225,0.12)]',
        'transition-all duration-500',
        'overflow-hidden cursor-pointer',
        'hover:bg-white/30 hover:border-primary/20',
        'rounded-2xl',
        'hover:scale-[1.02]'
    )

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Хедер */}
            <div className="flex-shrink-0 pt-1 pb-1">
                <div className="flex items-center justify-between mb-1.5">
                    <div>
                        <h1 className="text-lg font-light text-foreground/90">
                            {getGreeting()}
                        </h1>
                        <span className="text-[10px] text-muted-foreground/50 font-light">
                            {profile?.skinType ? `Тип кожи: ${profile.skinType}` : 'Выберите тип кожи'}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        {!profile?.skinType && (
                            <button
                                onClick={onStartQuiz}
                                className="text-[10px] text-primary/70 hover:text-primary transition-colors flex items-center gap-1"
                            >
                                <Sparkles className="size-3" />
                                Опросник
                            </button>
                        )}
                        <button
                            onClick={onInfoClick}
                            className="w-8 h-8 rounded-xl bg-white/20 backdrop-blur-sm border border-white/20 flex items-center justify-center text-muted-foreground/60 hover:text-primary hover:border-primary/30 transition-all duration-300 text-sm"
                        >
                            ?
                        </button>
                    </div>
                </div>

                {/* Поиск */}
                <div className={cn(
                    'relative rounded-xl transition-all duration-300 mb-1.5',
                    isFocused ? 'shadow-[0_0_40px_rgba(108,60,225,0.06)]' : ''
                )}>
                    <div className={cn(
                        'flex items-center gap-2.5 rounded-xl border px-3.5 py-2 transition-all duration-300',
                        'bg-white/20 backdrop-blur-sm',
                        'border-white/20',
                        isFocused
                            ? 'border-primary/30 bg-white/30 shadow-sm'
                            : 'hover:border-white/40'
                    )}>
                        <Search className={cn(
                            'size-4 transition-colors duration-300',
                            isFocused ? 'text-primary' : 'text-muted-foreground/30'
                        )} />
                        <input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            onFocus={() => setIsFocused(true)}
                            onBlur={() => setIsFocused(false)}
                            placeholder="Поиск продуктов..."
                            className="w-full bg-transparent text-sm placeholder:text-muted-foreground/30 focus:outline-none text-foreground/80"
                        />
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="p-1 rounded-full hover:bg-white/20 transition-colors"
                            >
                                <X className="size-3.5 text-muted-foreground/40" />
                            </button>
                        )}
                    </div>
                </div>

                {/* Кнопка "Заполнить анкету" */}
                {!profile?.skinType && (
                    <button
                        onClick={onGoToProfile}
                        className="w-full py-1.5 rounded-xl text-[10px] font-medium bg-primary/10 backdrop-blur-sm border border-primary/20 text-primary hover:bg-primary/20 transition-all duration-300 active:scale-[0.98] flex items-center justify-center gap-2 mb-1.5"
                    >
                        <Zap className="size-3" />
                        Заполнить анкету
                        <ArrowRight className="size-3" />
                    </button>
                )}

                {/* Фильтры + пагинация */}
                <div className="flex items-center justify-between">
                    <button
                        onClick={() => setShowFilters(true)}
                        className="px-3 py-1 rounded-xl bg-white/20 backdrop-blur-sm border border-white/20 text-[10px] text-muted-foreground/60 hover:text-primary hover:border-primary/30 transition-all duration-300 flex items-center gap-1.5"
                    >
                        <span>Фильтры</span>
                        {(category || brand) && (
                            <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                        )}
                    </button>

                    {totalPages > 1 && !loading && (
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => handlePageChange(currentPage - 1)}
                                disabled={currentPage === 1}
                                className={cn(
                                    'w-7 h-7 rounded-xl border transition-all duration-300 flex items-center justify-center bg-white/10 backdrop-blur-sm',
                                    currentPage === 1
                                        ? 'border-white/10 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-white/20 hover:border-primary/30 hover:text-primary text-muted-foreground/60 hover:bg-white/20'
                                )}
                            >
                                <ArrowRight className="size-3 rotate-180" />
                            </button>
                            <span className="text-[10px] text-muted-foreground/40 px-1.5 min-w-[32px] text-center font-light">
                                {currentPage}/{totalPages}
                            </span>
                            <button
                                onClick={() => handlePageChange(currentPage + 1)}
                                disabled={currentPage === totalPages}
                                className={cn(
                                    'w-7 h-7 rounded-xl border transition-all duration-300 flex items-center justify-center bg-white/10 backdrop-blur-sm',
                                    currentPage === totalPages
                                        ? 'border-white/10 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-white/20 hover:border-primary/30 hover:text-primary text-muted-foreground/60 hover:bg-white/20'
                                )}
                            >
                                <ArrowRight className="size-3" />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* Галерея */}
            <div className="flex-1 min-h-0 overflow-hidden">
                {loading ? (
                    <div className="grid grid-cols-2 gap-2.5 pb-2">
                        {Array.from({ length: 6 }).map((_, i) => (
                            <SkeletonCard key={i} />
                        ))}
                    </div>
                ) : products.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full">
                        <div className="w-16 h-16 rounded-full bg-white/10 backdrop-blur-sm flex items-center justify-center mb-3">
                            <Compass className="size-6 text-muted-foreground/20" />
                        </div>
                        <p className="text-sm text-muted-foreground/50 font-light">Ничего не найдено</p>
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="mt-2 text-xs text-primary/60 hover:text-primary transition-colors"
                            >
                                Очистить поиск
                            </button>
                        )}
                    </div>
                ) : (
                    <div
                        ref={scrollContainerRef}
                        className="h-full overflow-y-auto pr-0.5 scrollbar-thin scrollbar-thumb-white/20 scrollbar-track-transparent"
                        style={{
                            height: '100%',
                            overflowY: 'auto',
                            paddingRight: '0.25rem',
                        }}
                    >
                        <div className="grid grid-cols-2 gap-2.5">
                            {products.map((product, index) => {
                                const isHovered = hoveredId === product.slug
                                return (
                                    <div
                                        key={product.slug}
                                        className={cn(
                                            glassCardStyle,
                                            isHovered && 'border-primary/30 shadow-[0_12px_48px_rgba(108,60,225,0.15)]',
                                            'card-enter',
                                            isVisible && `card-enter-${Math.min(index + 1, 6)}`
                                        )}
                                        style={{
                                            animationDelay: `${index * 0.08}s`,
                                            borderRadius: '16px',
                                        }}
                                        onMouseEnter={() => setHoveredId(product.slug)}
                                        onMouseLeave={() => setHoveredId(null)}
                                        onClick={() => triggerCheck(product.name)}
                                    >
                                        <div className="w-full aspect-square overflow-hidden bg-white/5 flex items-center justify-center">
                                            {product.image_url ? (
                                                <img
                                                    src={product.image_url}
                                                    alt={product.name}
                                                    loading="lazy"
                                                    className={cn(
                                                        'w-full h-full object-contain p-3 transition-all duration-500',
                                                        isHovered ? 'scale-105' : 'scale-100'
                                                    )}
                                                />
                                            ) : (
                                                <span className="text-3xl opacity-20">🧴</span>
                                            )}
                                        </div>
                                        <div className="p-3">
                                            <p className="text-xs font-medium text-foreground/80 line-clamp-2 leading-snug">
                                                {product.name}
                                            </p>
                                            {product.category && (
                                                <p className="text-[8px] text-muted-foreground/40 uppercase tracking-wider mt-0.5">
                                                    {product.category}
                                                </p>
                                            )}
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation()
                                                    triggerCheck(product.name)
                                                }}
                                                className={cn(
                                                    'w-full mt-1.5 py-1.5 rounded-xl text-[9px] font-medium transition-all duration-500',
                                                    isHovered
                                                        ? 'bg-primary/20 text-primary/90 opacity-100 backdrop-blur-sm'
                                                        : 'bg-transparent text-transparent opacity-0'
                                                )}
                                            >
                                                Проверить
                                            </button>
                                        </div>
                                    </div>
                                )
                            })}
                            <div className="h-20 col-span-2" />
                        </div>
                    </div>
                )}
            </div>

            <FilterPopup />
        </div>
    )
}

export const CatalogTab = memo(CatalogTabComponent)