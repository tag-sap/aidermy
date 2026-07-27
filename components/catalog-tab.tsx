'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, Filter, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SkinProfile } from '@/lib/store'

interface Product {
    name: string
    slug: string
    image_url: string | null
    ingredients: string | null
    category: string | null
    brand: string | null
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

export function CatalogTab({
    onCheck,
    profile,
}: {
    onCheck?: (product: string, skinType: string) => void
    profile?: SkinProfile
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

    const limit = 20
    const cardStyle = "relative overflow-hidden bg-gradient-to-br from-primary/10 via-primary/5 to-transparent rounded-2xl p-5 border border-primary/20 backdrop-blur-sm hover:shadow-md transition-shadow"

    useEffect(() => {
        const timer = setTimeout(() => setIsVisible(true), 50)
        return () => clearTimeout(timer)
    }, [])

    useEffect(() => {
        fetchCategories()
        fetchProducts()
    }, [])

    useEffect(() => {
        fetchProducts()
    }, [category, brand, sort, offset, search])

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

    const totalPages = Math.ceil(total / limit)
    const currentPage = Math.floor(offset / limit) + 1

    const handlePageChange = (page: number) => {
        setOffset((page - 1) * limit)
        window.scrollTo({ top: 0, behavior: 'smooth' })
    }

    const triggerCheck = (productName: string) => {
        if (onCheck && profile) {
            onCheck(productName, profile.skinType || 'Нормальная')
        }
    }

    return (
        <div className="flex flex-col gap-5 max-w-md mx-auto">
            {/* Заголовок */}
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-normal text-foreground">Каталог</h1>
                <button
                    onClick={() => setShowFilters(!showFilters)}
                    className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors"
                >
                    <Filter className="size-4" />
                    Фильтры
                </button>
            </div>

            {/* Поиск */}
            <div className="cardStyle relative">
                <div className="flex items-center gap-3 rounded-xl border px-4 py-2.5 bg-white/50 border-gray-200/70">
                    <Search className="size-4 shrink-0 text-muted-foreground" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Поиск по каталогу..."
                        className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/60 focus:outline-none text-sm"
                    />
                    {search && (
                        <button onClick={() => setSearch('')} className="text-muted-foreground/50 hover:text-foreground">
                            ✕
                        </button>
                    )}
                </div>
            </div>

            {/* Фильтры */}
            {showFilters && (
                <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-1')}>
                    <div className="relative z-10">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-normal text-foreground">Фильтры</h3>
                            <button onClick={() => { setCategory(''); setBrand('') }} className="text-xs text-primary hover:underline">
                                Сбросить
                            </button>
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="text-xs text-muted-foreground block mb-1.5">Категория</label>
                                <select
                                    value={category}
                                    onChange={(e) => setCategory(e.target.value)}
                                    className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
                                >
                                    <option value="">Все категории</option>
                                    {categories.map(c => (
                                        <option key={c} value={c}>{c}</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="text-xs text-muted-foreground block mb-1.5">Бренд</label>
                                <select
                                    value={brand}
                                    onChange={(e) => setBrand(e.target.value)}
                                    className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
                                >
                                    <option value="">Все бренды</option>
                                    {brands.map(b => (
                                        <option key={b} value={b}>{b}</option>
                                    ))}
                                </select>
                            </div>

                            <div>
                                <label className="text-xs text-muted-foreground block mb-1.5">Сортировка</label>
                                <select
                                    value={sort}
                                    onChange={(e) => setSort(e.target.value)}
                                    className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
                                >
                                    <option value="popular">По популярности</option>
                                    <option value="score">По оценке</option>
                                    <option value="name">По названию</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Список продуктов */}
            {loading ? (
                <div className="flex justify-center py-10">
                    <div className="animate-spin rounded-full h-8 w-8 border-4 border-primary/30 border-t-primary" />
                </div>
            ) : products.length === 0 ? (
                <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-1')}>
                    <div className="relative z-10 text-center py-8">
                        <p className="text-muted-foreground">Ничего не найдено</p>
                    </div>
                </div>
            ) : (
                <div className="flex flex-col gap-3">
                    {products.map((product, index) => (
                        <div
                            key={product.slug}
                            className={cn(
                                cardStyle,
                                'card-enter cursor-pointer',
                                isVisible && `card-enter-${Math.min(index + 1, 6)}`
                            )}
                            style={{ animationDelay: `${index * 0.05}s` }}
                            onClick={() => triggerCheck(product.name)}
                        >
                            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
                            <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
                            <div className="relative z-10 flex items-center gap-4">
                                {product.image_url && (
                                    <div className="product-image-wrapper">
                                        <img
                                            src={p.image_url}
                                            alt={p.name}
                                            className="product-image"
                                        />
                                    </div>
                                )}
                                <div className="flex-1 min-w-0">
                                    <MarqueeText text={product.name} className="text-sm font-normal text-foreground" />
                                    {product.category && (
                                        <span className="text-xs text-muted-foreground">{product.category}</span>
                                    )}
                                </div>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation()
                                        triggerCheck(product.name)
                                    }}
                                    className="px-3 py-1.5 rounded-full bg-primary/10 text-primary text-xs font-normal hover:bg-primary/20 transition-colors"
                                >
                                    Проверить
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Пагинация */}
            {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 py-4">
                    <button
                        onClick={() => handlePageChange(currentPage - 1)}
                        disabled={currentPage === 1}
                        className="p-2 rounded-xl border border-gray-200 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                    >
                        <ChevronLeft className="size-4" />
                    </button>
                    <span className="text-sm text-muted-foreground">
                        {currentPage} / {totalPages}
                    </span>
                    <button
                        onClick={() => handlePageChange(currentPage + 1)}
                        disabled={currentPage === totalPages}
                        className="p-2 rounded-xl border border-gray-200 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
                    >
                        <ChevronRight className="size-4" />
                    </button>
                </div>
            )}
        </div>
    )
}