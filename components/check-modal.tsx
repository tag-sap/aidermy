'use client'

import { useState } from 'react'
import { X, Link2, Search, Camera, LoaderCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useScrollLock } from '@/lib/use-scroll-lock'

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

  useScrollLock(isOpen)

  if (!isOpen) return null

  const handleName = () => {
    if (!name.trim() || loading) return
    onCheck(name.trim(), 'Нормальная')
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
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white p-4 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
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
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleName()}
              placeholder="Название продукта…"
              className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none"
            />
            <button onClick={handleName} disabled={!name.trim() || loading} className="shrink-0 rounded-xl bg-primary px-4 py-2.5 text-sm text-white transition-colors hover:bg-primary/90 disabled:opacity-40">
              Проверить
            </button>
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
  )
}