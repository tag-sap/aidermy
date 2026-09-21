'use client'

import { useEffect, useRef, useState } from 'react'
import { X, LogOut, Camera, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useScrollLock } from '@/lib/use-scroll-lock'

export function AccountModal({
  isOpen,
  onClose,
  userName,
  userEmail,
  avatarUrl,
  onSaved,
  onLogout,
  onSwitchUser,
}: {
  isOpen: boolean
  onClose: () => void
  userName: string
  userEmail: string
  avatarUrl: string
  onSaved: (user: { name: string; avatar_url: string | null }) => void
  onLogout: () => void
  onSwitchUser: () => void
}) {
  const [name, setName] = useState(userName)
  const [avatar, setAvatar] = useState(avatarUrl)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement | null>(null)

  useScrollLock(isOpen)

  useEffect(() => {
    if (isOpen) {
      setName(userName)
      setAvatar(avatarUrl)
      setError('')
    }
  }, [isOpen, userName, avatarUrl])

  if (!isOpen) return null

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (file.size > 500000) {
      setError('Файл слишком большой (до 500 КБ)')
      return
    }
    const reader = new FileReader()
    reader.onload = () => setAvatar(reader.result as string)
    reader.readAsDataURL(file)
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const token = localStorage.getItem('token')
      const res = await fetch('/api/auth/account', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: name.trim(), avatar_url: avatar || null }),
      })
      if (!res.ok) throw new Error('Не удалось сохранить')
      const data = await res.json()
      onSaved({ name: data.name || '', avatar_url: data.avatar_url || null })
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop"
      onClick={onClose}
    >
      <div
        className="max-h-[88dvh] w-full max-w-sm overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl animate-modal-panel"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-xl font-normal text-foreground">Личный кабинет</h2>
          <button onClick={onClose} className="text-muted-foreground transition-colors hover:text-foreground">
            <X className="size-5" />
          </button>
        </div>

        <div className="mb-5 flex flex-col items-center">
          <div className="relative">
            <div className="flex size-20 items-center justify-center overflow-hidden rounded-full border border-primary/15 bg-primary/5">
              {avatar ? (
                <img src={avatar} alt="Аватар" className="h-full w-full object-cover" />
              ) : (
                <span className="text-2xl font-normal text-primary">{name?.[0]?.toUpperCase() || 'U'}</span>
              )}
            </div>
            <button
              onClick={() => fileRef.current?.click()}
              className="absolute -bottom-1 -right-1 flex size-8 items-center justify-center rounded-full border border-gray-200 bg-white text-primary shadow-sm transition-colors hover:bg-primary/5"
              aria-label="Загрузить аватар"
            >
              <Camera className="size-4" />
            </button>
            <input ref={fileRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
          </div>
          {avatar && (
            <button onClick={() => setAvatar('')} className="mt-2 text-[11px] text-muted-foreground/60 hover:text-red-500">
              Убрать аватар
            </button>
          )}
        </div>

        <label className="mb-1 block text-xs font-medium text-muted-foreground/70">Имя пользователя</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={40}
          placeholder="Ваше имя"
          className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none"
        />

        {userEmail && <p className="mt-2 text-xs text-muted-foreground/50">{userEmail}</p>}

        {error && <p className="mt-2 text-[11px] text-red-500">{error}</p>}

        <button
          onClick={save}
          disabled={saving || !name.trim()}
          className={cn(
            'mt-4 w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors',
            saving || !name.trim() ? 'cursor-not-allowed opacity-50' : 'hover:bg-primary/90',
          )}
        >
          {saving ? 'Сохраняем…' : 'Сохранить'}
        </button>

        <div className="mt-5 border-t border-gray-100 pt-4">
          <button
            onClick={onSwitchUser}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground transition-colors hover:bg-gray-50"
          >
            <RefreshCw className="size-4 text-muted-foreground" />
            Сменить пользователя
          </button>
          <button
            onClick={onLogout}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-red-500 transition-colors hover:bg-red-50"
          >
            <LogOut className="size-4" />
            Выйти
          </button>
        </div>
      </div>
    </div>
  )
}
