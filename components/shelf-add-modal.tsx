'use client'

import { useEffect, useRef, useState } from 'react'
import { X, Search, Link2, Wand2, LoaderCircle, Sparkles, ChevronLeft, ThumbsDown, Camera, ImagePlus, Trash2 } from 'lucide-react'
import { CABINET_TITLES, CABINET_META } from '@/lib/shelf'
import { useScrollLock } from '@/lib/use-scroll-lock'
import { cn, capitalizeFirst } from '@/lib/utils'

type Mode = 'menu' | 'base' | 'url' | 'recommend' | 'photo'

type PhotoMatch = {
  slug: string
  name: string
  brand: string
  image_url: string
  category: string
  match_percent: number
  matched_count: number
  total_recognized: number
}

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

type SearchProduct = {
  slug: string
  name: string
  brand: string
  image_url: string
  category: string
}

type Recommendation = {
  slug: string
  name: string
  brand: string
  image_url: string
  score: number | null
  shelf_compatibility: number | null
  reason: string
}

function splitName(name: string): { brand: string; title: string } {
  const parts = (name || '').split('\n').filter((x) => x.trim())
  if (parts.length >= 2) return { brand: capitalizeFirst(parts[0]), title: capitalizeFirst(parts.slice(1).join(' ')) }
  return { brand: '', title: capitalizeFirst((name || '').trim()) }
}

const DISLIKE_REASONS = [
  { key: 'wrong_category', label: 'Не та категория' },
  { key: 'low_score', label: 'Слишком низкий процент соответствия' },
  { key: 'composition', label: 'Не подходит по составу' },
  { key: 'tried', label: 'Уже пробовал / не понравился' },
  { key: 'other', label: 'Другое' },
]

