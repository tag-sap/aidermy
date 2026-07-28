'use client'

import { useState, useEffect } from 'react'
import { Search, Filter, X, Grid3x3, LayoutList, ChevronDown, ArrowLeft, ArrowRight, Sparkles, TrendingUp, Star } from 'lucide-react'
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
    const [searchTimeout, setSearchTimeout] = useState<NodeJS.Timeout | null>(null)

    const limit = 8

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
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
                <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowFilters(false)} />
                <div className="relative w-full max-w-sm bg-white rounded-3xl shadow-2xl p-6 max-h-[80vh] overflow-y-auto">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-xl font-light text-foreground">Фильтры</h3>
                        <button onClick={() => setShowFilters(false)} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
                            <X className="size-5" />
                        </button>
                    </div>
                    <div className="space-y-6">
                        <div>
                            <label className="text-xs font-medium text-muted-foreground/70 block mb-2 uppercase tracking-wider">Категория</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full rounded-2xl border border-gray-200 bg-gray-50/50 px-4 py-3 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all"
                            >
                                <option value="">Все категории</option>
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground/70 block mb-2 uppercase tracking-wider">Бренд</label>
                            <select
                                value={brand}
                                onChange={(e) => setBrand(e.target.value)}
                                className="w-full rounded-2xl border border-gray-200 bg-gray-50/50 px-4 py-3 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all"
                            >
                                <option value="">Все бренды</option>
                                {brands.map(b => <option key={b} value={b}>{b}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-medium text-muted-foreground/70 block mb-2 uppercase tracking-wider">Сортировка</label>
                            <select
                                value={sort}
                                onChange={(e) => setSort(e.target.value)}
                                className="w-full rounded-2xl border border-gray-200 bg-gray-50/50 px-4 py-3 text-sm focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all"
                            >
                                <option value="popular">По популярности</option>
                                <option value="score">По оценке</option>
                                <option value="name">По названию</option>
                            </select>
                        </div>
                        <button
                            onClick={clearFilters}
                            className="w-full py-3 rounded-2xl border border-gray-200 text-sm text-muted-foreground hover:bg-gray-50 transition-colors"
                        >
                            Сбросить все
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="h-full flex flex-col overflow-hidden bg-gradient-to-br from-slate-50 via-white to-primary/5">
            {/* ШАПКА — минималистичная */}
            <div className="flex-shrink-0 px-4 pt-3 pb-2">
                <div className="flex items-center justify-between mb-3">
                    <div>
                        <h1 className="text-xl font-light text-foreground tracking-tight">
                            {getGreeting()}
                        </h1>
                        <p className="text-[11px] text-muted-foreground/60 font-light mt-0.5">
                            {profile?.skinType ? `Тип кожи: ${profile.skinType}` : 'Выберите тип кожи'}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={onInfoClick}
                            className="w-9 h-9 rounded-2xl border border-gray-200/60 bg-white/50 flex items-center justify-center text-muted-foreground hover:text-primary hover:border-primary/30 transition-all duration-300"
                        >
                            <span className="text-sm font-light">?</span>
                        </button>
                        {!profile?.skinType && (
                            <button
                                onClick={onStartQuiz}
                                className="px-4 py-2 rounded-2xl bg-primary/10 text-primary text-[11px] font-medium hover:bg-primary/20 transition-all duration-300 flex items-center gap-1.5"
                            >
                                <Sparkles className="size-3.5" />
                                Опросник
                            </button>
                        )}
                    </div>
                </div>

                {/* ПОИСК */}
                <div className="relative mb-2">
                    <div className="flex items-center gap-2 rounded-2xl bg-white/70 backdrop-blur-sm border border-gray-200/60 px-4 py-2.5 focus-within:border-primary/40 focus-within:bg-white focus-within:shadow-[0_0_40px_rgba(108,60,225,0.06)] transition-all duration-300">
                        <Search className="size-4 shrink-0 text-muted-foreground/40" />
                        <input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Поиск продуктов..."
                            className="w-full bg-transparent text-sm placeholder:text-muted-foreground/40 focus:outline-none min-w-0"
                        />
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="p-1 rounded-full hover:bg-gray-100 transition-colors text-muted-foreground shrink-0"
                            >
                                <X className="size-3.5" />
                            </button>
                        )}
                    </div>
                </div>

                {/* ВИД + ФИЛЬТРЫ + ПАГИНАЦИЯ */}
                <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setShowFilters(true)}
                            className="px-3 py-1.5 rounded-xl border border-gray-200/60 bg-white/50 text-xs font-medium text-muted-foreground hover:text-primary hover:border-primary/30 transition-all duration-300 flex items-center gap-1.5"
                        >
                            <Filter className="size-3" />
                            Фильтр
                            {(category || brand) && (
                                <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                            )}
                        </button>
                        <div className="flex bg-white/50 border border-gray-200/60 rounded-xl overflow-hidden">
                            <button
                                onClick={() => setViewMode('grid')}
                                className={cn('p-1.5 transition-all duration-300', viewMode === 'grid' ? 'bg-primary/10 text-primary' : 'text-muted-foreground/60 hover:text-foreground')}
                            >
                                <Grid3x3 className="size-3.5" />
                            </button>
                            <button
                                onClick={() => setViewMode('list')}
                                className={cn('p-1.5 transition-all duration-300 border-l border-gray-200/60', viewMode === 'list' ? 'bg-primary/10 text-primary' : 'text-muted-foreground/60 hover:text-foreground')}
                            >
                                <LayoutList className="size-3.5" />
                            </button>
                        </div>
                    </div>

                    {totalPages > 1 && !loading && products.length > 0 && (
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => handlePageChange(currentPage - 1)}
                                disabled={currentPage === 1}
                                className={cn(
                                    'w-7 h-7 rounded-xl border transition-all duration-300 flex items-center justify-center',
                                    currentPage === 1
                                        ? 'border-gray-100 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-gray-200/60 hover:border-primary/30 hover:text-primary text-muted-foreground'
                                )}
                            >
                                <ArrowLeft className="size-3" />
                            </button>
                            <span className="text-[10px] text-muted-foreground/60 font-medium px-1.5">
                                {currentPage}/{totalPages}
                            </span>
                            <button
                                onClick={() => handlePageChange(currentPage + 1)}
                                disabled={currentPage === totalPages}
                                className={cn(
                                    'w-7 h-7 rounded-xl border transition-all duration-300 flex items-center justify-center',
                                    currentPage === totalPages
                                        ? 'border-gray-100 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-gray-200/60 hover:border-primary/30 hover:text-primary text-muted-foreground'
                                )}
                            >
                                <ArrowRight className="size-3" />
                            </button>
                        </div>
                    )}
                </div>

                {!loading && products.length > 0 && (
                    <p className="text-[10px] text-muted-foreground/40 text-center mt-2 font-light tracking-wider">
                        {total} продукта
                    </p>
                )}
            </div>

            {/* ГРИД ПРОДУКТОВ */}
            <div className="flex-1 min-h-0 overflow-hidden px-4 pb-24">
                {loading ? (
                    <div className="flex flex-col items-center justify-center h-full gap-4">
                        <div className="relative">
                            <div className="w-10 h-10 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
                        </div>
                        <p className="text-xs text-muted-foreground/40 font-light">Загрузка...</p>
                    </div>
                ) : products.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full">
                        <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-3">
                            <Search className="size-6 text-muted-foreground/40" />
                        </div>
                        <p className="text-sm text-muted-foreground font-light">Ничего не найдено</p>
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
                        className="h-full overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-gray-200 scrollbar-track-transparent hover:scrollbar-thumb-gray-300"
                        style={{
                            height: '100%',
                            overflowY: 'auto',
                            paddingRight: '0.25rem',
                        }}
                    >
                        <div className={cn(
                            'grid gap-3 pb-2',
                            viewMode === 'grid' ? 'grid-cols-2' : 'grid-cols-1'
                        )}>
                            {products.map((product, index) => (
                                <div
                                    key={product.slug}
                                    className={cn(
                                        'group relative bg-white/80 rounded-2xl border border-gray-100/80 shadow-sm hover:shadow-xl transition-all duration-500 cursor-pointer hover:-translate-y-1 hover:border-primary/20',
                                        viewMode === 'grid' ? 'p-4' : 'p-4 flex items-center gap-4'
                                    )}
                                    onClick={() => triggerCheck(product.name)}
                                >
                                    {/* Glow эффект */}
                                    <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

                                    <div className={cn(
                                        'flex relative',
                                        viewMode === 'grid' ? 'flex-col items-center w-full' : 'items-center gap-4 flex-1 min-w-0'
                                    )}>
                                        <div className={cn(
                                            'rounded-2xl overflow-hidden bg-gradient-to-br from-gray-50 to-gray-100/30 flex items-center justify-center flex-shrink-0 transition-all duration-500 group-hover:scale-[1.02]',
                                            viewMode === 'grid' ? 'w-full aspect-square' : 'w-16 h-16'
                                        )}>
                                            {product.image_url ? (
                                                <img
                                                    src={product.image_url}
                                                    alt={product.name}
                                                    loading="lazy"
                                                    className="w-full h-full object-contain p-2 group-hover:scale-110 transition-transform duration-500"
                                                />
                                            ) : (
                                                <span className="text-3xl opacity-30">🧴</span>
                                            )}
                                        </div>

                                        <div className={cn(
                                            'w-full min-w-0',
                                            viewMode === 'grid' ? 'mt-3 text-center' : 'flex-1'
                                        )}>
                                            <p className={cn(
                                                'font-medium text-foreground/90 leading-tight group-hover:text-primary transition-colors duration-300',
                                                viewMode === 'grid' ? 'text-[13px]' : 'text-sm'
                                            )}>
                                                {product.name}
                                            </p>
                                            {product.category && (
                                                <span className="text-[10px] text-muted-foreground/50 mt-1 block tracking-wide uppercase">
                                                    {product.category}
                                                </span>
                                            )}
                                            {viewMode === 'list' && (
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        triggerCheck(product.name)
                                                    }}
                                                    className="mt-2 px-3 py-1 rounded-xl bg-primary/5 text-primary text-[10px] font-medium hover:bg-primary/10 transition-all duration-300 inline-block"
                                                >
                                                    Проверить состав
                                                </button>
                                            )}
                                        </div>
                                    </div>

                                    {viewMode === 'grid' && (
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation()
                                                triggerCheck(product.name)
                                            }}
                                            className="mt-2 w-full py-1.5 rounded-xl bg-primary/5 text-primary text-[10px] font-medium hover:bg-primary/10 transition-all duration-300 relative opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0"
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

            {/* ФУТЕР — минималистичный */}
            <div className="flex-shrink-0 px-4 pb-4 pt-2 bg-gradient-to-t from-white via-white/80 to-transparent">
                {!profile?.skinType && (
                    <button
                        onClick={onGoToProfile}
                        className="w-full py-3 rounded-2xl text-xs font-medium bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/20 text-primary hover:shadow-lg hover:shadow-primary/10 transition-all duration-300 active:scale-[0.98]"
                    >
                        Заполнить анкету →
                    </button>
                )}
            </div>

            <FilterPopup />
        </div>
    )
}