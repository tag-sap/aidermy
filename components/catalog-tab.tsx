'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, Filter, ChevronLeft, ChevronRight, Info, Sparkles, X, Grid3x3, LayoutList, ChevronDown } from 'lucide-react'
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

// === БЕГУЩАЯ СТРОКА ===
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
            <div className={cn('whitespace-nowrap inline-block', isOverflowing && 'animate-marquee')}>
                <span ref={textRef}>{text}</span>
                {isOverflowing && <span className="ml-8">{text}</span>}
            </div>
        </div>
    )
}

export function CatalogTab({
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
}) {
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
    const [isVisible, setIsVisible] = useState(false)
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
    const [skinTypeIndex, setSkinTypeIndex] = useState(() => {
        const defaultIndex = SKIN_TYPES.indexOf(profile?.skinType || '')
        return defaultIndex >= 0 ? defaultIndex : 0
    })
    const [isSearchSticky, setIsSearchSticky] = useState(false)
    const [showSkinTypes, setShowSkinTypes] = useState(false)
    const searchRef = useRef<HTMLDivElement>(null)
    const productsContainerRef = useRef<HTMLDivElement>(null)

    const limit = 6
    const cardStyle = "relative overflow-hidden bg-white/80 backdrop-blur-sm rounded-2xl border border-gray-100/50 shadow-sm hover:shadow-xl transition-all duration-300"

    // Эффекты
    useEffect(() => {
        const timer = setTimeout(() => setIsVisible(true), 100)
        return () => clearTimeout(timer)
    }, [])

    useEffect(() => {
        fetchCategories()
        fetchProducts()
    }, [])

    useEffect(() => {
        fetchProducts()
    }, [category, brand, sort, offset, search])

    // ОБСЕРВЕР
    useEffect(() => {
        const observer = new IntersectionObserver(
            ([entry]) => {
                setIsSearchSticky(!entry.isIntersecting)
            },
            { root: null, rootMargin: '0px 0px -150px 0px', threshold: 0 }
        )
        const sentinel = document.getElementById('sticky-sentinel')
        if (sentinel) observer.observe(sentinel)
        return () => observer.disconnect()
    }, [])

    const fetchCategories = async () => {
        try {
            const res = await fetch('/api/categories')
            const data = await res.json()
            setCategories(data.categories || [])
            setBrands(data.brands || [])
        } catch (error) {
            console.error('Ошибка загрузки категорий:', error)
        }
    }

    const fetchProducts = async () => {
        setLoading(true)
        try {
            const params = new URLSearchParams({ limit: String(limit), offset: String(offset), sort })
            if (category) params.append('category', category)
            if (brand) params.append('brand', brand)
            if (search) params.append('search', search)
            const res = await fetch(`/api/catalog?${params}`)
            const data = await res.json()
            setProducts(data.products || [])
            setTotal(data.total || 0)
        } catch (error) {
            console.error('Ошибка загрузки каталога:', error)
        } finally {
            setLoading(false)
        }
    }

    const totalPages = Math.ceil(total / limit)
    const currentPage = Math.floor(offset / limit) + 1

    const handlePageChange = (page: number) => {
        setOffset((page - 1) * limit)
        if (productsContainerRef.current) {
            setTimeout(() => {
                const rect = productsContainerRef.current?.getBoundingClientRect()
                if (rect) {
                    const top = rect.top + window.scrollY - 20
                    window.scrollTo({ top, behavior: 'smooth' })
                }
            }, 100)
        }
    }

    const triggerCheck = (productName: string) => {
        if (onCheck && profile) {
            onCheck(productName, profile.skinType || SKIN_TYPES[skinTypeIndex])
        }
    }

    const handleSkinTypeChange = (direction: 'left' | 'right') => {
        if (profile?.skinType) return
        const newIndex = direction === 'left'
            ? (skinTypeIndex - 1 + SKIN_TYPES.length) % SKIN_TYPES.length
            : (skinTypeIndex + 1) % SKIN_TYPES.length
        setSkinTypeIndex(newIndex)
    }

    const getGreeting = () => {
        const name = profile?.name || ''
        const time = new Date().getHours()
        let greeting = 'Добрый вечер'
        if (time < 12) greeting = 'Доброе утро'
        else if (time < 18) greeting = 'Добрый день'
        return name ? `${greeting}, ${name}` : greeting
    }

    const FilterPopup = () => {
        if (!showFilters) return null
        return (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 animate-in fade-in duration-200">
                <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowFilters(false)} />
                <div className="relative w-full max-w-sm bg-white rounded-2xl shadow-2xl p-6 animate-in slide-in-from-bottom-4 duration-300">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-semibold text-foreground">Фильтры</h3>
                        <button onClick={() => setShowFilters(false)} className="p-1.5 hover:bg-gray-100 rounded-full transition-colors">
                            <X className="size-5" />
                        </button>
                    </div>
                    <div className="space-y-5">
                        <div>
                            <label className="text-xs font-medium text-muted-foreground block mb-1.5">Категория</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                            >
                                <option value="">Все категории</option>
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground block mb-1.5">Бренд</label>
                            <select
                                value={brand}
                                onChange={(e) => setBrand(e.target.value)}
                                className="w-full rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                            >
                                <option value="">Все бренды</option>
                                {brands.map(b => <option key={b} value={b}>{b}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground block mb-1.5">Сортировка</label>
                            <select
                                value={sort}
                                onChange={(e) => setSort(e.target.value)}
                                className="w-full rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                            >
                                <option value="popular">По популярности</option>
                                <option value="score">По оценке</option>
                                <option value="name">По названию</option>
                            </select>
                        </div>
                        <button
                            onClick={() => { setCategory(''); setBrand(''); setSort('popular') }}
                            className="w-full py-2.5 rounded-xl border border-gray-200 text-sm text-muted-foreground hover:bg-gray-50 transition-colors"
                        >
                            Сбросить все
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="flex flex-col gap-4 max-w-md mx-auto pb-24 px-4">

            {/* === КОМПАКТНАЯ ВЕРХНЯЯ ЧАСТЬ === */}
            <div className={cn(
                'sticky top-0 z-40 bg-background/80 backdrop-blur-xl -mx-4 px-4 pt-3 pb-3 transition-all duration-300',
                isSearchSticky && 'shadow-sm border-b border-gray-100/50'
            )}>
                {/* Приветствие + инфо */}
                <div className="flex items-center justify-between mb-2">
                    <div>
                        <h1 className="text-lg font-semibold text-foreground tracking-tight">
                            {getGreeting()}
                        </h1>
                    </div>
                    <div className="flex items-center gap-1">
                        <button
                            onClick={onInfoClick}
                            className="p-1.5 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                        >
                            <Info className="size-4" />
                        </button>
                        <button
                            onClick={() => setShowSkinTypes(!showSkinTypes)}
                            className="px-2.5 py-1 rounded-full text-xs font-medium bg-primary/5 text-primary hover:bg-primary/10 transition-colors flex items-center gap-1"
                        >
                            {profile?.skinType || SKIN_TYPES[skinTypeIndex] || 'Тип кожи'}
                            <ChevronDown className={cn('size-3 transition-transform', showSkinTypes && 'rotate-180')} />
                        </button>
                    </div>
                </div>

                {/* Поиск + фильтры + переключение вида */}
                <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                        <div className="flex items-center gap-2 rounded-xl border border-gray-200 bg-gray-50/50 px-3 py-2 focus-within:border-primary/50 focus-within:bg-white focus-within:shadow-[0_0_20px_rgba(108,60,225,0.06)] transition-all">
                            <Search className="size-3.5 shrink-0 text-muted-foreground" />
                            <input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Поиск..."
                                className="w-full bg-transparent text-sm placeholder:text-muted-foreground/60 focus:outline-none"
                            />
                            {search && (
                                <button onClick={() => setSearch('')} className="p-0.5 rounded-full hover:bg-gray-200 transition-colors text-muted-foreground">
                                    <X className="size-3" />
                                </button>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={() => setShowFilters(true)}
                        className="p-2 rounded-xl border border-gray-200 hover:border-primary/30 hover:bg-primary/5 transition-all text-muted-foreground hover:text-primary"
                    >
                        <Filter className="size-4" />
                    </button>
                    <div className="flex border border-gray-200 rounded-xl overflow-hidden">
                        <button
                            onClick={() => setViewMode('grid')}
                            className={cn('p-2 transition-colors', viewMode === 'grid' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-gray-50')}
                        >
                            <Grid3x3 className="size-3.5" />
                        </button>
                        <button
                            onClick={() => setViewMode('list')}
                            className={cn('p-2 transition-colors border-l border-gray-200', viewMode === 'list' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-gray-50')}
                        >
                            <LayoutList className="size-3.5" />
                        </button>
                    </div>
                </div>

                {/* Выбор типа кожи (раскрывается под поиском) */}
                {showSkinTypes && !profile?.skinType && (
                    <div className="mt-3 pt-3 border-t border-gray-100/50 animate-in fade-in slide-in-from-top-2 duration-200">
                        <div className="flex items-center justify-center gap-3">
                            <button
                                onClick={() => handleSkinTypeChange('left')}
                                className="p-1.5 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                            >
                                <ChevronLeft className="size-4" />
                            </button>
                            <span className="text-sm font-medium min-w-[100px] text-center">
                                {SKIN_TYPES[skinTypeIndex]}
                            </span>
                            <button
                                onClick={() => handleSkinTypeChange('right')}
                                className="p-1.5 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                            >
                                <ChevronRight className="size-4" />
                            </button>
                        </div>
                        {onStartQuiz && (
                            <button onClick={onStartQuiz} className="text-xs text-primary hover:underline block text-center mt-1.5">
                                <Sparkles className="inline size-3 mr-1" /> Пройти опросник
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* СЕНТИНЕЛЬ ДЛЯ ПРИЛИПАНИЯ */}
            <div id="sticky-sentinel" className="h-0" />

            {/* КАТАЛОГ — СРАЗУ КАРТОЧКИ, МИНИМАЛЬНЫЙ ОТСТУП */}
            <div ref={productsContainerRef} className="space-y-4">
                {loading ? (
                    <div className="flex justify-center py-12">
                        <div className="animate-spin rounded-full h-10 w-10 border-4 border-primary/20 border-t-primary" />
                    </div>
                ) : products.length === 0 ? (
                    <div className={cn(cardStyle, 'text-center py-12')}>
                        <p className="text-muted-foreground">Ничего не найдено</p>
                    </div>
                ) : (
                    <>
                        <div className={cn('grid gap-3', viewMode === 'grid' ? 'grid-cols-2' : 'grid-cols-1')}>
                            {products.map((product, index) => (
                                <div
                                    key={product.slug}
                                    className={cn(
                                        'group bg-white/70 backdrop-blur-sm rounded-2xl border border-gray-100/50 shadow-sm hover:shadow-xl transition-all duration-300 cursor-pointer hover:border-primary/20',
                                        viewMode === 'grid' ? 'p-3' : 'p-4 flex items-center gap-4',
                                        'opacity-0 animate-in fade-in slide-in-from-bottom-4 duration-500'
                                    )}
                                    style={{ animationDelay: `${index * 50}ms`, animationFillMode: 'forwards' }}
                                    onClick={() => triggerCheck(product.name)}
                                >
                                    <div className={cn(
                                        'flex',
                                        viewMode === 'grid' ? 'flex-col items-center' : 'items-center gap-4 flex-1'
                                    )}>
                                        <div className={cn(
                                            'rounded-xl overflow-hidden bg-gray-50 flex items-center justify-center flex-shrink-0',
                                            viewMode === 'grid' ? 'w-full aspect-square' : 'w-16 h-16'
                                        )}>
                                            {product.image_url ? (
                                                <img
                                                    src={product.image_url}
                                                    alt={product.name}
                                                    className="w-full h-full object-contain p-2 group-hover:scale-105 transition-transform duration-300"
                                                />
                                            ) : (
                                                <span className="text-3xl">🧴</span>
                                            )}
                                        </div>
                                        <div className={cn(
                                            'w-full text-center',
                                            viewMode === 'grid' ? 'mt-2' : 'flex-1 text-left'
                                        )}>
                                            <p className="text-xs font-medium text-foreground line-clamp-2 leading-tight">
                                                {product.name}
                                            </p>
                                            {product.category && (
                                                <span className="text-[10px] text-muted-foreground mt-0.5 block">
                                                    {product.category}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    {viewMode === 'list' && (
                                        <button
                                            onClick={(e) => { e.stopPropagation(); triggerCheck(product.name) }}
                                            className="px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-medium hover:bg-primary/20 transition-colors flex-shrink-0"
                                        >
                                            Проверить
                                        </button>
                                    )}
                                </div>
                            ))}
                        </div>

                        {totalPages > 1 && (
                            <div className="flex items-center justify-center gap-2 py-4">
                                <button
                                    onClick={() => handlePageChange(currentPage - 1)}
                                    disabled={currentPage === 1}
                                    className="p-2 rounded-xl border border-gray-200 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                                >
                                    <ChevronLeft className="size-4" />
                                </button>
                                <span className="text-sm text-muted-foreground">{currentPage} / {totalPages}</span>
                                <button
                                    onClick={() => handlePageChange(currentPage + 1)}
                                    disabled={currentPage === totalPages}
                                    className="p-2 rounded-xl border border-gray-200 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                                >
                                    <ChevronRight className="size-4" />
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* ЗАПОЛНИТЬ АНКЕТУ */}
            {!profile?.skinType && (
                <button
                    onClick={onGoToProfile}
                    className="w-full py-3 rounded-2xl bg-gradient-to-r from-primary/5 to-primary/10 border border-primary/20 text-primary text-sm font-medium hover:shadow-md transition-all"
                >
                    ✨ Заполни анкету для точных рекомендаций
                </button>
            )}

            <FilterPopup />
        </div>
    )
}