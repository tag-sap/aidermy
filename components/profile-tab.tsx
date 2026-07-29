'use client'

import { forwardRef, useState, useEffect, useImperativeHandle, useRef } from 'react'
import { Check, Trash2, X, User, Droplets, Calendar, AlertCircle, Sparkles } from 'lucide-react'
import { Chip } from '@/components/chip'
import { ScrambleText } from '@/components/scramble-text'
import { AGE_GROUPS, ALLERGIES, SKIN_CONCERNS, SKIN_TYPES } from '@/lib/products'
import type { SkinProfile } from '@/lib/store'
import { cn } from '@/lib/utils'

interface ProfileTabProps {
  profile: SkinProfile
  onSave: (p: SkinProfile) => void
  onDirtyChange?: (dirty: boolean) => void
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
    const scrollRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
      const timer = setTimeout(() => setIsVisible(true), 50)
      return () => clearTimeout(timer)
    }, [])

    useEffect(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = 0
      }
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
    }, [draft, profile])

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

    const glassCardStyle = cn(
      'bg-white/20 backdrop-blur-xl',
      'border border-white/20',
      'shadow-[0_8px_32px_rgba(108,60,225,0.06)]',
      'hover:shadow-[0_12px_48px_rgba(108,60,225,0.1)]',
      'transition-all duration-500',
      'rounded-2xl p-4',
      'hover:bg-white/30 hover:border-primary/20'
    )

    const Section = ({ icon: Icon, title, children, className, delay }: any) => (
      <div 
        className={cn(
          glassCardStyle,
          'card-enter',
          isVisible && `card-enter-${delay || 1}`,
          className
        )}
        style={{
          animationDelay: `${((delay || 1) - 1) * 80}ms`,
          animationFillMode: 'forwards'
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Icon className="size-4 text-primary/60" strokeWidth={1.5} />
          <h2 className="text-[10px] font-medium text-muted-foreground/70 uppercase tracking-wider">
            {title}
          </h2>
        </div>
        {children}
      </div>
    )

    return (
      <div className="h-full flex flex-col overflow-hidden pb-24">
        <div className="flex-shrink-0 pt-1 pb-3">
          <ScrambleText
            as="h1"
            text="Мои данные"
            className="text-xl font-light text-foreground/90"
          />
          <p className="text-[10px] text-muted-foreground/50 font-light mt-0.5">
            Заполните анкету для точных рекомендаций
          </p>
        </div>

        <div 
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-y-auto pr-1 pb-4 space-y-3"
        >
          <Section icon={User} title="Как к вам обращаться?" delay={1}>
            <input
              type="text"
              value={draft.name || ''}
              onChange={(e) => handleChange('name', e.target.value)}
              placeholder="Например: Райан Гослинг..."
              className="w-full rounded-xl bg-white/30 backdrop-blur-sm border border-white/20 px-4 py-2.5 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all"
              maxLength={30}
            />
            <div className="mt-1 text-right text-[10px] text-muted-foreground/40">
              {(draft.name?.length || 0)}/30
            </div>
          </Section>

          <Section icon={Droplets} title="Тип кожи" delay={2}>
            <div className="flex flex-wrap gap-1.5">
              {SKIN_TYPES.map((t) => (
                <Chip
                  key={t}
                  label={t}
                  active={draft.skinType === t}
                  onClick={() => handleChange('skinType', t)}
                />
              ))}
            </div>
          </Section>

          <Section icon={Calendar} title="Возраст" delay={3}>
            <div className="flex flex-wrap gap-1.5">
              {AGE_GROUPS.map((a) => (
                <Chip
                  key={a}
                  label={a}
                  active={draft.age === a}
                  onClick={() => handleChange('age', a)}
                />
              ))}
            </div>
          </Section>

          <Section icon={AlertCircle} title="Что беспокоит" delay={4}>
            <div className="flex flex-wrap gap-1.5">
              {SKIN_CONCERNS.map((c) => (
                <Chip
                  key={c}
                  label={c}
                  active={draft.concerns.includes(c)}
                  onClick={() => toggleArray('concerns', c)}
                />
              ))}
            </div>
          </Section>

          <Section icon={AlertCircle} title="Аллергии" delay={5}>
            <div className="flex flex-wrap gap-1.5">
              {ALLERGIES.map((a) => (
                <Chip
                  key={a}
                  label={a}
                  active={draft.allergies.includes(a)}
                  onClick={() => toggleArray('allergies', a)}
                />
              ))}
            </div>
          </Section>

          <Section icon={Sparkles} title="Опишите проблему" delay={6}>
            <p className="text-[10px] text-muted-foreground/50 font-light mb-2">
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
              className="w-full rounded-xl bg-white/30 backdrop-blur-sm border border-white/20 px-4 py-2.5 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all resize-none"
              rows={2}
              maxLength={MAX_CUSTOM_TEXT}
            />
            <div className={`mt-1 text-right text-[10px] ${(draft.customText?.length || 0) >= MAX_CUSTOM_TEXT ? 'text-orange-400' : 'text-muted-foreground/40'}`}>
              {draft.customText?.length || 0}/{MAX_CUSTOM_TEXT}
            </div>
          </Section>

          {!profileEmpty && (
            <div className="flex gap-2 pt-1 pb-2">
              <button
                type="button"
                onClick={() => setShowResetConfirm(true)}
                className="flex items-center justify-center gap-2 rounded-xl border border-red-200/50 bg-white/10 backdrop-blur-sm px-4 py-2.5 text-xs font-medium text-red-400 transition-all hover:bg-red-500/10 hover:border-red-300/50"
              >
                <Trash2 className="size-3.5" />
                Сбросить
              </button>

              <button
                type="button"
                onClick={handleSave}
                disabled={!hasChanges || saved}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2 rounded-xl px-6 py-2.5 text-xs font-medium uppercase tracking-wider transition-all',
                  !hasChanges || saved
                    ? 'bg-white/10 backdrop-blur-sm text-muted-foreground/40 cursor-default border border-white/10'
                    : 'bg-primary/20 backdrop-blur-sm border border-primary/30 text-primary hover:bg-primary/30 hover:shadow-[0_0_30px_rgba(108,60,225,0.15)] active:scale-[0.97]'
                )}
              >
                {saved || !hasChanges ? (
                  <>
                    <Check className="size-3.5" />
                    Сохранено
                  </>
                ) : (
                  'Сохранить'
                )}
              </button>
            </div>
          )}
        </div>

        {showResetConfirm && (
          <>
            <div
              className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm"
              onClick={() => setShowResetConfirm(false)}
            />
            <div className="fixed left-1/2 top-1/2 z-50 w-80 -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white/80 backdrop-blur-xl border border-white/30 p-6 shadow-2xl">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-light text-foreground">Сбросить анкету?</h3>
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="text-muted-foreground/60 hover:text-foreground transition-colors"
                >
                  <X className="size-4.5" />
                </button>
              </div>
              <p className="text-sm text-muted-foreground/70 font-light mb-6">
                Все данные анкеты будут удалены. Это действие нельзя отменить.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="flex-1 rounded-xl border border-gray-200/50 px-4 py-2.5 text-xs font-medium text-muted-foreground transition-all hover:bg-gray-50/50"
                >
                  Отмена
                </button>
                <button
                  onClick={handleReset}
                  className="flex-1 rounded-xl bg-red-500/20 backdrop-blur-sm border border-red-300/30 px-4 py-2.5 text-xs font-medium text-red-400 transition-all hover:bg-red-500/30"
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