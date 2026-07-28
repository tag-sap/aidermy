'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, Filter, ChevronLeft, ChevronRight, Info, Sparkles, X, Grid3x3, LayoutList, ChevronDown, ArrowLeft, ArrowRight } from 'lucide-react'
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

    useEffect(() => {
        const timer = setTimeout(() => setIsVisible(true), 50)
        return () => clearTimeout(timer)
    }, [])

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

    // Эффекты
    useEffect(() => {
        fetchCategories()
        fetchProducts()
    }, [])

    useEffect(() => {
        fetchProducts()
    }, [category, brand, sort, offset])

    useEffect(() => {
        if (searchTimeout) clearTimeout(searchTimeout)
        const timeout = setTimeout(() => {
            setOffset(0)
            fetchProducts()
        }, 300)
        setSearchTimeout(timeout)
        return () => clearTimeout(timeout)
    }, [search])

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
        <div className="h-full flex flex-col overflow-hidden bg-gradient-to-b from-background via-background to-primary/5">
            {/* === ШАПКА — СТИЛЬНАЯ === */}
            <div className="flex-shrink-0 px-1 pt-1.5 pb-1">
                {/* Приветствие + тип кожи */}
                <div className="flex items-center justify-between mb-1">
                    <h1 className="text-[15px] font-medium text-foreground tracking-tight truncate bg-gradient-to-r from-primary/80 to-primary bg-clip-text text-transparent">
                        {getGreeting()}
                    </h1>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button
                            onClick={onInfoClick}
                            className="p-1 rounded-full hover:bg-primary/10 transition-all duration-300 text-muted-foreground hover:text-primary hover:scale-110"
                        >
                            <Info className="size-3.5" />
                        </button>
                        <button
                            onClick={() => setShowSkinTypes(!showSkinTypes)}
                            className="px-2.5 py-0.5 rounded-full text-[9px] font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-all duration-300 flex items-center gap-0.5 whitespace-nowrap border border-primary/10"
                        >
                            <span className="opacity-60 text-[8px]">тип:</span>
                            {profile?.skinType || SKIN_TYPES[skinTypeIndex] || 'Выбрать'}
                            <ChevronDown className={cn('size-2.5 transition-transform duration-300', showSkinTypes && 'rotate-180')} />
                        </button>
                    </div>
                </div>

                {/* Поиск + фильтры + вид */}
                <div className="flex items-center gap-1.5 mb-1">
                    <div className="relative flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 rounded-xl bg-white/60 backdrop-blur-sm border border-gray-200/60 px-3 py-1.5 focus-within:border-primary/40 focus-within:bg-white focus-within:shadow-[0_0_30px_rgba(108,60,225,0.08)] transition-all duration-300">
                            <Search className="size-3.5 shrink-0 text-muted-foreground/60" />
                            <input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Поиск..."
                                className="w-full bg-transparent text-xs placeholder:text-muted-foreground/50 focus:outline-none min-w-0"
                            />
                            {search && (
                                <button
                                    onClick={() => setSearch('')}
                                    className="p-0.5 rounded-full hover:bg-gray-100 transition-colors text-muted-foreground shrink-0"
                                >
                                    <X className="size-2.5" />
                                </button>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={() => setShowFilters(true)}
                        className="p-1.5 rounded-xl bg-white/60 backdrop-blur-sm border border-gray-200/60 hover:border-primary/30 hover:bg-primary/5 transition-all duration-300 text-muted-foreground hover:text-primary shrink-0"
                    >
                        <Filter className="size-3.5" />
                    </button>
                    <div className="flex bg-white/60 backdrop-blur-sm border border-gray-200/60 rounded-xl overflow-hidden shrink-0">
                        <button
                            onClick={() => setViewMode('grid')}
                            className={cn('p-1.5 transition-all duration-300', viewMode === 'grid' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-gray-50/50')}
                        >
                            <Grid3x3 className="size-3.5" />
                        </button>
                        <button
                            onClick={() => setViewMode('list')}
                            className={cn('p-1.5 transition-all duration-300 border-l border-gray-200/60', viewMode === 'list' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-gray-50/50')}
                        >
                            <LayoutList className="size-3.5" />
                        </button>
                    </div>
                </div>

                {/* Выбор типа кожи (раскрывается) */}
                {showSkinTypes && !profile?.skinType && (
                    <div className="mt-1.5 pt-1.5 border-t border-gray-100/50 animate-in fade-in slide-in-from-top-2 duration-200">
                        <div className="flex items-center justify-center gap-4">
                            <button
                                onClick={() => handleSkinTypeChange('left')}
                                className="p-1 rounded-full hover:bg-primary/10 transition-all duration-300 text-muted-foreground hover:text-primary hover:scale-110"
                            >
                                <ChevronLeft className="size-3.5" />
                            </button>
                            <span className="text-[11px] font-medium min-w-[100px] text-center text-foreground">
                                {SKIN_TYPES[skinTypeIndex]}
                            </span>
                            <button
                                onClick={() => handleSkinTypeChange('right')}
                                className="p-1 rounded-full hover:bg-primary/10 transition-all duration-300 text-muted-foreground hover:text-primary hover:scale-110"
                            >
                                <ChevronRight className="size-3.5" />
                            </button>
                        </div>
                        {onStartQuiz && (
                            <button
                                onClick={onStartQuiz}
                                className="text-[9px] text-primary hover:underline block text-center mt-1 transition-all duration-300 hover:scale-105"
                            >
                                <Sparkles className="inline size-2.5 mr-1" /> Пройти опросник
                            </button>
                        )}
                    </div>
                )}

                {/* Счётчик */}
                {!loading && products.length > 0 && (
                    <p className="text-[9px] text-muted-foreground/60 text-center mt-1 font-medium tracking-wider">
                        {total} продуктов
                    </p>
                )}
            </div>

            {/* === ГРИД ПРОДУКТОВ === */}
            <div className="flex-1 min-h-0 overflow-hidden px-0.5">
                {loading ? (
                    <div className="flex justify-center items-center h-full">
                        <div className="relative">
                            <div className="animate-spin rounded-full h-8 w-8 border-3 border-primary/20 border-t-primary" />
                            <div className="absolute inset-0 rounded-full border-3 border-primary/5 animate-pulse" />
                        </div>
                    </div>
                ) : products.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                        <span className="text-3xl mb-2 opacity-50">🔍</span>
                        <p className="text-sm font-medium">Ничего не найдено</p>
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="mt-2 text-xs text-primary hover:underline transition-all"
                            >
                                Очистить поиск
                            </button>
                        )}
                    </div>
                ) : (
                    <div
                        className="h-full overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-primary/20 scrollbar-track-transparent hover:scrollbar-thumb-primary/30"
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
                                        'group bg-white/80 backdrop-blur-sm rounded-xl border border-gray-100/50 shadow-sm hover:shadow-xl transition-all duration-400 cursor-pointer hover:border-primary/30 active:scale-[0.97]',
                                        viewMode === 'grid' ? 'p-2.5' : 'p-3 flex items-center gap-3',
                                        'opacity-0 animate-in fade-in slide-in-from-bottom-4 duration-500'
                                    )}
                                    style={{
                                        animationDelay: `${Math.min(index, 15) * 35}ms`,
                                        animationFillMode: 'forwards'
                                    }}
                                    onClick={() => triggerCheck(product.name)}
                                >
                                    <div className={cn(
                                        'flex',
                                        viewMode === 'grid' ? 'flex-col items-center w-full' : 'items-center gap-3 flex-1 min-w-0'
                                    )}>
                                        <div className={cn(
                                            'rounded-xl overflow-hidden bg-gradient-to-br from-gray-50 to-gray-100/50 flex items-center justify-center flex-shrink-0 transition-all duration-300 group-hover:shadow-inner',
                                            viewMode === 'grid' ? 'w-full aspect-square' : 'w-12 h-12'
                                        )}>
                                            {product.image_url ? (
                                                <img
                                                    src={product.image_url}
                                                    alt={product.name}
                                                    loading="lazy"
                                                    className="w-full h-full object-contain p-1.5 group-hover:scale-110 transition-transform duration-500"
                                                />
                                            ) : (
                                                <span className="text-2xl opacity-40">🧴</span>
                                            )}
                                        </div>
                                        <div className={cn(
                                            'w-full min-w-0',
                                            viewMode === 'grid' ? 'mt-1.5 text-center' : 'flex-1 text-left'
                                        )}>
                                            <p className="text-[11px] font-medium text-foreground/90 line-clamp-2 leading-snug break-words group-hover:text-primary transition-colors duration-300">
                                                {product.name}
                                            </p>
                                            {product.category && (
                                                <span className="text-[8px] text-muted-foreground/60 mt-0.5 block truncate tracking-wide uppercase">
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
                                            className="px-3 py-1 rounded-full bg-primary/10 text-primary text-[9px] font-medium hover:bg-primary/20 transition-all duration-300 flex-shrink-0 hover:scale-105 active:scale-95"
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

            {/* === ФУТЕР — СТИЛЬНЫЙ === */}
            <div className="flex-shrink-0 px-1 py-1.5 bg-gradient-to-t from-background via-background to-transparent">
                {/* Пагинация с большими стрелками */}
                {totalPages > 1 && !loading && products.length > 0 && (
                    <div className="flex items-center justify-center gap-3 mb-1.5">
                        <button
                            onClick={() => handlePageChange(currentPage - 1)}
                            disabled={currentPage === 1}
                            className={cn(
                                'p-1.5 rounded-xl border transition-all duration-300',
                                currentPage === 1
                                    ? 'border-gray-100 text-muted-foreground/30 cursor-not-allowed'
                                    : 'border-gray-200 hover:border-primary/30 hover:bg-primary/5 hover:text-primary hover:scale-105 active:scale-95 text-muted-foreground'
                            )}
                        >
                            <ArrowLeft className="size-4" />
                        </button>

                        <div className="flex items-center gap-1.5">
                            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                                let pageNum
                                if (totalPages <= 5) {
                                    pageNum = i + 1
                                } else if (currentPage <= 3) {
                                    pageNum = i + 1
                                } else if (currentPage >= totalPages - 2) {
                                    pageNum = totalPages - 4 + i
                                } else {
                                    pageNum = currentPage - 2 + i
                                }

                                return (
                                    <button
                                        key={pageNum}
                                        onClick={() => handlePageChange(pageNum)}
                                        className={cn(
                                            'w-7 h-7 rounded-lg text-xs font-medium transition-all duration-300',
                                            currentPage === pageNum
                                                ? 'bg-primary text-white shadow-md shadow-primary/20 scale-105'
                                                : 'text-muted-foreground hover:bg-primary/10 hover:text-primary hover:scale-105'
                                        )}
                                    >
                                        {pageNum}
                                    </button>
                                )
                            })}
                            {totalPages > 5 && currentPage < totalPages - 2 && (
                                <>
                                    <span className="text-muted-foreground/40 text-xs">...</span>
                                    <button
                                        onClick={() => handlePageChange(totalPages)}
                                        className="w-7 h-7 rounded-lg text-xs font-medium text-muted-foreground hover:bg-primary/10 hover:text-primary transition-all duration-300"
                                    >
                                        {totalPages}
                                    </button>
                                </>
                            )}
                        </div>

                        <button
                            onClick={() => handlePageChange(currentPage + 1)}
                            disabled={currentPage === totalPages}
                            className={cn(
                                'p-1.5 rounded-xl border transition-all duration-300',
                                currentPage === totalPages
                                    ? 'border-gray-100 text-muted-foreground/30 cursor-not-allowed'
                                    : 'border-gray-200 hover:border-primary/30 hover:bg-primary/5 hover:text-primary hover:scale-105 active:scale-95 text-muted-foreground'
                            )}
                        >
                            <ArrowRight className="size-4" />
                        </button>
                    </div>
                )}

                {/* Кнопка "Заполнить анкету" */}
                {!profile?.skinType && (
                    <button
                        onClick={onGoToProfile}
                        className="w-full py-2 rounded-xl text-[10px] font-medium bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/20 text-primary hover:shadow-lg hover:shadow-primary/10 transition-all duration-300 active:scale-[0.97] hover:scale-[1.01]"
                    >
                        ✨ Заполнить анкету
                    </button>
                )}
            </div>

            <FilterPopup />
        </div>
    )
}