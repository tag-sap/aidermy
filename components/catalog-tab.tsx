'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, X, Sparkles, ArrowRight, Compass, Zap, Heart, Eye, TrendingUp, Clock } from 'lucide-react'
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
    const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
    const [isFocused, setIsFocused] = useState(false)

    const inputRef = useRef<HTMLInputElement>(null)

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

    // ===== ВИЗУАЛЬНЫЕ СОСТОЯНИЯ =====
    const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
    const [rotationAngles] = useState(() =>
        products.map(() => (Math.random() - 0.5) * 4)
    )

    const FilterPopup = () => {
        if (!showFilters) return null
        return (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
                <div className="absolute inset-0 bg-black/50 backdrop-blur-md" onClick={() => setShowFilters(false)} />
                <div className="relative w-full max-w-sm bg-white/90 backdrop-blur-xl rounded-3xl shadow-2xl p-6 border border-white/20 max-h-[80vh] overflow-y-auto">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-light text-foreground">Настроить поиск</h3>
                        <button onClick={() => setShowFilters(false)} className="p-2 hover:bg-gray-100/50 rounded-full transition-colors">
                            <X className="size-5" />
                        </button>
                    </div>
                    <div className="space-y-5">
                        <div>
                            <label className="text-xs font-light text-muted-foreground/70 block mb-2">Категория</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full rounded-2xl border border-gray-200/50 bg-white/50 px-4 py-3 text-sm focus:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary/5 transition-all"
                            >
                                <option value="">Все категории</option>
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-light text-muted-foreground/70 block mb-2">Бренд</label>
                            <select
                                value={brand}
                                onChange={(e) => setBrand(e.target.value)}
                                className="w-full rounded-2xl border border-gray-200/50 bg-white/50 px-4 py-3 text-sm focus:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary/5 transition-all"
                            >
                                <option value="">Все бренды</option>
                                {brands.map(b => <option key={b} value={b}>{b}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-light text-muted-foreground/70 block mb-2">Сортировка</label>
                            <select
                                value={sort}
                                onChange={(e) => setSort(e.target.value)}
                                className="w-full rounded-2xl border border-gray-200/50 bg-white/50 px-4 py-3 text-sm focus:border-primary/30 focus:outline-none focus:ring-2 focus:ring-primary/5 transition-all"
                            >
                                <option value="popular">По популярности</option>
                                <option value="score">По оценке</option>
                                <option value="name">По названию</option>
                            </select>
                        </div>
                        <button
                            onClick={clearFilters}
                            className="w-full py-3 rounded-2xl border border-gray-200/50 text-sm text-muted-foreground hover:bg-gray-50/50 transition-colors"
                        >
                            Сбросить все
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    // ===== КОМПОНЕНТ КАРТОЧКИ =====
    const ProductCard = ({ product, index }: { product: Product; index: number }) => {
        const isHovered = hoveredIndex === index

        return (
            <div
                className={cn(
                    'group relative bg-white/60 backdrop-blur-sm rounded-3xl border border-white/40 shadow-sm transition-all duration-500 cursor-pointer overflow-hidden',
                    isHovered ? 'scale-[1.02] shadow-2xl border-primary/20' : 'hover:scale-[1.02] hover:shadow-xl'
                )}
                style={{
                    transform: `rotate(${rotationAngles[index] || 0}deg)`,
                    transition: 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
                }}
                onMouseEnter={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
                onClick={() => triggerCheck(product.name)}
            >
                {/* Градиентный фон */}
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />

                {/* Изображение */}
                <div className={cn(
                    'w-full aspect-square overflow-hidden bg-gradient-to-br from-gray-50 to-gray-100/30 flex items-center justify-center',
                    'transition-all duration-700',
                    isHovered ? 'scale-105' : ''
                )}>
                    {product.image_url ? (
                        <img
                            src={product.image_url}
                            alt={product.name}
                            loading="lazy"
                            className="w-full h-full object-contain p-4 group-hover:scale-110 transition-transform duration-700"
                        />
                    ) : (
                        <span className="text-5xl opacity-20">🧴</span>
                    )}
                </div>

                {/* Информация */}
                <div className="p-4 space-y-1">
                    <p className="text-sm font-medium text-foreground/90 line-clamp-2 leading-snug group-hover:text-primary transition-colors duration-300">
                        {product.name}
                    </p>
                    {product.category && (
                        <p className="text-[10px] text-muted-foreground/40 uppercase tracking-wider font-light">
                            {product.category}
                        </p>
                    )}

                    {/* Кнопка "Проверить" появляется при наведении */}
                    <div className={cn(
                        'overflow-hidden transition-all duration-500',
                        isHovered ? 'max-h-12 opacity-100 mt-2' : 'max-h-0 opacity-0'
                    )}>
                        <button
                            onClick={(e) => {
                                e.stopPropagation()
                                triggerCheck(product.name)
                            }}
                            className="w-full py-2 rounded-2xl bg-primary/10 text-primary text-[11px] font-medium hover:bg-primary/20 transition-all duration-300 flex items-center justify-center gap-2"
                        >
                            Проверить состав
                            <ArrowRight className="size-3.5" />
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="h-full flex flex-col overflow-hidden bg-gradient-to-br from-slate-50 via-white to-primary/[0.03]">
            {/* === ХЕДЕР === */}
            <div className="flex-shrink-0 px-6 pt-4 pb-3">
                {/* Верхняя строка */}
                <div className="flex items-start justify-between mb-4">
                    <div>
                        <h1 className="text-2xl font-light text-foreground tracking-tight">
                            {getGreeting()}
                        </h1>
                        <div className="flex items-center gap-3 mt-1">
                            <span className="text-[11px] text-muted-foreground/50 font-light">
                                {profile?.skinType ? `Тип кожи: ${profile.skinType}` : 'Выберите тип кожи'}
                            </span>
                            {!profile?.skinType && (
                                <button
                                    onClick={onStartQuiz}
                                    className="text-[10px] text-primary/70 hover:text-primary transition-colors flex items-center gap-1"
                                >
                                    <Sparkles className="size-3" />
                                    Пройти опросник
                                </button>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={onInfoClick}
                        className="w-10 h-10 rounded-2xl border border-gray-200/50 bg-white/50 flex items-center justify-center text-muted-foreground hover:text-primary hover:border-primary/30 transition-all duration-300 text-sm font-light"
                    >
                        ?
                    </button>
                </div>

                {/* Поиск — увеличенный, с фокусом */}
                <div className={cn(
                    'relative rounded-2xl transition-all duration-300',
                    isFocused ? 'shadow-[0_0_50px_rgba(108,60,225,0.08)]' : ''
                )}>
                    <div className={cn(
                        'flex items-center gap-3 rounded-2xl border px-5 py-3.5 transition-all duration-300',
                        isFocused
                            ? 'border-primary/30 bg-white shadow-sm'
                            : 'border-gray-200/50 bg-white/60 backdrop-blur-sm'
                    )}>
                        <Search className={cn(
                            'size-4 transition-colors duration-300',
                            isFocused ? 'text-primary' : 'text-muted-foreground/30'
                        )} />
                        <input
                            ref={inputRef}
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            onFocus={() => setIsFocused(true)}
                            onBlur={() => setIsFocused(false)}
                            placeholder="Что ищем сегодня? ✨"
                            className="w-full bg-transparent text-sm placeholder:text-muted-foreground/30 focus:outline-none"
                        />
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="p-1.5 rounded-full hover:bg-gray-100/50 transition-colors"
                            >
                                <X className="size-3.5 text-muted-foreground/40" />
                            </button>
                        )}
                    </div>
                </div>

                {/* Фильтры и навигация */}
                <div className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setShowFilters(true)}
                            className="px-3.5 py-2 rounded-2xl border border-gray-200/50 bg-white/50 text-xs font-light text-muted-foreground hover:text-primary hover:border-primary/30 transition-all duration-300 flex items-center gap-2"
                        >
                            <span>Фильтры</span>
                            {(category || brand) && (
                                <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                            )}
                        </button>
                        {!loading && products.length > 0 && (
                            <span className="text-[10px] text-muted-foreground/30 font-light ml-1">
                                {total} продуктов
                            </span>
                        )}
                    </div>

                    {totalPages > 1 && !loading && (
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => handlePageChange(currentPage - 1)}
                                disabled={currentPage === 1}
                                className={cn(
                                    'w-8 h-8 rounded-2xl border transition-all duration-300 flex items-center justify-center',
                                    currentPage === 1
                                        ? 'border-gray-100 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-gray-200/50 hover:border-primary/30 hover:text-primary text-muted-foreground/60 hover:bg-white/50'
                                )}
                            >
                                <ArrowRight className="size-3.5 rotate-180" />
                            </button>
                            <span className="text-[10px] text-muted-foreground/40 font-light px-2 min-w-[40px] text-center">
                                {currentPage}/{totalPages}
                            </span>
                            <button
                                onClick={() => handlePageChange(currentPage + 1)}
                                disabled={currentPage === totalPages}
                                className={cn(
                                    'w-8 h-8 rounded-2xl border transition-all duration-300 flex items-center justify-center',
                                    currentPage === totalPages
                                        ? 'border-gray-100 text-muted-foreground/20 cursor-not-allowed'
                                        : 'border-gray-200/50 hover:border-primary/30 hover:text-primary text-muted-foreground/60 hover:bg-white/50'
                                )}
                            >
                                <ArrowRight className="size-3.5" />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* === ГАЛЕРЕЯ === */}
            <div className="flex-1 min-h-0 overflow-hidden px-6 pb-24">
                {loading ? (
                    <div className="flex flex-col items-center justify-center h-full gap-4">
                        <div className="relative w-12 h-12">
                            <div className="absolute inset-0 rounded-full border-2 border-primary/20 border-t-primary animate-spin" />
                            <div className="absolute inset-2 rounded-full border-2 border-primary/5 animate-pulse" />
                        </div>
                        <p className="text-xs text-muted-foreground/30 font-light animate-pulse">Ищем...</p>
                    </div>
                ) : products.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center">
                        <div className="w-20 h-20 rounded-full bg-gray-100/50 flex items-center justify-center mb-4">
                            <Compass className="size-8 text-muted-foreground/20" />
                        </div>
                        <p className="text-sm text-muted-foreground/50 font-light">Ничего не найдено</p>
                        <p className="text-xs text-muted-foreground/30 font-light mt-1">Попробуйте изменить поиск</p>
                        {search && (
                            <button
                                onClick={() => setSearch('')}
                                className="mt-4 px-6 py-2 rounded-2xl bg-primary/5 text-primary text-xs hover:bg-primary/10 transition-colors"
                            >
                                Очистить поиск
                            </button>
                        )}
                    </div>
                ) : (
                    <div
                        className="h-full overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-gray-200/50 scrollbar-track-transparent"
                        style={{
                            height: '100%',
                            overflowY: 'auto',
                            paddingRight: '0.25rem',
                        }}
                    >
                        <div className="grid grid-cols-2 gap-3 pb-2">
                            {products.map((product, index) => (
                                <ProductCard key={product.slug} product={product} index={index} />
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* === ФУТЕР === */}
            <div className="flex-shrink-0 px-6 pb-4 pt-2 bg-gradient-to-t from-white via-white/80 to-transparent">
                {!profile?.skinType && (
                    <button
                        onClick={onGoToProfile}
                        className="w-full py-3.5 rounded-2xl text-sm font-light bg-gradient-to-r from-primary/5 to-primary/10 border border-primary/20 text-primary hover:shadow-lg hover:shadow-primary/10 transition-all duration-300 active:scale-[0.98] flex items-center justify-center gap-2"
                    >
                        <Zap className="size-4" />
                        Заполнить анкету
                        <ArrowRight className="size-4" />
                    </button>
                )}
            </div>

            <FilterPopup />
        </div>
    )
}