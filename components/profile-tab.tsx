'use client'

import { forwardRef, useState, useEffect, useImperativeHandle } from 'react'
import { Check, Trash2, X } from 'lucide-react'
import { Chip } from '@/components/chip'
import { ScrambleText } from '@/components/scramble-text'
import { AGE_GROUPS, ALLERGIES, SKIN_CONCERNS, SKIN_TYPES } from '@/lib/products'
import type { SkinProfile } from '@/lib/store'
import { cn } from '@/lib/utils'

interface ProfileTabProps {
  profile: SkinProfile
  onSave: (p: SkinProfile) => void
  onDirtyChange: (dirty: boolean) => void
  onStartQuiz?: () => void
}

export const ProfileTab = forwardRef<{ getDraft: () => SkinProfile }, ProfileTabProps>(
  ({ profile, onSave, onDirtyChange, onStartQuiz }, ref) => {
    const [draft, setDraft] = useState<SkinProfile>(profile)
    const [saved, setSaved] = useState(false)
    const [hasChanges, setHasChanges] = useState(false)
    const [showResetConfirm, setShowResetConfirm] = useState(false)
    const [isVisible, setIsVisible] = useState(false)

    const MAX_CUSTOM_TEXT = 100

    useEffect(() => {
      const timer = setTimeout(() => setIsVisible(true), 50)
      return () => clearTimeout(timer)
    }, [])

    useImperativeHandle(ref, () => ({
      getDraft: () => draft,
    }))

    useEffect(() => {
      const isChanged = JSON.stringify(draft) !== JSON.stringify(profile)
      setHasChanges(isChanged)
      if (isChanged) {
        setSaved(false)
      }
      if (onDirtyChange) {
        onDirtyChange(isChanged)
      }
    }, [draft, profile, onDirtyChange])

    const toggleArray = (key: 'concerns' | 'allergies', value: string) => {
      setDraft((prev) => {
        const set = new Set(prev[key])
        if (set.has(value)) set.delete(value)
        else set.add(value)
        return { ...prev, [key]: Array.from(set) }
      })
    }

    const handleSave = () => {
      onSave(draft)
      setSaved(true)
      setHasChanges(false)
    }

    const handleChange = (field: keyof SkinProfile, value: any) => {
      setDraft((prev) => ({ ...prev, [field]: value }))
    }

    const handleReset = () => {
      const emptyProfile: SkinProfile = {
        name: '',
        skinType: '',
        age: '',
        concerns: [],
        allergies: [],
        customText: '',
      }
      setDraft(emptyProfile)
      onSave(emptyProfile)
      setSaved(true)
      setHasChanges(false)
      setShowResetConfirm(false)
    }

    const isProfileEmpty = () => {
      return (
        !draft.name &&
        !draft.skinType &&
        !draft.age &&
        draft.concerns.length === 0 &&
        draft.allergies.length === 0 &&
        !draft.customText
      )
    }

    const profileEmpty = isProfileEmpty()
    const cardStyle = "relative overflow-hidden bg-gradient-to-br from-primary/10 via-primary/5 to-transparent rounded-2xl p-5 border border-primary/20 backdrop-blur-sm hover:shadow-md transition-shadow"

    return (
      <div className="flex flex-col gap-5 max-w-md mx-auto">
        <ScrambleText
          as="h1"
          text="Мои данные для AI"
          className="text-2xl font-normal text-foreground"
        />

        {/* === ИМЯ === */}
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-1')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative">
            <h2 className="mb-3 text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground">
              Как к вам обращаться?
            </h2>
            <input
              type="text"
              value={draft.name || ''}
              onChange={(e) => handleChange('name', e.target.value)}
              placeholder="Например: Райан Гослинг..."
              className="w-full rounded-xl border border-primary/15 bg-white/50 px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              maxLength={30}
            />
            <div className="mt-1 text-right text-xs text-muted-foreground">
              {(draft.name?.length || 0)}/30
            </div>
          </div>
        </div>

        {/* === ТИП КОЖИ === */}
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-2')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative">
            <h2 className="mb-3 text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground">
              Тип кожи
            </h2>
            <div className="flex flex-wrap gap-2">
              {SKIN_TYPES.map((t) => (
                <Chip
                  key={t}
                  label={t}
                  active={draft.skinType === t}
                  onClick={() => handleChange('skinType', t)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* === ВОЗРАСТ === */}
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-3')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative">
            <h2 className="mb-3 text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground">
              Возраст
            </h2>
            <div className="flex flex-wrap gap-2">
              {AGE_GROUPS.map((a) => (
                <Chip
                  key={a}
                  label={a}
                  active={draft.age === a}
                  onClick={() => handleChange('age', a)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* === ЧТО БЕСПОКОИТ === */}
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-4')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative">
            <h2 className="mb-3 text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground">
              Что беспокоит
            </h2>
            <div className="flex flex-wrap gap-2">
              {SKIN_CONCERNS.map((c) => (
                <Chip
                  key={c}
                  label={c}
                  active={draft.concerns.includes(c)}
                  onClick={() => toggleArray('concerns', c)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* === АЛЛЕРГИИ === */}
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-5')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative">
            <h2 className="mb-3 text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground">
              Аллергии
            </h2>
            <div className="flex flex-wrap gap-2">
              {ALLERGIES.map((a) => (
                <Chip
                  key={a}
                  label={a}
                  active={draft.allergies.includes(a)}
                  onClick={() => toggleArray('allergies', a)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* === ОПИШИТЕ ПРОБЛЕМУ === */}
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-6')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative">
            <h2 className="mb-3 text-xs font-normal uppercase tracking-[0.08em] text-muted-foreground">
              Опишите проблему
            </h2>
            <p className="mb-2 text-xs text-muted-foreground">
              Коротко, 1 предложение (до 100 символов)
            </p>
            <textarea
              value={draft.customText || ''}
              onChange={(e) => {
                const text = e.target.value
                if (text.length <= MAX_CUSTOM_TEXT) {
                  handleChange('customText', text)
                }
              }}
              placeholder="Например: кожа стягивается после умывания"
              className="w-full rounded-xl border border-primary/15 bg-white/50 px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              rows={2}
              maxLength={MAX_CUSTOM_TEXT}
            />
            <div className={`mt-1 text-right text-xs ${(draft.customText?.length || 0) >= MAX_CUSTOM_TEXT ? 'text-orange-500' : 'text-muted-foreground'}`}>
              {draft.customText?.length || 0}/{MAX_CUSTOM_TEXT}
            </div>
          </div>
        </div>

        {/* === КНОПКИ === */}
        {!profileEmpty && (
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setShowResetConfirm(true)}
              className="flex items-center justify-center gap-2 rounded-xl border border-red-300 px-4 py-3 text-sm font-normal text-red-500 transition-all hover:bg-red-50 hover:border-red-400"
            >
              <Trash2 className="size-4" />
              Сбросить
            </button>

            <button
              type="button"
              onClick={handleSave}
              disabled={!hasChanges || saved}
              className={`flex-1 flex items-center justify-center gap-2 rounded-xl px-6 py-3 font-normal uppercase tracking-wider transition-all ${!hasChanges || saved
                  ? 'bg-transparent text-primary hover:bg-transparent hover:shadow-none cursor-default'
                  : 'bg-primary text-primary-foreground hover:shadow-[0_0_28px_rgba(255,79,0,0.5)] active:scale-[0.97]'
                }`}
            >
              {saved || !hasChanges ? (
                <>
                  <Check className="size-4" />
                  Сохранено
                </>
              ) : (
                'Сохранить'
              )}
            </button>
          </div>
        )}

        {/* === ПОПАП ПОДТВЕРЖДЕНИЯ СБРОСА === */}
        {showResetConfirm && (
          <>
            <div
              className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
              onClick={() => setShowResetConfirm(false)}
            />
            <div className="fixed left-1/2 top-1/2 z-50 w-80 -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-xl border border-red-200">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-normal text-foreground">Сбросить анкету?</h3>
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-5" />
                </button>
              </div>
              <p className="text-sm text-muted-foreground mb-6">
                Все данные анкеты будут удалены. Это действие нельзя отменить.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="flex-1 rounded-xl border border-gray-200 px-4 py-2 text-sm font-normal text-gray-600 transition-colors hover:bg-gray-50"
                >
                  Отмена
                </button>
                <button
                  onClick={handleReset}
                  className="flex-1 rounded-xl bg-red-500 px-4 py-2 text-sm font-normal text-white transition-colors hover:bg-red-600"
                >
                  Сбросить
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    )
  }
)

ProfileTab.displayName = 'ProfileTab'
