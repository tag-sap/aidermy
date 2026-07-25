'use client'

import { useState, useEffect, useRef } from 'react'
import { Search, X, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Product {
    name: string
    slug: string
    image_url: string | null
    category: string | null
    brand: string | null
}

export function CatalogDropdown({
    isOpen,
    onClose,
    onSelectProduct,
}: {
    isOpen: boolean
    onClose: () => void
    onSelectProduct: (name: string) => void
}) {
    const [search, setSearch] = useState('')
    const [category, setCategory] = useState('')
    const [brand, setBrand] = useState('')
    const [products, setProducts] = useState<Product[]>([])
    const [loading, setLoading] = useState(false)
    const [categories, setCategories] = useState<string[]>([])
    const [brands, setBrands] = useState<string[]>([])
    const [showCategories, setShowCategories] = useState(true)
    const dropdownRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                onClose()
            }
        }
        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside)
            fetchCategories()
            fetchProducts()
        }
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [isOpen])

    useEffect(() => {
        const timer = setTimeout(() => {
            fetchProducts()
        }, 300)
        return () => clearTimeout(timer)
    }, [search, category, brand])

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
            const params = new URLSearchParams()
            if (category) params.append('category', category)
            if (brand) params.append('brand', brand)
            if (search) params.append('search', search)
            params.append('limit', '50')

            const res = await fetch(`/api/catalog?${params}`)
            const data = await res.json()
            setProducts(data.products || [])
        } catch (error) {
            console.error('Ошибка загрузки продуктов:', error)
        } finally {
            setLoading(false)
        }
    }

    if (!isOpen) return null

    return (
        <div ref={dropdownRef} className="absolute top-full left-0 right-0 mt-2 z-[9999] bg-white rounded-2xl shadow-2xl border border-gray-200 max-h-[80vh] overflow-hidden">
            <div className="p-4 border-b border-gray-100">
                <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-normal text-foreground">Каталог</h3>
                    <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-full transition-colors">
                        <X className="size-4" />
                    </button>
                </div>

                {/* Поиск */}
                <div className="flex items-center gap-2 rounded-xl border border-gray-200 px-3 py-2 bg-gray-50">
                    <Search className="size-4 shrink-0 text-muted-foreground" />
                    <input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Искать по каталогу..."
                        className="w-full bg-transparent text-sm focus:outline-none"
                    />
                    {search && (
                        <button onClick={() => setSearch('')} className="text-muted-foreground">
                            ✕
                        </button>
                    )}
                </div>
            </div>

            <div className="flex h-[400px]">
                {/* Фильтры слева */}
                <div className="w-1/3 border-r border-gray-100 overflow-y-auto p-3">
                    <button
                        onClick={() => setShowCategories(!showCategories)}
                        className="flex items-center justify-between w-full text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2"
                    >
                        Категории
                        {showCategories ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
                    </button>
                    {showCategories && (
                        <div className="space-y-1">
                            <button
                                onClick={() => setCategory('')}
                                className={cn(
                                    'w-full text-left text-sm px-2 py-1 rounded transition-colors',
                                    !category ? 'bg-primary/10 text-primary' : 'hover:bg-gray-50'
                                )}
                            >
                                Все
                            </button>
                            {categories.map(c => (
                                <button
                                    key={c}
                                    onClick={() => setCategory(c)}
                                    className={cn(
                                        'w-full text-left text-sm px-2 py-1 rounded transition-colors',
                                        category === c ? 'bg-primary/10 text-primary' : 'hover:bg-gray-50'
                                    )}
                                >
                                    {c}
                                </button>
                            ))}
                        </div>
                    )}

                    <div className="mt-4">
                        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Бренды</p>
                        <div className="space-y-1 max-h-40 overflow-y-auto">
                            <button
                                onClick={() => setBrand('')}
                                className={cn(
                                    'w-full text-left text-sm px-2 py-1 rounded transition-colors',
                                    !brand ? 'bg-primary/10 text-primary' : 'hover:bg-gray-50'
                                )}
                            >
                                Все
                            </button>
                            {brands.slice(0, 20).map(b => (
                                <button
                                    key={b}
                                    onClick={() => setBrand(b)}
                                    className={cn(
                                        'w-full text-left text-sm px-2 py-1 rounded transition-colors',
                                        brand === b ? 'bg-primary/10 text-primary' : 'hover:bg-gray-50'
                                    )}
                                >
                                    {b}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Список продуктов */}
                <div className="flex-1 overflow-y-auto p-3">
                    {loading ? (
                        <div className="flex justify-center items-center h-full">
                            <div className="animate-spin rounded-full h-6 w-6 border-4 border-primary/30 border-t-primary" />
                        </div>
                    ) : products.length === 0 ? (
                        <div className="flex justify-center items-center h-full text-sm text-muted-foreground">
                            Ничего не найдено
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {products.map((p) => (
                                <button
                                    key={p.slug}
                                    onClick={() => {
                                        onSelectProduct(p.name)
                                        onClose()
                                    }}
                                    className="w-full flex items-center gap-3 p-2 rounded-xl hover:bg-gray-50 transition-colors text-left"
                                >
                                    {p.image_url && (
                                        <img src={p.image_url} alt={p.name} className="w-10 h-10 object-cover rounded-lg flex-shrink-0 bg-gray-100" />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-normal text-foreground truncate">{p.name}</p>
                                        {p.category && (
                                            <p className="text-xs text-muted-foreground">{p.category}</p>
                                        )}
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}