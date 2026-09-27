'use client'

import { useEffect, useRef, useState } from 'react'
import { X, Link2, Search, Camera, LoaderCircle, Trash2, Check, ChevronLeft, Sparkles, AlertCircle, Keyboard } from 'lucide-react'
import { cn, capitalizeFirst } from '@/lib/utils'
import { useScrollLock } from '@/lib/use-scroll-lock'
import type { CheckResult, SkinProfile } from '@/lib/store'

type Suggestion = { name: string; brand: string; title: string; image_url: string }

type RecognitionIngredient = { raw: string; normalized: string; confidence: number | null }
type Recognition = {
  is_inci: boolean
  raw_text: string
  ingredients: RecognitionIngredient[]
  uncertain_items: { text: string; reason: string }[]
  overall_confidence: number | null
}
type ProductMatch = {
  slug: string
  name: string
  brand: string
  image_url: string
  category: string
  match_percent: number
  matched_count: number
  total_recognized: number
}
type Identified = { brand: string; name: string; variant: string | null; type: string | null; confidence: number }
type FoundProduct = { slug: string; name: string; brand: string; ingredients: string }

function splitName(raw: string): { brand: string; title: string } {
  const parts = (raw || '').split('\n').filter((x) => x.trim())
  if (parts.length >= 2) return { brand: capitalizeFirst(parts[0]), title: capitalizeFirst(parts.slice(1).join(' ')) }
  return { brand: '', title: capitalizeFirst((raw || '').trim()) }
}

// Уменьшает фото до разумного размера (для лимитов тела запроса и экономии токенов).
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

function buildProfileBody(profile: SkinProfile) {
  return {
    name: profile.name || '',
    age: profile.age || '',
    concerns: profile.concerns || [],
    allergies: profile.allergies || [],
    custom_text: profile.customText || '',
    quiz_answers: profile.quizAnswers || {},
    skin_type_determined: profile.skinTypeDetermined || '',
  }
}

