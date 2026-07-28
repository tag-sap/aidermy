'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
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
    const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
    const [skinTypeIndex, setSkinTypeIndex] = useState(() => {
        const defaultIndex = SKIN_TYPES.indexOf(profile?.skinType || '')
        return defaultIndex >= 0 ? defaultIndex : 0
    })
    const [showSkinTypes, setShowSkinTypes] = useState(false)
    const [searchTimeout, setSearchTimeout] = useState<NodeJS.Timeout | null>(null)
    const [isVisible, setIsVisible] = useState(false)

    const limit = 8

    // Refs для высоты
    const headerRef = useRef<HTMLDivElement>(null)
    const footerRef = useRef<HTMLDivElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)
    const [gridHeight, setGridHeight] = useState<number | null>(null)

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
    }, [category, brand, sort, offset])

    // Debounced search
    useEffect(() => {
        if (searchTimeout) clearTimeout(searchTimeout)
        const timeout = setTimeout(() => {
            setOffset(0)
            fetchProducts()
        }, 300)
        setSearchTimeout(timeout)
        return () => clearTimeout(timeout)
    }, [search])

    // Расчёт высоты грида
    useEffect(() => {
        const calculateHeight = () => {
            if (headerRef.current && footerRef.current && containerRef.current) {
                const headerHeight = headerRef.current.offsetHeight
                const footerHeight = footerRef.current.offsetHeight
                const containerHeight = containerRef.current.clientHeight
                const available = containerHeight - headerHeight - footerHeight - 16
                setGridHeight(Math.max(available, 200))
            }
        }

        calculateHeight()
        window.addEventListener('resize', calculateHeight)
        return () => window.removeEventListener('resize', calculateHeight)
    }, [loading, products.length])

    // Функции загрузки
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
            const params = new URLSearchParams({
                limit: String(limit),
                offset: String(offset),
                sort
            })
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

    // Обработчики
    const totalPages = Math.ceil(total / limit)
    const currentPage = Math.floor(offset / limit) + 1

    const handlePageChange = (page: number) => {
        setOffset((page - 1) * limit)
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

    const clearFilters = () => {
        setCategory('')
        setBrand('')
        setSort('popular')
        setOffset(0)
        setShowFilters(false)
    }

    // Фильтр попап
    const FilterPopup = () => {
        if (!showFilters) return null
        return (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 animate-in fade-in duration-200">
                <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowFilters(false)} />
                <div className="relative w-full max-w-sm bg-white rounded-2xl shadow-2xl p-6 animate-in slide-in-from-bottom-4 duration-300 max-h-[80vh] overflow-y-auto">
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
                            onClick={clearFilters}
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
        <div
            ref={containerRef}
            className="h-full flex flex-col overflow-hidden"
            style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
            }}
        >
            {/* === ШАПКА — фиксированная === */}
            <div
                ref={headerRef}
                className="flex-shrink-0 pt-3 pb-2"
                style={{ flexShrink: 0 }}
            >
                {/* Приветствие + инфо */}
                <div className="flex items-center justify-between mb-1.5">
                    <h1 className="text-base font-semibold text-foreground tracking-tight truncate">
                        {getGreeting()}
                    </h1>
                    <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                            onClick={onInfoClick}
                            className="p-1.5 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                            aria-label="Информация"
                        >
                            <Info className="size-3.5" />
                        </button>
                        <button
                            onClick={() => setShowSkinTypes(!showSkinTypes)}
                            className="px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-primary/5 text-primary hover:bg-primary/10 transition-colors flex items-center gap-0.5 whitespace-nowrap"
                        >
                            <span className="text-muted-foreground text-[9px] hidden xs:inline">Тип кожи:</span>
                            <span className="max-w-[60px] truncate">
                                {profile?.skinType || SKIN_TYPES[skinTypeIndex] || 'Выбрать'}
                            </span>
                            <ChevronDown className={cn('size-3 transition-transform', showSkinTypes && 'rotate-180')} />
                        </button>
                    </div>
                </div>

                {/* Поиск + фильтры + переключение вида */}
                <div className="flex items-center gap-1.5">
                    <div className="relative flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 rounded-xl border border-gray-200 bg-gray-50/50 px-3 py-1.5 focus-within:border-primary/50 focus-within:bg-white focus-within:shadow-[0_0_20px_rgba(108,60,225,0.06)] transition-all">
                            <Search className="size-3 shrink-0 text-muted-foreground" />
                            <input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Поиск..."
                                className="w-full bg-transparent text-sm placeholder:text-muted-foreground/60 focus:outline-none min-w-0"
                            />
                            {search && (
                                <button
                                    onClick={() => setSearch('')}
                                    className="p-0.5 rounded-full hover:bg-gray-200 transition-colors text-muted-foreground shrink-0"
                                >
                                    <X className="size-2.5" />
                                </button>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={() => setShowFilters(true)}
                        className="p-1.5 rounded-xl border border-gray-200 hover:border-primary/30 hover:bg-primary/5 transition-all text-muted-foreground hover:text-primary shrink-0"
                        aria-label="Фильтры"
                    >
                        <Filter className="size-3.5" />
                    </button>
                    <div className="flex border border-gray-200 rounded-xl overflow-hidden shrink-0">
                        <button
                            onClick={() => setViewMode('grid')}
                            className={cn('p-1.5 transition-colors', viewMode === 'grid' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-gray-50')}
                            aria-label="Сетка"
                        >
                            <Grid3x3 className="size-3" />
                        </button>
                        <button
                            onClick={() => setViewMode('list')}
                            className={cn('p-1.5 transition-colors border-l border-gray-200', viewMode === 'list' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-gray-50')}
                            aria-label="Список"
                        >
                            <LayoutList className="size-3" />
                        </button>
                    </div>
                </div>

                {/* Выбор типа кожи (раскрывается под поиском) */}
                {showSkinTypes && !profile?.skinType && (
                    <div className="mt-2 pt-2 border-t border-gray-100/50 animate-in fade-in slide-in-from-top-2 duration-200">
                        <div className="flex items-center justify-center gap-3">
                            <button
                                onClick={() => handleSkinTypeChange('left')}
                                className="p-1 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                                aria-label="Предыдущий тип"
                            >
                                <ChevronLeft className="size-3.5" />
                            </button>
                            <span className="text-xs font-medium min-w-[100px] text-center">
                                {SKIN_TYPES[skinTypeIndex]}
                            </span>
                            <button
                                onClick={() => handleSkinTypeChange('right')}
                                className="p-1 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                                aria-label="Следующий тип"
                            >
                                <ChevronRight className="size-3.5" />
                            </button>
                        </div>
                        {onStartQuiz && (
                            <button
                                onClick={onStartQuiz}
                                className="text-[10px] text-primary hover:underline block text-center mt-1"
                            >
                                <Sparkles className="inline size-2.5 mr-1" /> Пройти опросник
                            </button>
                        )}
                    </div>
                )}

                {/* Счетчик результатов */}
                {!loading && products.length > 0 && (
                    <p className="text-[10px] text-muted-foreground mt-1 text-center">
                        {total} продуктов
                    </p>
                )}
            </div>

            {/* === ГРИД ПРОДУКТОВ — заполняет всё оставшееся место === */}
            <div
                className="flex-1 min-h-0 overflow-hidden"
                style={{
                    flex: '1 1 0%',
                    minHeight: 0,
                    overflow: 'hidden',
                }}
            >
                {loading ? (
                    <div className="flex justify-center items-center h-full">
                        <div className="animate-spin rounded-full h-8 w-8 border-4 border-primary/20 border-t-primary" />
                    </div>
                ) : products.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                        <span className="text-3xl mb-2">🔍</span>
                        <p className="text-sm">Ничего не найдено</p>
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="mt-2 text-xs text-primary hover:underline"
                            >
                                Очистить поиск
                            </button>
                        )}
                    </div>
                ) : (
                    <div
                        className="h-full overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-primary/20 scrollbar-track-transparent"
                        style={{
                            height: '100%',
                            overflowY: 'auto',
                            paddingRight: '0.25rem',
                        }}
                    >
                        <div className={cn(
                            'grid gap-2 pb-1',
                            viewMode === 'grid' ? 'grid-cols-2' : 'grid-cols-1'
                        )}>
                            {products.map((product, index) => (
                                <div
                                    key={product.slug}
                                    className={cn(
                                        'group bg-white/70 backdrop-blur-sm rounded-xl border border-gray-100/50 shadow-sm hover:shadow-xl transition-all duration-300 cursor-pointer hover:border-primary/20 active:scale-[0.98]',
                                        viewMode === 'grid' ? 'p-2.5' : 'p-3 flex items-center gap-3',
                                        'opacity-0 animate-in fade-in slide-in-from-bottom-3 duration-400'
                                    )}
                                    style={{
                                        animationDelay: `${Math.min(index, 15) * 40}ms`,
                                        animationFillMode: 'forwards'
                                    }}
                                    onClick={() => triggerCheck(product.name)}
                                >
                                    <div className={cn(
                                        'flex',
                                        viewMode === 'grid' ? 'flex-col items-center w-full' : 'items-center gap-3 flex-1 min-w-0'
                                    )}>
                                        <div className={cn(
                                            'rounded-lg overflow-hidden bg-gray-50 flex items-center justify-center flex-shrink-0',
                                            viewMode === 'grid' ? 'w-full aspect-square' : 'w-12 h-12'
                                        )}>
                                            {product.image_url ? (
                                                <img
                                                    src={product.image_url}
                                                    alt={product.name}
                                                    loading="lazy"
                                                    className="w-full h-full object-contain p-1.5 group-hover:scale-105 transition-transform duration-300"
                                                />
                                            ) : (
                                                <span className="text-2xl">🧴</span>
                                            )}
                                        </div>
                                        <div className={cn(
                                            'w-full min-w-0',
                                            viewMode === 'grid' ? 'mt-1.5 text-center' : 'flex-1 text-left'
                                        )}>
                                            <p className="text-[11px] font-medium text-foreground line-clamp-2 leading-tight break-words">
                                                {product.name}
                                            </p>
                                            {product.category && (
                                                <span className="text-[9px] text-muted-foreground mt-0.5 block truncate">
                                                    {product.category}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    {viewMode === 'list' && (
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                triggerCheck(product.name)
                                            }}
                                            className="px-2.5 py-1 rounded-full bg-primary/10 text-primary text-[10px] font-medium hover:bg-primary/20 transition-colors flex-shrink-0"
                                        >
                                            Проверить
                                        </button>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* === ФУТЕР — пагинация и кнопка анкеты === */}
            <div
                ref={footerRef}
                className="flex-shrink-0 py-2 space-y-1.5"
                style={{ flexShrink: 0 }}
            >
                {/* Пагинация */}
                {totalPages > 1 && !loading && products.length > 0 && (
                    <div className="flex items-center justify-center gap-2">
                        <button
                            onClick={() => handlePageChange(currentPage - 1)}
                            disabled={currentPage === 1}
                            className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                            aria-label="Предыдущая страница"
                        >
                            <ChevronLeft className="size-3.5" />
                        </button>
                        <span className="text-xs text-muted-foreground">
                            {currentPage} / {totalPages}
                        </span>
                        <button
                            onClick={() => handlePageChange(currentPage + 1)}
                            disabled={currentPage === totalPages}
                            className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                            aria-label="Следующая страница"
                        >
                            <ChevronRight className="size-3.5" />
                        </button>
                    </div>
                )}

                {/* Кнопка "Заполнить анкету" */}
                {!profile?.skinType && (
                    <button
                        onClick={onGoToProfile}
                        className="w-full py-2 rounded-xl text-xs font-medium bg-gradient-to-r from-primary/5 to-primary/10 border border-primary/20 text-primary hover:shadow-md transition-all active:scale-[0.98]"
                    >
                        ✨ Заполнить анкету
                    </button>
                )}
            </div>

            {/* Фильтр попап */}
            <FilterPopup />
        </div>
    )
}