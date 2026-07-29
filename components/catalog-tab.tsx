'use client'

import { useState, useEffect } from 'react'
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
    const [searchTimeout, setSearchTimeout] = useState<NodeJS.Timeout | null>(null)
    const [isFocused, setIsFocused] = useState(false)
    const [hoveredId, setHoveredId] = useState<string | null>(null)

    const limit = 6

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
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setShowFilters(false)} />
                <div className="relative w-full max-w-sm bg-white rounded-2xl shadow-xl p-6 max-h-[80vh] overflow-y-auto">
                    <div className="flex items-center justify-between mb-5">
                        <h3 className="text-base font-medium text-foreground">Фильтры</h3>
                        <button onClick={() => setShowFilters(false)} className="p-1.5 hover:bg-gray-100 rounded-full transition-colors">
                            <X className="size-4" />
                        </button>
                    </div>
                    <div className="space-y-4">
                        <div>
                            <label className="text-xs text-muted-foreground block mb-1.5">Категория</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full rounded-xl border border-gray-200 bg-white/50 px-3.5 py-2.5 text-sm focus:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary/5 transition-all"
                            >
                                <option value="">Все категории</option>
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-muted-foreground block mb-1.5">Бренд</label>
                            <select
                                value={brand}
                                onChange={(e) => setBrand(e.target.value)}
                                className="w-full rounded-xl border border-gray-200 bg-white/50 px-3.5 py-2.5 text-sm focus:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary/5 transition-all"
                            >
                                <option value="">Все бренды</option>
                                {brands.map(b => <option key={b} value={b}>{b}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs text-muted-foreground block mb-1.5">Сортировка</label>
                            <select
                                value={sort}
                                onChange={(e) => setSort(e.target.value)}
                                className="w-full rounded-xl border border-gray-200 bg-white/50 px-3.5 py-2.5 text-sm focus:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary/5 transition-all"
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

    const SkeletonCard = () => (
        <div className="bg-white/60 rounded-xl border border-gray-100/50 overflow-hidden animate-pulse">
            <div className="w-full aspect-square bg-gray-100/60" />
            <div className="p-3 space-y-2">
                <div className="h-3.5 bg-gray-100/60 rounded-full w-3/4" />
                <div className="h-2.5 bg-gray-100/40 rounded-full w-1/2" />
            </div>
        </div>
    )

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Хедер */}
            <div className="flex-shrink-0 pt-1 pb-2">
                <div className="flex items-center justify-between mb-2.5">
                    <div>
                        <h1 className="text-lg font-medium text-foreground">
                            {getGreeting()}
                        </h1>
                        <span className="text-[10px] text-muted-foreground/60">
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
                            className="w-8 h-8 rounded-xl border border-gray-200/50 bg-white/50 flex items-center justify-center text-muted-foreground hover:text-primary hover:border-primary/30 transition-all duration-300 text-sm"
                        >
                            ?
                        </button>
                    </div>
                </div>

                {/* Поиск */}
                <div className={cn(
                    'relative rounded-xl transition-all duration-300',
                    isFocused ? 'shadow-[0_0_40px_rgba(108,60,225,0.05)]' : ''
                )}>
                    <div className={cn(
                        'flex items-center gap-2.5 rounded-xl border px-3.5 py-2 transition-all duration-300',
                        isFocused 
                            ? 'border-primary/30 bg-white shadow-sm' 
                            : 'border-gray-200/50 bg-white/60'
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
                            className="w-full bg-transparent text-sm placeholder:text-muted-foreground/30 focus:outline-none"
                        />
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="p-1 rounded-full hover:bg-gray-100/50 transition-colors"
                            >
                                <X className="size-3.5 text-muted-foreground/40" />
                            </button>
                        )}
                    </div>
                </div>

                {/* Фильтры + пагинация */}
                <div className="flex items-center justify-between mt-2.5">
                    <button
                        onClick={() => setShowFilters(true)}
                        className="px-3 py-1.5 rounded-xl border border-gray-200/50 bg-white/50 text-[10px] text-muted-foreground hover:text-primary hover:border-primary/30 transition-all duration-300 flex items-center gap-1.5"
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
                                    'w-7 h-7 rounded-xl border transition-all duration-300 flex items-center justify-center',
                                    currentPage === 1
                                        ? 'border-gray-100 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-gray-200/50 hover:border-primary/30 hover:text-primary text-muted-foreground/60'
                                )}
                            >
                                <ArrowRight className="size-3 rotate-180" />
                            </button>
                            <span className="text-[10px] text-muted-foreground/40 px-1.5 min-w-[32px] text-center">
                                {currentPage}/{totalPages}
                            </span>
                            <button
                                onClick={() => handlePageChange(currentPage + 1)}
                                disabled={currentPage === totalPages}
                                className={cn(
                                    'w-7 h-7 rounded-xl border transition-all duration-300 flex items-center justify-center',
                                    currentPage === totalPages
                                        ? 'border-gray-100 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-gray-200/50 hover:border-primary/30 hover:text-primary text-muted-foreground/60'
                                )}
                            >
                                <ArrowRight className="size-3" />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* Галерея - БЕЗ АНИМАЦИИ */}
            <div className="flex-1 min-h-0 overflow-hidden">
                {loading ? (
                    <div className="grid grid-cols-2 gap-2.5 pb-2">
                        {Array.from({ length: 6 }).map((_, i) => (
                            <SkeletonCard key={i} />
                        ))}
                    </div>
                ) : products.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full">
                        <div className="w-16 h-16 rounded-full bg-gray-100/50 flex items-center justify-center mb-3">
                            <Compass className="size-6 text-muted-foreground/20" />
                        </div>
                        <p className="text-sm text-muted-foreground/50">Ничего не найдено</p>
                    </div>
                ) : (
                    <div className="h-full overflow-y-auto pr-0.5 scrollbar-thin scrollbar-thumb-gray-200/50 scrollbar-track-transparent pb-20">
                        <div className="grid grid-cols-2 gap-2.5 pb-2">
                            {products.map((product) => {
                                const isHovered = hoveredId === product.slug
                                return (
                                    <div
                                        key={product.slug}
                                        className={cn(
                                            'bg-white/80 rounded-xl border border-gray-100/50 shadow-sm overflow-hidden cursor-pointer transition-all duration-300',
                                            isHovered ? 'scale-[1.02] shadow-md border-primary/20' : 'hover:scale-[1.02] hover:shadow-md'
                                        )}
                                        onMouseEnter={() => setHoveredId(product.slug)}
                                        onMouseLeave={() => setHoveredId(null)}
                                        onClick={() => triggerCheck(product.name)}
                                    >
                                        <div className="w-full aspect-square overflow-hidden bg-gray-50/50 flex items-center justify-center">
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
                                            <p className="text-xs font-medium text-foreground/90 line-clamp-2 leading-snug">
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
                                                    'w-full mt-1.5 py-1.5 rounded-xl text-[9px] font-medium transition-all duration-300',
                                                    isHovered 
                                                        ? 'bg-primary/10 text-primary opacity-100' 
                                                        : 'bg-transparent text-transparent opacity-0'
                                                )}
                                            >
                                                Проверить
                                            </button>
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                )}
            </div>

            {/* Футер */}
            <div className="flex-shrink-0 pb-3 pt-1 bg-gradient-to-t from-[#FAF9F6] via-[#FAF9F6]/80 to-transparent">
                {!profile?.skinType && (
                    <button
                        onClick={onGoToProfile}
                        className="w-full py-2.5 rounded-xl text-xs font-medium bg-primary/5 border border-primary/15 text-primary hover:bg-primary/10 transition-all duration-300 active:scale-[0.98] flex items-center justify-center gap-2"
                    >
                        <Zap className="size-3.5" />
                        Заполнить анкету
                        <ArrowRight className="size-3.5" />
                    </button>
                )}
            </div>

            <FilterPopup />
        </div>
    )
}