export function CheckModal({ isOpen, onClose, onCheck, profile, onRecognized, onOpenCatalog }: {
  isOpen: boolean
  onClose: () => void
  onCheck: (product: string, skinType: string) => void
  profile: SkinProfile
  onRecognized: (result: CheckResult) => void
  onOpenCatalog?: (query: string) => void
}) {
  const [mode, setMode] = useState<'name' | 'link' | 'photo' | 'product'>('name')
  const [name, setName] = useState('')
  const [link, setLink] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ===== Фото-распознавание состава =====
  const [photos, setPhotos] = useState<string[]>([])
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photoStatus, setPhotoStatus] = useState('')
  const [recognition, setRecognition] = useState<Recognition | null>(null)
  const [matches, setMatches] = useState<ProductMatch[]>([])
  const [confidentThreshold, setConfidentThreshold] = useState(70)
  const [showManualForm, setShowManualForm] = useState(false)
  const [brandInput, setBrandInput] = useState('')
  const [nameInput, setNameInput] = useState('')
  const [nameError, setNameError] = useState('')
  const [brandOptions, setBrandOptions] = useState<string[]>([])
  const [creatingProduct, setCreatingProduct] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)
  const brandDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ===== Определение продукта (фото → Vision → БД → Web Search) =====
  const [productStage, setProductStage] = useState<'idle' | 'identifying' | 'searching' | 'found' | 'fallback' | 'error'>('idle')
  const [productStatus, setProductStatus] = useState('')
  const [identified, setIdentified] = useState<Identified | null>(null)
  const [foundProduct, setFoundProduct] = useState<FoundProduct | null>(null)
  const productFileRef = useRef<HTMLInputElement | null>(null)

  useScrollLock(isOpen)

  useEffect(() => {
    if (!isOpen) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (name.trim().length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/products?q=${encodeURIComponent(name.trim())}`)
        const data = await res.json()
        const items = (data.products || []).slice(0, 6).map((p: any) => {
          const { brand, title } = splitName(p.name || '')
          return { name: p.name || '', brand, title, image_url: p.image_url || '' }
        })
        setSuggestions(items)
        setShowSuggestions(items.length > 0)
      } catch {
        setSuggestions([])
      }
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [name, isOpen])

  // Автокомплит брендов (существующая Brand DB — извлекается из Product DB).
  useEffect(() => {
    if (mode !== 'photo' || !showManualForm) return
    if (brandDebounceRef.current) clearTimeout(brandDebounceRef.current)
    const q = brandInput.trim()
    if (q.length < 1) {
      setBrandOptions([])
      return
    }
    brandDebounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/brands?q=${encodeURIComponent(q)}`)
        const data = await res.json()
        setBrandOptions(Array.isArray(data.brands) ? data.brands.slice(0, 8) : [])
      } catch {
        setBrandOptions([])
      }
    }, 250)
    return () => {
      if (brandDebounceRef.current) clearTimeout(brandDebounceRef.current)
    }
  }, [brandInput, mode, showManualForm])

  // Сбрасываем флоу при закрытии модалки.
  useEffect(() => {
    if (!isOpen) {
      resetPhotoFlow()
      resetProductFlow()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  if (!isOpen) return null

  const handleName = () => {
    if (!name.trim() || loading) return
    onCheck(name.trim(), 'Нормальная')
    setName('')
    onClose()
  }

  const selectSuggestion = (s: Suggestion) => {
    setShowSuggestions(false)
    onCheck(s.title || s.brand, 'Нормальная')
    setName('')
    onClose()
  }

  const handleLink = async () => {
    if (!link.trim() || loading) return
    setLoading(true)
    setStatus('Загружаем страницу…')
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
      const res = await fetch('/api/products/import-url', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ url: link.trim() }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Не удалось получить товар')
      const productName = data.product?.name
      if (!productName) throw new Error('Товар на странице не найден')
      onCheck(productName, 'Нормальная')
      setLink('')
      setStatus('')
      onClose()
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Не удалось получить товар')
    } finally {
      setLoading(false)
    }
  }

  function resetPhotoFlow() {
    setPhotos([])
    setRecognition(null)
    setMatches([])
    setConfidentThreshold(70)
    setShowManualForm(false)
    setBrandInput('')
    setNameInput('')
    setNameError('')
    setBrandOptions([])
    setPhotoStatus('')
    setPhotoBusy(false)
    setAnalyzing(false)
    setCreatingProduct(false)
  }

  const enterPhotoMode = () => {
    resetPhotoFlow()
    setMode('photo')
  }

  function resetProductFlow() {
    setProductStage('idle')
    setProductStatus('')
    setIdentified(null)
    setFoundProduct(null)
  }

  const enterProductMode = () => {
    resetProductFlow()
    setMode('product')
  }

  const handleAddPhotos = async (files: FileList | null) => {
    if (!files || !files.length) return
    setPhotoStatus('')
    try {
      const dataUrls: string[] = []
      for (const file of Array.from(files)) {
        dataUrls.push(await fileToResizedDataUrl(file))
      }
      setPhotos((prev) => [...prev, ...dataUrls])
    } catch (e) {
      setPhotoStatus(e instanceof Error ? e.message : 'Не удалось добавить фото')
    }
  }

  const handleRemovePhoto = (index: number) => {
    setPhotos((prev) => prev.filter((_, i) => i !== index))
  }

  const handleRecognize = async () => {
    if (!photos.length || photoBusy) return
    setPhotoBusy(true)
    setPhotoStatus('')
    setRecognition(null)
    setMatches([])
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
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
      setRecognition(data.recognition || null)
      setMatches(data.matches || [])
      setConfidentThreshold(typeof data.confident_threshold === 'number' ? data.confident_threshold : 70)
      if (!(data.recognition && data.recognition.is_inci)) {
        setPhotoStatus('На фото не удалось найти список ингредиентов (INCI). Попробуйте другой ракурс.')
      }
    } catch (e) {
      setPhotoStatus(e instanceof Error ? e.message : 'Не удалось распознать состав')
    } finally {
      setPhotoBusy(false)
    }
  }

  const handleAnalyze = async (payload: { product_name: string; brand: string; slug: string }) => {
    if (analyzing) return
    setAnalyzing(true)
    setPhotoStatus('')
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
      const ingredients = (recognition?.ingredients || [])
        .map((i) => i.normalized || i.raw)
        .filter((x) => x && x.trim())
      const res = await fetch('/api/composition/analyze', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          product_name: payload.product_name,
          brand: payload.brand || '',
          slug: payload.slug || '',
          ingredients,
          skin_type: profile.skinType || 'Нормальная',
          profile: buildProfileBody(profile),
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Не удалось выполнить анализ')
      const result: CheckResult = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        product: payload.product_name,
        skinType: profile.skinType || 'Нормальная',
        score: data.score || 0,
        verdict: data.verdict || 'Нет данных',
        summary: data.summary || 'Не удалось получить рекомендацию.',
        safe_ingredients: data.safe_ingredients || [],
        caution_ingredients: data.caution_ingredients || [],
        slug: data.slug || '',
        image_url: data.image_url || '',
        createdAt: Date.now(),
        active_ingredients: data.active_ingredients,
        how_to_use: data.how_to_use,
        expectations: data.expectations,
      }
      onRecognized(result)
      onClose()
    } catch (e) {
      setPhotoStatus(e instanceof Error ? e.message : 'Не удалось выполнить анализ')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleConfirmMatch = (m: ProductMatch) => {
    handleAnalyze({ product_name: m.name, brand: m.brand, slug: m.slug })
  }

  const handleCreateProduct = async () => {
    const brand = brandInput.trim()
    const productName = nameInput.trim()
    if (!productName) {
      setNameError('Укажите название продукта')
      return
    }
    setNameError('')
    if (creatingProduct) return
    setCreatingProduct(true)
    setPhotoStatus('')
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
      const ingredients = (recognition?.ingredients || [])
        .map((i) => i.normalized || i.raw)
        .filter((x) => x && x.trim())
      const res = await fetch('/api/products/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ brand, name: productName, ingredients }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Не удалось сохранить продукт')
      const slug = (data.product && data.product.slug) || ''
      await handleAnalyze({ product_name: productName, brand, slug })
    } catch (e) {
      setPhotoStatus(e instanceof Error ? e.message : 'Не удалось сохранить продукт')
    } finally {
      setCreatingProduct(false)
    }
  }

  // ===== Определение продукта =====
  const runProductIdentify = async (images: string[]) => {
    setProductStage('identifying')
    setProductStatus('Определяем продукт…')
    try {
      const res = await fetch('/api/product/identify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ images }),
      })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setIdentified(data.identified)

      if (data.product && data.has_inci) {
        setFoundProduct(data.product)
        setProductStage('found')
        return
      }

      setProductStage('searching')
      setProductStatus('Ищем продукт в интернете…')
      const ws = await fetch('/api/product/web-search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brand: data.identified?.brand || '',
          name: data.identified?.name || '',
          variant: data.identified?.variant || null,
        }),
      })
      if (ws.ok) {
        const wsData = await ws.json()
        if (wsData.found && wsData.product) {
          setFoundProduct(wsData.product)
          setProductStage('found')
          return
        }
      }
      setProductStage('fallback')
    } catch {
      setProductStage('error')
      setProductStatus('Не удалось определить продукт. Попробуйте ещё раз или введите вручную.')
    }
  }

  const handleProductFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const imgs: string[] = []
    for (const f of Array.from(files)) imgs.push(await fileToResizedDataUrl(f))
    if (imgs.length) await runProductIdentify(imgs)
  }

  const handleProductCheck = (p: FoundProduct) => {
    const brand = (p.brand || '').trim()
    const name = (p.name || '').trim()
    const productStr = brand && name && name.toLowerCase().startsWith(brand.toLowerCase())
      ? name
      : brand && name
        ? `${brand}\n${name}`
        : name
    onCheck(productStr, 'Нормальная')
    onClose()
  }

  const gotoComposition = () => {
    const brand = identified?.brand || ''
    const name = identified?.name || ''
    resetPhotoFlow()
    setMode('photo')
    setBrandInput(brand)
    setNameInput(name)
  }

  const modes = [
    { id: 'product', label: 'Продукт', icon: Camera },
    { id: 'photo', label: 'Состав', icon: Sparkles },
    { id: 'name', label: 'Название', icon: Search },
    { id: 'link', label: 'Ссылка', icon: Link2 },
  ]

  return (
    <>
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={onClose}>
      <div className="flex max-h-[85dvh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-white/50 bg-white/75 backdrop-blur-xl animate-modal-panel" onClick={(e) => e.stopPropagation()}>
        {/* Заголовок закреплён при прокрутке (как в отчёте и карточках) */}
        <div className="flex shrink-0 items-center justify-between border-b border-gray-100 px-4 pt-4 pb-3">
          <h2 className="text-base font-normal text-foreground">Проверить продукт</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
        </div>

        <div className="no-scrollbar min-h-[320px] flex-1 overflow-y-auto px-4 pb-4 pt-3">
        <div className="mb-3 flex rounded-xl bg-gray-100 p-1">
          {modes.map((m) => (
            <button
              key={m.id}
              onClick={() => {
                setShowSuggestions(false)
                if (m.id === 'product') { enterProductMode(); return }
                if (m.id === 'photo') enterPhotoMode()
                else { setMode(m.id as any); setStatus('') }
              }}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-colors',
                mode === m.id ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground/60 hover:bg-white/50 hover:text-foreground'
              )}
            >
              <m.icon className="size-3.5" />
              {m.label}
            </button>
          ))}
        </div>

        <div key={mode} className="check-tab-bounce">
        {mode === 'product' && (
          <div className="space-y-3">
            {productStage === 'idle' && (
              <>
                <button
                  onClick={() => productFileRef.current?.click()}
                  className="flex w-full flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-gray-50 py-8 text-center transition-colors hover:bg-gray-100"
                >
                  <Camera className="mb-2 size-7 text-muted-foreground/40" />
                  <p className="text-xs text-muted-foreground/70">Сфотографируйте продукт</p>
                  <p className="mt-1 px-4 text-[10px] text-muted-foreground/40">Мы определим бренд и название, найдём состав и проверим совместимость</p>
                </button>
                <input ref={productFileRef} type="file" accept="image/*" capture="environment" multiple className="hidden" onChange={(e) => handleProductFiles(e.target.files)} />
              </>
            )}

            {(productStage === 'identifying' || productStage === 'searching') && (
              <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-gray-200 bg-gray-50 py-8 text-center">
                <LoaderCircle className="size-6 animate-spin text-primary" />
                <p className="text-xs text-muted-foreground/70">{productStatus}</p>
              </div>
            )}

            {productStage === 'found' && foundProduct && (
              <div className="space-y-3">
                <div className="rounded-xl border border-gray-200 p-3">
                  <p className="text-[11px] text-muted-foreground/60">Найден продукт</p>
                  {foundProduct.brand && <p className="mt-0.5 text-sm font-medium text-foreground">{foundProduct.brand}</p>}
                  <p className="text-sm text-foreground/80">{foundProduct.name}</p>
                </div>
                <button onClick={() => handleProductCheck(foundProduct)} className="w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90">
                  Проверить совместимость
                </button>
                <button onClick={() => setProductStage('fallback')} className="w-full text-xs text-muted-foreground/70">
                  Это не тот продукт
                </button>
              </div>
            )}

            {productStage === 'fallback' && (
              <div className="space-y-3 text-center">
                <h3 className="text-sm font-medium text-foreground">Не удалось найти состав</h3>
                {identified?.brand && <p className="text-xs text-muted-foreground">Определено: {identified.brand} {identified.name}</p>}
                <p className="text-xs text-muted-foreground/70">Сфотографируйте состав на упаковке или введите его вручную.</p>
                <button onClick={gotoComposition} className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90">
                  <Camera className="size-4" /> Сфотографировать состав
                </button>
                <button onClick={gotoComposition} className="flex w-full items-center justify-center gap-2 rounded-xl border border-gray-300 py-2.5 text-sm text-foreground transition-colors hover:bg-gray-50">
                  <Keyboard className="size-4" /> Ввести вручную
                </button>
              </div>
            )}

            {productStage === 'error' && (
              <div className="space-y-3 text-center">
                <p className="text-sm font-medium text-foreground">{productStatus}</p>
                <div className="flex w-full flex-col gap-2">
                  <button onClick={() => setProductStage('idle')} className="rounded-xl bg-primary py-2.5 text-sm text-primary-foreground">
                    Повторить фото
                  </button>
                  <button onClick={gotoComposition} className="rounded-xl border border-gray-300 py-2.5 text-sm text-foreground">
                    Ввести вручную
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {mode === 'name' && (
          <div>
            <div className="flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleName()}
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                placeholder="Название продукта…"
                className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none"
              />
              <button onClick={handleName} disabled={!name.trim() || loading} className="shrink-0 rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40">
                Проверить
              </button>
            </div>

            {showSuggestions && suggestions.length > 0 && (
              <div className="mt-2 max-h-60 overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-sm">
                {suggestions.map((s, i) => (
                  <button
                    key={`${s.name}-${i}`}
                    onClick={() => selectSuggestion(s)}
                    className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-primary/5"
                  >
                    <div className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-50">
                      {s.image_url ? (
                        <img src={s.image_url} alt="" className="h-full w-full object-contain p-1" />
                      ) : (
                        <Search className="size-4 text-muted-foreground/30" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      {s.brand && <p className="text-[10px] uppercase tracking-wide text-muted-foreground/50">{s.brand}</p>}
                      <p className="truncate text-sm text-foreground">{s.title || s.brand}</p>
                    </div>
                  </button>
                ))}

                {onOpenCatalog && (
                  <button
                    onClick={() => {
                      onOpenCatalog(name.trim())
                      setShowSuggestions(false)
                      setName('')
                      onClose()
                    }}
                    className="flex w-full items-center justify-between gap-2 border-t border-gray-100 px-3 py-2.5 text-left text-xs text-primary transition-colors hover:bg-primary/5"
                  >
                    <span className="truncate">Посмотреть больше в каталоге → {name.trim()}</span>
                    <Search className="size-3.5 shrink-0" />
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {mode === 'link' && (
          <div>
            <div className="flex gap-2">
              <input
                value={link}
                onChange={(e) => setLink(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleLink()}
                placeholder="Вставьте ссылку на товар…"
                className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none"
              />
              <button onClick={handleLink} disabled={!link.trim() || loading} className="shrink-0 rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40">
                {loading ? <LoaderCircle className="size-4 animate-spin" /> : 'Проверить'}
              </button>
            </div>
            {status && <p className="mt-2 text-[11px] text-muted-foreground/60">{status}</p>}
          </div>
        )}

        {mode === 'photo' && (
          <div className="space-y-3">
            {recognition && (
              <button onClick={resetPhotoFlow} className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground">
                <ChevronLeft className="size-3.5" /> Сфотографировать заново
              </button>
            )}

            {!recognition ? (
              <>
                {photos.length > 0 && (
                  <div className="grid grid-cols-3 gap-2">
                    {photos.map((p, i) => (
                      <div key={`${i}-${p.slice(-20)}`} className="relative aspect-square overflow-hidden rounded-xl border border-gray-200 bg-gray-50">
                        <img src={p} alt={`Фото ${i + 1}`} className="h-full w-full object-cover" />
                        <span className="absolute left-1 top-1 rounded bg-black/50 px-1 text-[9px] text-white">{i + 1}</span>
                        <button onClick={() => handleRemovePhoto(i)} className="absolute right-1 top-1 rounded-full bg-black/50 p-0.5 text-white" aria-label="Удалить фото">
                          <Trash2 className="size-3" />
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={() => fileRef.current?.click()}
                      className="flex aspect-square flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-gray-50 text-muted-foreground/60 transition-colors hover:bg-gray-100"
                    >
                      <Camera className="size-5" />
                      <span className="mt-1 text-[10px]">Добавить</span>
                    </button>
                  </div>
                )}

                {photos.length === 0 && (
                  <button
                    onClick={() => fileRef.current?.click()}
                    className="flex w-full flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-gray-50 py-8 text-center transition-colors hover:bg-gray-100"
                  >
                    <Camera className="mb-2 size-7 text-muted-foreground/40" />
                    <p className="text-xs text-muted-foreground/70">Добавьте фото состава</p>
                    <p className="mt-1 px-4 text-[10px] text-muted-foreground/40">Можно несколько фото одного продукта — система соберёт их в единый состав</p>
                  </button>
                )}

                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  multiple
                  capture="environment"
                  className="hidden"
                  onChange={(e) => { handleAddPhotos(e.target.files); e.target.value = '' }}
                />

                <button
                  onClick={handleRecognize}
                  disabled={!photos.length || photoBusy}
                  className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                  {photoBusy ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                  {photoBusy ? 'Распознаём состав…' : 'Распознать'}
                </button>
              </>
            ) : showManualForm ? (
              <div className="rounded-xl border border-gray-200 p-3">
                <p className="mb-2 text-[11px] text-muted-foreground/60">Укажите продукт вручную</p>
                <div className="relative mb-2">
                  <input
                    value={brandInput}
                    onChange={(e) => setBrandInput(e.target.value)}
                    placeholder="Бренд"
                    className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm focus:border-primary/40 focus:outline-none"
                  />
                  {brandOptions.length > 0 && (
                    <div className="absolute z-10 mt-1 max-h-40 w-full overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-lg">
                      {brandOptions.map((b) => (
                        <button key={b} onClick={() => { setBrandInput(b); setBrandOptions([]) }} className="block w-full px-3 py-2 text-left text-sm transition-colors hover:bg-primary/5">
                          {b}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <input
                    value={nameInput}
                    onChange={(e) => { setNameInput(e.target.value); if (nameError) setNameError('') }}
                    placeholder="Название продукта *"
                    aria-invalid={!!nameError}
                    className={`w-full rounded-xl border px-3 py-2 text-sm focus:outline-none ${
                      nameError
                        ? 'border-red-400 bg-red-50 focus:border-red-400'
                        : 'border-gray-200 bg-gray-50 focus:border-primary/40'
                    }`}
                  />
                  {nameError && <p className="mt-1 text-[11px] text-red-500">{nameError}</p>}
                </div>
                <button
                  onClick={handleCreateProduct}
                  disabled={creatingProduct || analyzing}
                  className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                  {creatingProduct || analyzing ? <LoaderCircle className="size-4 animate-spin" /> : <Check className="size-4" />}
                  {creatingProduct ? 'Сохраняем…' : analyzing ? 'Анализируем…' : 'Сохранить и проанализировать'}
                </button>
              </div>
            ) : (
              <>
                <div className="rounded-xl border border-gray-200 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-[11px] font-medium text-foreground/70">Распознанный состав</p>
                    {recognition.overall_confidence != null && (
                      <span className="text-[10px] text-muted-foreground/50">уверенность {Math.round(recognition.overall_confidence * 100)}%</span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {recognition.ingredients.map((ing, i) => (
                      <span key={`${ing.normalized}-${i}`} className="rounded-full bg-primary/5 px-2 py-1 text-[10px] text-foreground/70">
                        {ing.normalized}
                      </span>
                    ))}
                  </div>
                  {recognition.uncertain_items.length > 0 && (
                    <div className="mt-2 flex items-start gap-1.5 rounded-lg bg-amber-50 p-2 text-[10px] text-amber-700">
                      <AlertCircle className="mt-0.5 size-3 shrink-0" />
                      <span>Плохо читаемые участки: {recognition.uncertain_items.map((u) => u.text).join(', ')}</span>
                    </div>
                  )}
                </div>

                {matches.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-[11px] text-muted-foreground/60">
                      {(matches[0]?.match_percent ?? 0) >= confidentThreshold ? 'Мы предполагаем, что это:' : 'Похожие продукты по составу:'}
                    </p>
                    {matches.map((m) => (
                      <div key={m.slug || m.name} className="flex items-center gap-2.5 rounded-xl border border-gray-200 p-2.5">
                        <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-50">
                          {m.image_url ? <img src={m.image_url} alt="" className="h-full w-full object-contain p-1" /> : <Sparkles className="size-4 text-muted-foreground/30" />}
                        </div>
                        <div className="min-w-0 flex-1">
                          {m.brand && <p className="text-[9px] uppercase tracking-wide text-muted-foreground/50">{m.brand}</p>}
                          <p className="truncate text-xs font-medium text-foreground/90">{m.name}</p>
                          <p className="text-[10px] text-primary">Совпадение состава: {Math.round(m.match_percent)}%</p>
                        </div>
                        <button
                          onClick={() => handleConfirmMatch(m)}
                          disabled={analyzing}
                          className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                        >
                          {analyzing ? <LoaderCircle className="size-3.5 animate-spin" /> : 'Это он'}
                        </button>
                      </div>
                    ))}
                    <button onClick={() => setShowManualForm(true)} className="w-full rounded-xl border border-gray-200 py-2.5 text-xs text-muted-foreground transition-colors hover:bg-gray-50">
                      Другой продукт
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-center text-xs text-muted-foreground/60">Подходящий продукт не найден в базе.</p>
                    <button onClick={() => setShowManualForm(true)} className="w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90">
                      Указать бренд и название
                    </button>
                  </div>
                )}
              </>
            )}

            {photoStatus && <p className="text-[11px] text-red-500">{photoStatus}</p>}
          </div>
        )}
        </div>
        </div>
      </div>
    </div>
    </>
  )
}