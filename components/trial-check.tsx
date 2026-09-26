'use client'

import { useRef, useState } from 'react'
import { ArrowRight, Camera, Link2, LoaderCircle, Search, Sparkles } from 'lucide-react'
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

type TrialResult = { score: number; verdict: string }

export function TrialCheck({ onAuth }: { onAuth: () => void }) {
  const [skinType, setSkinType] = useState('')
  const [concerns, setConcerns] = useState<string[]>([])
  const [mode, setMode] = useState<'name' | 'link' | 'photo'>('name')
  const [name, setName] = useState('')
  const [link, setLink] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<TrialResult | null>(null)
  const [error, setError] = useState('')
  const [photoName, setPhotoName] = useState('')
  const fileRef = useRef<HTMLInputElement | null>(null)

  const profileBody = () => ({
    name: '',
    age: '',
    concerns,
    allergies: [],
    custom_text: '',
    quiz_answers: {},
    skin_type_determined: skinType || '',
  })

  const runCheck = async (productName: string) => {
    const res = await fetch('/api/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_name: productName,
        skin_type: skinType || 'Нормальная',
        profile: profileBody(),
      }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || 'Не удалось проверить')
    setResult({ score: data.score ?? 0, verdict: data.verdict ?? '' })
  }

  const checkName = async () => {
    if (!name.trim() || loading) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      await runCheck(name.trim())
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
    setResult(null)
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
      await runCheck(productName)
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
    setResult(null)
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
      await runCheck(match.name)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось распознать состав')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full rounded-2xl border border-white/60 bg-white/90 p-4 text-left shadow-2xl backdrop-blur-xl">
      <div className="mb-3 flex items-center gap-1.5">
        <Sparkles className="size-4 text-primary/70" />
        <p className="text-xs font-medium uppercase tracking-wide text-foreground/70">Попробуйте бесплатно</p>
      </div>

      <p className="text-[11px] font-medium text-muted-foreground/70">Тип кожи</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {SKIN_TYPES.map((s) => (
          <button
            key={s}
            onClick={() => setSkinType(s)}
            className={cn('rounded-full border px-2.5 py-1 text-[11px] transition-colors', skinType === s ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-200 text-foreground/70 hover:border-primary/40')}
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
            className={cn('rounded-full border px-2.5 py-1 text-[11px] transition-colors', concerns.includes(c) ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/70 hover:border-primary/40')}
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
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && checkName()}
            placeholder="Название продукта…"
            className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-white/70 px-3 py-2 text-sm focus:border-primary/40 focus:outline-none"
          />
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

      {result && (
        <div className="mt-3 rounded-xl border border-primary/15 bg-primary/5 p-3 text-center">
          <div className="flex items-center justify-center gap-3">
            <span className="text-3xl font-light tabular-nums text-primary">{result.score}%</span>
            <span className="text-xs text-muted-foreground/70">{result.verdict}</span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-foreground/70">
            Это только начало… пройдите анкету — и мы поможем подобрать ваш идеальный уход за пару минут.
          </p>
          <button
            onClick={onAuth}
            className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary py-2.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Зарегистрироваться
            <ArrowRight className="size-3.5" />
          </button>
          <p className="mt-1.5 text-[10px] text-muted-foreground/60">
            Зарегистрированным пользователям — 20 кредитов бесплатно (1 кредит = 1 проверка)
          </p>
        </div>
      )}
    </div>
  )
}

