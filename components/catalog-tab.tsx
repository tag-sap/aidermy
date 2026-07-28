'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, Filter, ChevronLeft, ChevronRight, Info, Sparkles, X } from 'lucide-react'
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
    const [isVisible, setIsVisible] = useState(false)
    const [skinTypeIndex, setSkinTypeIndex] = useState(() => {
        const defaultIndex = SKIN_TYPES.indexOf(profile?.skinType || '')
        return defaultIndex >= 0 ? defaultIndex : 0
    })
    const [isSearchSticky, setIsSearchSticky] = useState(false)
    const searchRef = useRef<HTMLDivElement>(null)
    const stickySentinelRef = useRef<HTMLDivElement>(null)
    const productsContainerRef = useRef<HTMLDivElement>(null)

    const limit = 6
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

    // Intersection Observer для прилипания поиска
    useEffect(() => {
        const observer = new IntersectionObserver(
            ([entry]) => {
                setIsSearchSticky(!entry.isIntersecting)
            },
            {
                root: null,
                rootMargin: '-80px 0px 0px 0px',
                threshold: 0
            }
        )

        if (stickySentinelRef.current) {
            observer.observe(stickySentinelRef.current)
        }

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
        // Скроллим к контейнеру с продуктами, а не наверх
        if (productsContainerRef.current) {
            setTimeout(() => {
                const top = productsContainerRef.current?.getBoundingClientRect().top + window.scrollY - 100
                window.scrollTo({ top, behavior: 'smooth' })
            }, 100)
        }
    }

    const triggerCheck = (productName: string) => {
        if (onCheck && profile) {
            onCheck(productName, profile.skinType || SKIN_TYPES[skinTypeIndex])
        }
    }

    const getGreeting = () => {
        const name = profile?.name || ''
        const base = name ? `Привет, ${name}.` : 'Привет.'
        return `${base} Что ищем?`
    }

    const handleSkinTypeChange = (direction: 'left' | 'right') => {
        if (profile?.skinType) return
        const newIndex = direction === 'left'
            ? (skinTypeIndex - 1 + SKIN_TYPES.length) % SKIN_TYPES.length
            : (skinTypeIndex + 1) % SKIN_TYPES.length
        setSkinTypeIndex(newIndex)
    }

    const FilterPopup = () => {
        if (!showFilters) return null

        return (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={() => setShowFilters(false)} />
                <div className="relative w-full max-w-sm bg-white rounded-2xl shadow-2xl p-6 animate-in fade-in zoom-in duration-200">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-normal text-foreground">Фильтры</h3>
                        <button onClick={() => setShowFilters(false)} className="p-1 hover:bg-gray-100 rounded-full transition-colors">
                            <X className="size-5" />
                        </button>
                    </div>

                    <div className="space-y-5">
                        <div>
                            <label className="text-xs text-muted-foreground block mb-1.5">Категория</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
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
                                className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
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
                                className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none"
                            >
                                <option value="popular">По популярности</option>
                                <option value="score">По оценке</option>
                                <option value="name">По названию</option>
                            </select>
                        </div>

                        <button
                            onClick={() => { setCategory(''); setBrand(''); setSort('popular') }}
                            className="w-full py-2 rounded-xl border border-gray-200 text-sm text-muted-foreground hover:bg-gray-50 transition-colors"
                        >
                            Сбросить все
                        </button>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="flex flex-col gap-5 max-w-md mx-auto pb-20">
            {/* СЕНТИНЕЛЬ ДЛЯ СЛЕЖЕНИЯ ЗА СКРОЛЛОМ */}
            <div ref={stickySentinelRef} className="h-0" />

            {/* ПРИВЕТСТВИЕ + КАК ЭТО РАБОТАЕТ */}
            <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-1')}>
                <div className="relative z-10">
                    <div className="flex items-center justify-between">
                        <h1 className="text-2xl font-normal text-foreground tracking-tight">{getGreeting()}</h1>
                        <button
                            onClick={onInfoClick}
                            className="px-3 py-1.5 rounded-full bg-white/50 text-xs text-muted-foreground hover:text-primary hover:bg-white transition-colors border border-gray-200/50 backdrop-blur-sm"
                        >
                            <Info className="inline size-3 mr-1" />Как это работает
                        </button>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">Найди и проверь косметику</p>
                </div>
            </div>

            {/* ПОИСК + ФИЛЬТР — ПРИЛИПАЕТ */}
            <div
                ref={searchRef}
                className={cn(
                    cardStyle,
                    'transition-all duration-300 z-40',
                    isSearchSticky && 'fixed top-0 left-0 right-0 mx-auto max-w-md rounded-none border-t-0 shadow-lg'
                )}
                style={{
                    marginTop: isSearchSticky ? '0' : '',
                    borderRadius: isSearchSticky ? '0' : '',
                }}
            >
                <div className="relative z-10">
                    <div className="flex items-center gap-2 mb-3">
                        <label className="block text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground flex-1">
                            {isSearchSticky ? '🔍 Поиск' : 'Поиск'}
                        </label>
                        <button
                            onClick={() => setShowFilters(true)}
                            className="p-1.5 rounded-lg hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                        >
                            <Filter className="size-4" />
                        </button>
                    </div>
                    <div className="relative">
                        <div className="flex items-center gap-3 rounded-xl border px-4 py-3 bg-white/50 transition-all border-gray-200/50 hover:border-gray-300">
                            <Search className="size-4 shrink-0 text-muted-foreground" />
                            <input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Введи название или состав..."
                                className="w-full bg-transparent text-foreground placeholder:text-muted-foreground/60 focus:outline-none text-sm"
                            />
                            {search && (
                                <button onClick={() => setSearch('')} className="text-muted-foreground/50 hover:text-foreground">
                                    ✕
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* ОТСТУП ДЛЯ ПРИЛИПШЕГО ПОИСКА */}
            {isSearchSticky && <div className="h-24" />}

            {/* ТИП КОЖИ — КАРУСЕЛЬ СО СТРЕЛКАМИ */}
            <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-2')}>
                <div className="relative z-10">
                    <label className="block text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground mb-3 text-center">
                        {profile?.skinType ? 'Твой тип кожи' : 'Выбери тип кожи'}
                    </label>

                    {profile?.skinType ? (
                        <div className="text-center">
                            <span className="text-sm font-normal">{profile.skinType}</span>
                            {onStartQuiz && (
                                <button onClick={onStartQuiz} className="ml-3 text-xs text-primary hover:underline">
                                    <Sparkles className="inline size-3 mr-1" />Обновить
                                </button>
                            )}
                        </div>
                    ) : (
                        <div className="flex items-center justify-center gap-4">
                            <button
                                onClick={() => handleSkinTypeChange('left')}
                                className="p-2 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                            >
                                <ChevronLeft className="size-5" />
                            </button>
                            <span className="text-sm font-normal min-w-[120px] text-center transition-all duration-200">
                                {SKIN_TYPES[skinTypeIndex]}
                            </span>
                            <button
                                onClick={() => handleSkinTypeChange('right')}
                                className="p-2 rounded-full hover:bg-primary/5 transition-colors text-muted-foreground hover:text-primary"
                            >
                                <ChevronRight className="size-5" />
                            </button>
                        </div>
                    )}
                </div>
            </div>

            {/* КАТАЛОГ — КАРТОЧКИ ПО 2 В РЯДУ */}
            <div
                ref={productsContainerRef}
                className={cn('card-enter', isVisible && 'card-enter-3')}
            >
                {loading ? (
                    <div className="flex justify-center py-10">
                        <div className="animate-spin rounded-full h-8 w-8 border-4 border-primary/30 border-t-primary" />
                    </div>
                ) : products.length === 0 ? (
                    <div className={cn(cardStyle)}>
                        <div className="relative z-10 text-center py-8">
                            <p className="text-muted-foreground">Ничего не найдено</p>
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="grid grid-cols-2 gap-3 min-h-[60vh]">
                            {products.map((product, index) => (
                                <div
                                    key={product.slug}
                                    className={cn(
                                        'bg-white/70 backdrop-blur-sm rounded-2xl p-3 border border-gray-200/70 shadow-sm hover:shadow-md transition-all cursor-pointer hover:border-primary/30',
                                        'card-enter',
                                        isVisible && `card-enter-${Math.min(index + 1, 6)}`
                                    )}
                                    style={{ animationDelay: `${index * 0.05}s` }}
                                    onClick={() => triggerCheck(product.name)}
                                >
                                    <div className="flex flex-col items-center">
                                        {product.image_url ? (
                                            <div className="w-full aspect-square rounded-xl overflow-hidden bg-gray-100 flex items-center justify-center">
                                                <img
                                                    src={product.image_url}
                                                    alt={product.name}
                                                    className="w-full h-full object-contain p-2"
                                                />
                                            </div>
                                        ) : (
                                            <div className="w-full aspect-square rounded-xl bg-gray-100 flex items-center justify-center text-4xl">
                                                🧴
                                            </div>
                                        )}
                                        <div className="mt-2 text-center w-full">
                                            <p className="text-xs font-normal text-foreground line-clamp-2 leading-tight">
                                                {product.name}
                                            </p>
                                            {product.category && (
                                                <span className="text-[10px] text-muted-foreground mt-0.5 block">
                                                    {product.category}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {totalPages > 1 && (
                            <div className="flex items-center justify-center gap-2 py-4 mt-2">
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
                <div className={cn('card-enter', isVisible && 'card-enter-4')}>
                    <button onClick={onGoToProfile} className="w-full text-sm text-primary hover:text-primary/80 transition-colors flex items-center gap-1 justify-center py-3 bg-gradient-to-br from-primary/10 via-primary/5 to-transparent rounded-2xl border border-primary/20 backdrop-blur-sm px-4">
                        Заполни анкету для точных рекомендаций
                    </button>
                </div>
            )}

            {/* ФИЛЬТРЫ — ПОПАП ПОВЕРХ */}
            <FilterPopup />
        </div>
    )
}