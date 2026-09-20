'use client'

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { X, Link2, Search, Camera, LoaderCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useScrollLock } from '@/lib/use-scroll-lock'

type Suggestion = { name: string; brand: string; title: string; image_url: string }

function splitName(raw: string): { brand: string; title: string } {
  const parts = (raw || '').split('\n').filter((x) => x.trim())
  if (parts.length >= 2) return { brand: parts[0], title: parts.slice(1).join(' ') }
  return { brand: '', title: (raw || '').trim() }
}

export function CheckModal({ isOpen, onClose, onCheck }: {
  isOpen: boolean
  onClose: () => void
  onCheck: (product: string, skinType: string) => void
}) {
  const [mode, setMode] = useState<'name' | 'link' | 'photo'>('name')
  const [name, setName] = useState('')
  const [link, setLink] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number; width: number } | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputWrapRef = useRef<HTMLDivElement | null>(null)

  useScrollLock(isOpen)

  useEffect(() => {
    if (!showSuggestions || !inputWrapRef.current) {
      setDropdownPos(null)
      return
    }
    const rect = inputWrapRef.current.getBoundingClientRect()
    setDropdownPos({ top: rect.bottom + 4, left: rect.left, width: rect.width })
  }, [showSuggestions, suggestions])

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
      const res = await fetch('/api/products/import-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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

  const modes = [
    { id: 'name', label: 'Название', icon: Search },
    { id: 'link', label: 'Ссылка', icon: Link2 },
    { id: 'photo', label: 'Фото', icon: Camera },
  ]

  return (
    <>
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={onClose}>
      <div className="max-h-[85dvh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-4 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-normal text-foreground">Проверить продукт</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
        </div>

        <div className="mb-3 flex rounded-xl bg-gray-100 p-1">
          {modes.map((m) => (
            <button
              key={m.id}
              onClick={() => { setMode(m.id as any); setStatus('') }}
              disabled={m.id === 'photo'}
              className={cn(
                'flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-colors',
                mode === m.id ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground/60',
                m.id === 'photo' && 'cursor-not-allowed opacity-50'
              )}
            >
              <m.icon className="size-3.5" />
              {m.label}
            </button>
          ))}
        </div>

        {mode === 'name' && (
          <div className="relative" ref={inputWrapRef}>
            <div className="flex gap-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleName()}
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
                placeholder="Название продукта…"
                className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none"
              />
              <button onClick={handleName} disabled={!name.trim() || loading} className="shrink-0 rounded-xl bg-primary px-4 py-2.5 text-sm text-white transition-colors hover:bg-primary/90 disabled:opacity-40">
                Проверить
              </button>
            </div>
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
              <button onClick={handleLink} disabled={!link.trim() || loading} className="shrink-0 rounded-xl bg-primary px-4 py-2.5 text-sm text-white transition-colors hover:bg-primary/90 disabled:opacity-40">
                {loading ? <LoaderCircle className="size-4 animate-spin" /> : 'Проверить'}
              </button>
            </div>
            {status && <p className="mt-2 text-[11px] text-muted-foreground/60">{status}</p>}
          </div>
        )}

        {mode === 'photo' && (
          <div className="rounded-xl border border-dashed border-gray-200 bg-gray-50 py-8 text-center">
            <Camera className="mx-auto mb-2 size-6 text-muted-foreground/30" />
            <p className="text-xs text-muted-foreground/50">Распознавание состава по фото скоро появится</p>
          </div>
        )}
      </div>
    </div>

    {showSuggestions && suggestions.length > 0 && dropdownPos && typeof document !== 'undefined' &&
      createPortal(
        <div
          className="fixed z-[100] max-h-72 overflow-y-auto rounded-xl border border-gray-200 bg-white shadow-lg"
          style={{ top: dropdownPos.top, left: dropdownPos.left, width: dropdownPos.width }}
        >
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
        </div>,
        document.body,
      )}
    </>
  )
}