export function ShelfAddModal({
  cabinet,
  category,
  onClose,
  onAdded,
  onOpenProduct,
}: {
  cabinet: string
  category: string
  onClose: () => void
  onAdded: () => void
  onOpenProduct?: (slug: string) => void
}) {
  const [mode, setMode] = useState<Mode>('menu')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchProduct[]>([])
  const [searching, setSearching] = useState(false)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [recs, setRecs] = useState<Recommendation[]>([])
  const [recLoading, setRecLoading] = useState(false)
  const [dislikeTarget, setDislikeTarget] = useState<Recommendation | null>(null)
  const [dislikeReason, setDislikeReason] = useState('')
  const [dislikeNote, setDislikeNote] = useState('')
  const [submittingDislike, setSubmittingDislike] = useState(false)
  const [reviews, setReviews] = useState<Record<string, string>>({})
  const [reviewLoading, setReviewLoading] = useState<Set<string>>(new Set())

  const [photos, setPhotos] = useState<string[]>([])
  const [photoMatches, setPhotoMatches] = useState<PhotoMatch[]>([])
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photoStatus, setPhotoStatus] = useState('')
  const photoInputRef = useRef<HTMLInputElement | null>(null)

  useScrollLock(true)

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const isScoring = CABINET_META.find((c) => c.key === cabinet)?.hasScoring ?? false

  const search = async (q: string) => {
    setQuery(q)
    if (q.trim().length < 2) {
      setResults([])
      return
    }
    setSearching(true)
    try {
      const res = await fetch(`/api/catalog?search=${encodeURIComponent(q.trim())}&limit=10`)
      const data = await res.json()
      setResults(
        (data.products || []).map((p: any) => {
          const { brand, title } = splitName(p.name || '')
          return {
            slug: p.slug,
            name: title,
            brand: brand || p.brand || '',
            image_url: p.image_url || '',
            category: p.category || '',
          }
        }),
      )
    } catch (e) {
      console.error(e)
    } finally {
      setSearching(false)
    }
  }

  const addBySlug = async (slug: string, openCard = false) => {
    setBusy(true)
    setStatus('')
    try {
      const res = await fetch('/api/shelf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug, cabinet, category }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        if (res.status === 422) {
          throw new Error(`Этот продукт не подходит для выбранной категории. ${data.detail || ''}`)
        }
        throw new Error(data.detail || 'Не удалось добавить')
      }
      if (data.duplicate) setStatus('Этот продукт уже на полке')
      onAdded()
      if (openCard && onOpenProduct) {
        onOpenProduct(slug)
      } else {
        onClose()
      }
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось добавить')
    } finally {
      setBusy(false)
    }
  }

  const submitDislike = async () => {
    if (!dislikeTarget || !dislikeReason || submittingDislike) return
    setSubmittingDislike(true)
    setStatus('')
    try {
      const res = await fetch('/api/recommendations/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug: dislikeTarget.slug, cabinet, category, reason: dislikeReason, note: dislikeNote }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Не удалось сохранить')
      const replacement = data.replacement || []
      setRecs((prev) => {
        const without = prev.filter((r) => r.slug !== dislikeTarget.slug)
        const merged = [...without]
        for (const r of replacement) {
          if (!merged.some((m) => m.slug === r.slug)) merged.push(r)
        }
        return merged
      })
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось сохранить')
    } finally {
      setSubmittingDislike(false)
      setDislikeTarget(null)
      setDislikeReason('')
      setDislikeNote('')
    }
  }

  const addByUrl = async () => {
    if (!url.trim() || busy) return
    setBusy(true)
    setStatus('Загружаем страницу…')
    try {
      const imp = await fetch('/api/products/import-url', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ url: url.trim() }),
      })
      const impData = await imp.json().catch(() => ({}))
      if (!imp.ok) throw new Error(impData.detail || 'Не удалось получить товар')
      const slug = impData.product?.slug
      if (!slug) throw new Error('Товар на странице не найден')
      setStatus('Добавляем на полку…')
      await addBySlug(slug, true)
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось получить товар')
      setBusy(false)
    }
  }

  const enterPhotoMode = () => {
    setPhotos([])
    setPhotoMatches([])
    setPhotoStatus('')
    setPhotoBusy(false)
    setStatus('')
    setMode('photo')
  }

  const handlePhotoFiles = async (files: FileList | null) => {
    if (!files || !files.length) return
    setPhotoStatus('')
    try {
      const dataUrls: string[] = []
      for (const file of Array.from(files)) {
        dataUrls.push(await fileToResizedDataUrl(file))
      }
      setPhotos((prev) => [...prev, ...dataUrls])
      setPhotoMatches([])
    } catch (e) {
      setPhotoStatus(e instanceof Error ? e.message : 'Не удалось добавить фото')
    }
  }

  const removePhoto = (index: number) => {
    setPhotos((prev) => prev.filter((_, i) => i !== index))
  }

  const recognizePhoto = async () => {
    if (!photos.length || photoBusy) return
    setPhotoBusy(true)
    setPhotoStatus('')
    setPhotoMatches([])
    try {
      const res = await fetch('/api/composition/recognize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ images: photos }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Не удалось распознать состав')
      setPhotoMatches(data.matches || [])
      if (!(data.recognition && data.recognition.is_inci)) {
        setPhotoStatus('На фото не удалось найти список ингредиентов (INCI). Попробуйте другой ракурс.')
      } else if (!(data.matches || []).length) {
        setPhotoStatus('Подходящий продукт не найден в базе. Попробуйте добавить по названию или ссылке.')
      }
    } catch (e) {
      setPhotoStatus(e instanceof Error ? e.message : 'Не удалось распознать состав')
    } finally {
      setPhotoBusy(false)
    }
  }

  const requestReview = async (slug: string) => {
    setReviewLoading((prev) => new Set(prev).add(slug))
    try {
      const res = await fetch('/api/shelf/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug }),
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.review) {
        setReviews((prev) => ({ ...prev, [slug]: data.review }))
      }
    } catch (e) {
      console.error(e)
    } finally {
      setReviewLoading((prev) => {
        const next = new Set(prev)
        next.delete(slug)
        return next
      })
    }
  }

  const loadRecommendations = async () => {
    setRecLoading(true)
    setStatus('')
    try {
      const res = await fetch('/api/shelf/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ cabinet, category }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Не удалось подобрать')
      const recommendations: Recommendation[] = (data.recommendations || []) as Recommendation[]
      setRecs(recommendations)
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось подобрать')
    } finally {
      setRecLoading(false)
    }
  }

  useEffect(() => {
    if (mode === 'recommend') loadRecommendations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])
  const title = `${CABINET_TITLES[cabinet] || cabinet} → ${category}`

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={onClose}>
      <div className="flex max-h-[80dvh] w-full max-w-md max-w-[100vw] flex-col overflow-hidden rounded-2xl bg-white p-4 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex shrink-0 items-center justify-between">
          <div className="flex items-center gap-2">
            {mode !== 'menu' && (
              <button onClick={() => { setMode('menu'); setStatus('') }} className="text-muted-foreground hover:text-foreground">
                <ChevronLeft className="size-4" />
              </button>
            )}
            <h2 className="text-base font-normal text-foreground">
              {mode === 'menu' ? 'Добавить продукт' : mode === 'base' ? 'Выбрать из базы' : mode === 'url' ? 'Добавить по ссылке' : mode === 'photo' ? 'Добавить по фото' : 'Подобрать автоматически'}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="relative z-10 shrink-0 text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
        </div>

        {mode !== 'menu' && <p className="mb-3 shrink-0 text-[11px] text-muted-foreground/60">В полку: {title}</p>}

        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        {mode === 'menu' && (
          <div className="space-y-2">
            <button onClick={() => setMode('base')} className="flex w-full items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 text-left transition-colors hover:bg-gray-50">
              <Search className="size-4 text-primary" />
              <div><p className="text-sm text-foreground">Выбрать из базы</p><p className="text-[10px] text-muted-foreground/60">Найти уже существующий продукт</p></div>
            </button>
            <button onClick={() => setMode('url')} className="flex w-full items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 text-left transition-colors hover:bg-gray-50">
              <Link2 className="size-4 text-primary" />
              <div><p className="text-sm text-foreground">Добавить по ссылке</p><p className="text-[10px] text-muted-foreground/60">Импортировать товар по URL</p></div>
            </button>
            <button onClick={() => setMode('recommend')} className="flex w-full items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 text-left transition-colors hover:bg-gray-50">
              <Wand2 className="size-4 text-primary" />
              <div><p className="text-sm text-foreground">Подобрать автоматически</p><p className="text-[10px] text-muted-foreground/60">Aidermy предложит 3 варианта</p></div>
            </button>
            <button onClick={enterPhotoMode} className="flex w-full items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 text-left transition-colors hover:bg-gray-50">
              <Camera className="size-4 text-primary" />
              <div><p className="text-sm text-foreground">Добавить по фото</p><p className="text-[10px] text-muted-foreground/60">Распознать состав с фотографии</p></div>
            </button>
          </div>
        )}
        {mode === 'base' && (
          <div>
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground/40" />
              <input value={query} onChange={(e) => search(e.target.value)} placeholder="Название, бренд или категория…" className="w-full rounded-xl border border-gray-200/60 bg-gray-50/50 py-2 pl-8 pr-3 text-sm focus:border-primary/40 focus:outline-none" />
            </div>
            <div className="max-h-72 overflow-y-auto rounded-xl border border-gray-100">
              {searching ? (
                <div className="p-3 text-center text-xs text-muted-foreground/50">Поиск…</div>
              ) : results.length === 0 ? (
                <div className="p-3 text-center text-xs text-muted-foreground/50">{query.trim().length >= 2 ? 'Ничего не найдено' : 'Введите запрос'}</div>
              ) : (
                results.map((p) => (
                  <button key={p.slug} onClick={() => addBySlug(p.slug)} disabled={busy} className="flex w-full items-center gap-2 border-b border-gray-50 p-2 text-left transition-colors hover:bg-gray-50 disabled:opacity-50">
                    {p.image_url ? <img src={p.image_url} alt="" className="size-9 rounded-lg bg-white object-contain" /> : <Sparkles className="size-9 rounded-lg bg-gray-50 p-2 text-muted-foreground/30" />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs text-foreground/80">{p.brand}</span>
                      <span className="block truncate text-[11px] text-muted-foreground/60">{p.name}</span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        )}

        {mode === 'url' && (
          <div>
            <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addByUrl()} placeholder="Вставьте ссылку на товар…" className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none" />
            <button onClick={addByUrl} disabled={!url.trim() || busy} className="mt-2 w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40">
              {busy ? <LoaderCircle className="mx-auto size-4 animate-spin" /> : 'Импортировать'}
            </button>
          </div>
        )}

        {mode === 'photo' && (
          <div className="space-y-3">
            <input
              ref={photoInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => { handlePhotoFiles(e.target.files); e.target.value = '' }}
            />
            <button
              onClick={() => photoInputRef.current?.click()}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-primary/30 bg-primary/5 py-4 text-sm text-primary transition-colors hover:bg-primary/10"
            >
              <ImagePlus className="size-4" />
              Добавить фото состава
            </button>

            {photos.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {photos.map((p, i) => (
                  <div key={i} className="relative size-16 overflow-hidden rounded-lg border border-gray-200">
                    <img src={p} alt="" className="h-full w-full object-cover" />
                    <button onClick={() => removePhoto(i)} className="absolute right-0.5 top-0.5 rounded-full bg-black/50 p-0.5 text-white"><Trash2 className="size-3" /></button>
                  </div>
                ))}
              </div>
            )}

            <button
              onClick={recognizePhoto}
              disabled={!photos.length || photoBusy}
              className="w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
            >
              {photoBusy ? <LoaderCircle className="mx-auto size-4 animate-spin" /> : 'Распознать и найти продукт'}
            </button>

            {photoStatus && <p className="text-[11px] text-muted-foreground/60">{photoStatus}</p>}

            {photoMatches.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground/70">Найденные продукты</p>
                {photoMatches.map((m) => (
                  <div key={m.slug} className="flex items-center gap-2.5 rounded-xl border border-gray-200 p-2.5">
                    <div className="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-50">
                      {m.image_url ? <img src={m.image_url} alt="" className="h-full w-full object-contain p-1" /> : <Sparkles className="size-4 text-muted-foreground/30" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      {m.brand && <p className="text-[9px] uppercase tracking-wide text-muted-foreground/50">{m.brand}</p>}
                      <p className="truncate text-xs text-foreground/90">{m.name}</p>
                      {typeof m.match_percent === 'number' && <p className="text-[10px] text-muted-foreground/50">Совпадение: {m.match_percent}%</p>}
                    </div>
                    <button onClick={() => addBySlug(m.slug)} disabled={busy} className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40">
                      Выбрать
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {mode === 'recommend' && (
          <div>
            {recLoading ? (
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground/50">
                <LoaderCircle className="mb-2 size-6 animate-spin text-primary" />
                <span className="text-xs">Подбираем варианты…</span>
              </div>
            ) : recs.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground/50">В базе пока нет подходящих продуктов для этой категории</div>
            ) : (
              <div className="space-y-2">
                {recs.map((r) => (
                  <div key={r.slug} className="rounded-xl border border-gray-200 p-2.5">
                    <div className="flex gap-2.5">
                      <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-gray-50">
                        {r.image_url ? <img src={r.image_url} alt="" className="h-full w-full object-contain p-1" /> : <Sparkles className="size-5 text-muted-foreground/30" />}
                      </div>
                      <div className="min-w-0 flex-1">
                        {r.brand && <p className="text-[9px] uppercase tracking-wide text-muted-foreground/50">{r.brand}</p>}
                        <p className="truncate text-xs font-medium text-foreground/90">{r.name}</p>
                        {r.score != null ? (
                          <div className="mt-0.5">
                            <p className="text-sm font-light text-primary">{r.score}% <span className="text-[9px] font-normal text-muted-foreground/50">совместимость</span></p>
                            {r.shelf_compatibility != null && (
                              <p className="text-[10px] text-muted-foreground/60">Совместимость с полкой: {r.shelf_compatibility}%</p>
                            )}
                          </div>
                        ) : isScoring ? (
                          <p className="text-[10px] text-muted-foreground/50">—</p>
                        ) : null}
                      </div>
                    </div>
                    {reviews[r.slug] ? (
                      <p className="mt-2 break-words text-[10px] leading-relaxed text-muted-foreground/70">{reviews[r.slug]}</p>
                    ) : (
                      <button
                        onClick={() => requestReview(r.slug)}
                        disabled={reviewLoading.has(r.slug)}
                        className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-primary/70 transition-colors hover:text-primary disabled:opacity-40"
                      >
                        {reviewLoading.has(r.slug) ? 'Формируем…' : 'Показать отчёт'}
                      </button>
                    )}
                    <div className="mt-2 flex gap-1.5">
                      {onOpenProduct && (
                        <button
                          onClick={() => onOpenProduct(r.slug)}
                          className="flex-1 rounded-lg border border-gray-200 py-1.5 text-xs text-foreground/70 transition-colors hover:bg-gray-50"
                        >
                          Подробнее
                        </button>
                      )}
                      <button onClick={() => addBySlug(r.slug)} disabled={busy} className="flex-1 rounded-lg bg-primary py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40">
                        Выбрать
                      </button>
                      <button
                        onClick={() => { setDislikeTarget(r); setDislikeReason(''); setDislikeNote('') }}
                        aria-label="Не подходит"
                        className="shrink-0 rounded-lg border border-gray-200 px-2 py-1.5 text-muted-foreground/60 transition-colors hover:border-red-200 hover:text-red-500"
                      >
                        <ThumbsDown className="size-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        </div>

        {status && <p className="mt-2 shrink-0 text-[11px] text-muted-foreground/60">{status}</p>}
      </div>

      {dislikeTarget && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 p-4" onClick={() => setDislikeTarget(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white p-4 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-normal text-foreground">Почему этот продукт вам не подошёл?</h3>
              <button onClick={() => setDislikeTarget(null)} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
            </div>
            <div className="space-y-1.5">
              {DISLIKE_REASONS.map((r) => (
                <button
                  key={r.key}
                  onClick={() => setDislikeReason(r.key)}
                  className={cn(
                    'w-full rounded-xl border px-3 py-2.5 text-left text-sm transition-colors',
                    dislikeReason === r.key ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-foreground/80 hover:border-primary/30',
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>
            {dislikeReason === 'other' && (
              <textarea
                value={dislikeNote}
                onChange={(e) => setDislikeNote(e.target.value)}
                placeholder="Уточните причину…"
                className="mt-2 w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:border-primary/40 focus:outline-none resize-none"
                rows={2}
              />
            )}
            <button
              onClick={submitDislike}
              disabled={!dislikeReason || submittingDislike}
              className="mt-3 w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
            >
              {submittingDislike ? 'Сохраняем…' : 'Отправить'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


