'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Camera, Link2, LoaderCircle, Search } from 'lucide-react'
import { SKIN_TYPES, SKIN_CONCERNS } from '@/lib/products'
import { cn } from '@/lib/utils'

function fileToResizedDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => {
        try {
          const maxDim = 1600
          let { width, height } = img
          if (width > maxDim || height > maxDim) {
            const scale = Math.min(maxDim / width, maxDim / height)
            width = Math.round(width * scale)
            height = Math.round(height * scale)
          }
          const canvas = document.createElement('canvas')
          canvas.width = width
          canvas.height = height
          const ctx = canvas.getContext('2d')
          if (!ctx) {
            resolve(reader.result as string)
            return
          }
          ctx.drawImage(img, 0, 0, width, height)
          resolve(canvas.toDataURL('image/jpeg', 0.85))
        } catch {
          resolve(reader.result as string)
        }
      }
      img.onerror = () => resolve(reader.result as string)
      img.src = reader.result as string
    }
    reader.onerror = () => reject(new Error('Не удалось прочитать файл'))
    reader.readAsDataURL(file)
  })
}

type Product = { id: number; slug: string; name: string; brand: string; image_url: string }

const STEPS = ['Кожа', 'Проблемы', 'Продукт', 'Анализ']

export function TrialCheck({ onAuth }: { onAuth: () => void }) {
  const [skinType, setSkinType] = useState('')
  const [concerns, setConcerns] = useState<string[]>([])
  const [mode, setMode] = useState<'name' | 'link' | 'photo'>('name')
  const [name, setName] = useState('')
  const [link, setLink] = useState('')
  const [loading, setLoading] = useState(false)
  const [product, setProduct] = useState<Product | null>(null)
  const [score, setScore] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [photoName, setPhotoName] = useState('')

  // Autocomplete
  const [suggestions, setSuggestions] = useState<Product[]>([])
  const [searching, setSearching] = useState(false)
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const progress = score != null ? 3 : product ? 2 : concerns.length > 0 ? 1 : skinType ? 0 : -1

  const profileBody = () => ({
    name: '',
    age: '',
    concerns,
    allergies: [],
    custom_text: '',
    quiz_answers: {},
    skin_type_determined: skinType || '',
  })

  // Debounced autocomplete (name mode): реальные товары из каталога.
  useEffect(() => {
    if (mode !== 'name') return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = name.trim()
    if (q.length < 2) {
      setSuggestions([])
      setOpen(false)
      setSearching(false)
      return
    }
    setSearching(true)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/catalog?search=${encodeURIComponent(q)}&limit=6`)
        const data = await res.json()
        const items: Product[] = (data.products || []).map((p: any) => {
          const parts = (p.name || '').split('\n').filter((x: string) => x.trim())
          return {
            id: p.id,
            slug: p.slug || '',
            name: parts.length > 1 ? parts.slice(1).join(' ') : (p.name || '').replace(/\n/g, ' ').trim(),
            brand: parts.length > 1 ? parts[0] : (p.brand || ''),
            image_url: p.image_url || '',
          }
        })
        setSuggestions(items)
        setOpen(items.length > 0)
      } catch {
        setSuggestions([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [name, mode])

  const doCheck = async (p: Product) => {
    const res = await fetch('/api/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_name: p.name,
        skin_type: skinType || 'Нормальная',
        profile: profileBody(),
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || 'Не удалось проверить')
    setProduct(p)
    setScore(typeof data.score === 'number' ? data.score : 0)
  }

  const selectSuggestion = async (s: Product) => {
    setName(s.name)
    setOpen(false)
    setLoading(true)
    setError('')
    setScore(null)
    try {
      await doCheck(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось проверить')
    } finally {
      setLoading(false)
    }
  }

  const checkName = async () => {
    if (!name.trim() || loading) return
    setLoading(true)
    setError('')
    setScore(null)
    try {
      await doCheck({ id: 0, slug: '', name: name.trim(), brand: '', image_url: '' })
      setName('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось проверить')
    } finally {
      setLoading(false)
    }
  }

  const checkLink = async () => {
    if (!link.trim() || loading) return
    setLoading(true)
    setError('')
    setScore(null)
    try {
      const imp = await fetch('/api/products/import-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: link.trim() }),
      })
      const impData = await imp.json().catch(() => ({}))
      if (!imp.ok) throw new Error(impData.detail || 'Не удалось получить товар')
      const productName = impData.product?.name
      if (!productName) throw new Error('Товар на странице не найден')
      await doCheck({
        id: impData.product?.id ?? 0,
        slug: impData.product?.slug ?? '',
        name: productName,
        brand: impData.product?.brand ?? '',
        image_url: impData.product?.image_url ?? '',
      })
      setLink('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось получить товар')
    } finally {
      setLoading(false)
    }
  }

  const checkPhoto = async (files: FileList | null) => {
    if (!files || !files.length || loading) return
    setLoading(true)
    setError('')
    setScore(null)
    try {
      const dataUrls: string[] = []
      for (const file of Array.from(files)) {
        dataUrls.push(await fileToResizedDataUrl(file))
      }
      const res = await fetch('/api/composition/recognize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ images: dataUrls }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Не удалось распознать состав')
      const match = (data.matches || [])[0]
      if (!match?.name) throw new Error('Продукт по фото не найден')
      setPhotoName(match.name)
      await doCheck({
        id: match.id ?? 0,
        slug: match.slug ?? '',
        name: match.name,
        brand: match.brand ?? '',
        image_url: match.image_url ?? '',
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось распознать состав')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full rounded-2xl border border-white/60 bg-white/90 p-4 text-left shadow-2xl backdrop-blur-xl">
      <div className="mb-4 flex items-center">
        {STEPS.map((label, i) => (
          <div key={label} className={cn('flex items-center', i < STEPS.length - 1 && 'flex-1')}>
            <span className={cn('neon-dot', i === progress + 1 ? 'neon-dot--lime' : i <= progress ? '' : 'neon-dot--muted')} />
            {i < STEPS.length - 1 && <span className="neon-hairline mx-1.5 h-px flex-1" />}
          </div>
        ))}
      </div>
      <div className="mb-3 flex justify-between text-[8px] uppercase tracking-wide text-muted-foreground/50">
        {STEPS.map((label) => <span key={label}>{label}</span>)}
      </div>

      <p className="text-[11px] font-medium text-muted-foreground/70">Тип кожи</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {SKIN_TYPES.map((s) => (
          <button
            key={s}
            onClick={() => setSkinType(s)}
            className={cn('rounded-full border px-2.5 py-1 text-[11px] transition-colors', skinType === s ? 'neon-ring border-primary bg-primary text-primary-foreground' : 'border-gray-200 text-foreground/70 hover:border-primary/40')}
          >
            {s}
          </button>
        ))}
      </div>

      <p className="mt-3 text-[11px] font-medium text-muted-foreground/70">Что беспокоит</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {SKIN_CONCERNS.map((c) => (
          <button
            key={c}
            onClick={() => setConcerns((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))}
            className={cn('rounded-full border px-2.5 py-1 text-[11px] transition-colors', concerns.includes(c) ? 'neon-ring border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/70 hover:border-primary/40')}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="mt-3 flex rounded-xl bg-gray-100/70 p-1">
        {[
          { id: 'name', label: 'Название', icon: Search },
          { id: 'link', label: 'Ссылка', icon: Link2 },
          { id: 'photo', label: 'Фото', icon: Camera },
        ].map((m) => (
          <button
            key={m.id}
            onClick={() => { setMode(m.id as typeof mode); setError('') }}
            className={cn('flex flex-1 items-center justify-center gap-1.5 rounded-lg py-1.5 text-[11px] font-medium transition-colors', mode === m.id ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground/60')}
          >
            <m.icon className="size-3.5" />
            {m.label}
          </button>
        ))}
      </div>

      <div className="mt-2 flex gap-2">
        {mode === 'name' && (
          <div className="relative min-w-0 flex-1">
            <input
              value={name}
              onChange={(e) => { setName(e.target.value); setOpen(true) }}
              onKeyDown={(e) => e.key === 'Enter' && checkName()}
              onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
              placeholder="Название продукта…"
              className="w-full rounded-xl border border-gray-200 bg-white/70 px-3 py-2 pr-9 text-sm focus:border-primary/40 focus:outline-none"
            />
            {searching && <LoaderCircle className="absolute right-2.5 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground/50" />}
            {open && (
              <div className="absolute left-0 right-0 top-full z-30 mt-1 overflow-hidden rounded-xl border border-gray-100 bg-white shadow-xl">
                {suggestions.map((s) => (
                  <button
                    key={s.slug || s.id}
                    onClick={() => selectSuggestion(s)}
                    className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-primary/5"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-50">
                      {s.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={s.image_url} alt="" className="h-full w-full object-contain p-1" />
                      ) : (
                        <Search className="size-4 text-muted-foreground/30" />
                      )}
                    </span>
                    <span className="min-w-0 flex-1">
                      {s.brand && <span className="block truncate text-[10px] uppercase tracking-wide text-muted-foreground/50">{s.brand}</span>}
                      <span className="block truncate text-sm text-foreground/90">{s.name}</span>
                    </span>
                  </button>
                ))}
                {!searching && suggestions.length === 0 && (
                  <p className="px-3 py-3 text-center text-xs text-muted-foreground/50">Ничего не найдено</p>
                )}
              </div>
            )}
          </div>
        )}
        {mode === 'link' && (
          <input
            value={link}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && checkLink()}
            placeholder="Ссылка на товар…"
            className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-white/70 px-3 py-2 text-sm focus:border-primary/40 focus:outline-none"
          />
        )}
        {mode === 'photo' && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => { checkPhoto(e.target.files); e.target.value = '' }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              className="flex-1 truncate rounded-xl border border-dashed border-gray-300 bg-white/70 px-3 py-2 text-sm text-muted-foreground/60 transition-colors hover:bg-white"
            >
              {photoName || 'Загрузите фото состава…'}
            </button>
          </>
        )}
        <button
          onClick={() => (mode === 'link' ? checkLink() : mode === 'photo' ? fileRef.current?.click() : checkName())}
          disabled={loading}
          className="shrink-0 rounded-xl bg-primary px-4 py-2 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? <LoaderCircle className="size-4 animate-spin" /> : 'Проверить'}
        </button>
      </div>

      {error && <p className="mt-2 text-[11px] text-red-500">{error}</p>}

      {score != null && (
        <div className="mt-3 rounded-xl border border-primary/15 bg-primary/5 p-3 text-center">
          {product && (
            <div className="mb-2 flex items-center gap-2">
              {product.image_url && (
                <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={product.image_url} alt="" className="h-full w-full object-contain p-1" />
                </span>
              )}
              <span className="min-w-0 flex-1 truncate text-left text-xs text-foreground/70">{product.name}</span>
            </div>
          )}
          <div className="flex items-baseline justify-center gap-1">
            <span className="text-4xl font-light tabular-nums text-foreground">{score}%</span>
          </div>
          <div className="neon-score-underline mx-auto mt-1 w-10" />
          <p className="mt-2 text-xs leading-relaxed text-foreground/70">
            Это только начало… пройдите полную анкету — и Aidermy сможет учитывать больше особенностей вашей кожи.
          </p>
          <button
            onClick={onAuth}
            className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary py-2.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Зарегистрироваться
            <ArrowRight className="size-3.5" />
          </button>
          <p className="mt-1.5 text-[10px] text-muted-foreground/60">
            20 кредитов бесплатно · 1 кредит = 1 проверка
          </p>
        </div>
      )}
    </div>
  )
}

