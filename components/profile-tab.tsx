'use client'

import { forwardRef, useState, useImperativeHandle } from 'react'
import { Check, X, User, Droplets, Calendar, AlertCircle, Sparkles, Trash2 } from 'lucide-react'
import { Chip } from '@/components/chip'
import { AGE_GROUPS, ALLERGIES, SKIN_CONCERNS, SKIN_TYPES } from '@/lib/products'
import type { SkinProfile } from '@/lib/store'
import { cn } from '@/lib/utils'

interface ProfileTabProps {
  profile: SkinProfile
  onSave: (p: SkinProfile) => void
  onStartQuiz?: () => void
}

export const ProfileTab = forwardRef<{ getDraft: () => SkinProfile }, ProfileTabProps>(
  ({ profile, onSave, onStartQuiz }, ref) => {
    const [name, setName] = useState(profile.name || '')
    const [skinType, setSkinType] = useState(profile.skinType || '')
    const [age, setAge] = useState(profile.age || '')
    const [concerns, setConcerns] = useState<string[]>(profile.concerns || [])
    const [allergies, setAllergies] = useState<string[]>(profile.allergies || [])
    const [customText, setCustomText] = useState(profile.customText || '')
    const [saved, setSaved] = useState(true)
    const [showReset, setShowReset] = useState(false)

    useImperativeHandle(ref, () => ({
      getDraft: () => ({ name, skinType, age, concerns, allergies, customText }),
    }))

    const hasChanges =
      name !== profile.name ||
      skinType !== profile.skinType ||
      age !== profile.age ||
      JSON.stringify(concerns) !== JSON.stringify(profile.concerns) ||
      JSON.stringify(allergies) !== JSON.stringify(profile.allergies) ||
      customText !== profile.customText

    const toggle = (key: 'concerns' | 'allergies', value: string) => {
      if (key === 'concerns') {
        setConcerns(prev => prev.includes(value) ? prev.filter(v => v !== value) : [...prev, value])
      } else {
        setAllergies(prev => prev.includes(value) ? prev.filter(v => v !== value) : [...prev, value])
      }
      setSaved(false)
    }

    const handleSave = () => {
      onSave({ name, skinType, age, concerns, allergies, customText })
      setSaved(true)
    }

    const handleReset = () => {
      setName('')
      setSkinType('')
      setAge('')
      setConcerns([])
      setAllergies([])
      setCustomText('')
      onSave({ name: '', skinType: '', age: '', concerns: [], allergies: [], customText: '' })
      setSaved(true)
      setShowReset(false)
    }

    const isEmpty = !name && !skinType && !age && concerns.length === 0 && allergies.length === 0 && !customText

    const glassCardStyle = (delay: number) => cn(
      'bg-white/20 backdrop-blur-xl',
      'border border-white/20',
      'shadow-[0_8px_32px_rgba(108,60,225,0.06)]',
      'hover:shadow-[0_12px_48px_rgba(108,60,225,0.1)]',
      'transition-all duration-500',
      'rounded-2xl p-4',
      'hover:bg-white/30 hover:border-primary/20',
      'card-enter',
      `card-enter-${delay}`
    )

    const Section = ({ icon: Icon, title, children, delay }: any) => (
      <div className={glassCardStyle(delay)}>
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
      <div className="h-full flex flex-col overflow-y-auto pb-24 space-y-3 pr-1">
        <Section icon={User} title="Как к вам обращаться?" delay={1}>
          <input
            type="text"
            value={name}
            onChange={(e) => { setName(e.target.value); setSaved(false) }}
            placeholder="Например: Райан Гослинг..."
            className="w-full bg-transparent text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:outline-none"
            maxLength={30}
          />
          <div className="mt-1 text-right text-[10px] text-muted-foreground/40">
            {name.length}/30
          </div>
        </Section>

        <Section icon={Droplets} title="Тип кожи" delay={2}>
          <div className="flex flex-wrap gap-1.5">
            {SKIN_TYPES.map((t) => (
              <Chip
                key={t}
                label={t}
                active={skinType === t}
                onClick={() => { setSkinType(t); setSaved(false) }}
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
                active={age === a}
                onClick={() => { setAge(a); setSaved(false) }}
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
                active={concerns.includes(c)}
                onClick={() => toggle('concerns', c)}
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
                active={allergies.includes(a)}
                onClick={() => toggle('allergies', a)}
              />
            ))}
          </div>
        </Section>

        <Section icon={Sparkles} title="Опишите проблему" delay={6}>
          <p className="text-[10px] text-muted-foreground/50 font-light mb-2">
            Коротко, 1 предложение (до 100 символов)
          </p>
          <textarea
            value={customText}
            onChange={(e) => {
              const text = e.target.value
              if (text.length <= 100) {
                setCustomText(text)
                setSaved(false)
              }
            }}
            placeholder="Например: кожа стягивается после умывания..."
            className="w-full bg-transparent text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:outline-none resize-none"
            rows={2}
          />
          <div className={`mt-1 text-right text-[10px] ${customText.length >= 100 ? 'text-orange-400' : 'text-muted-foreground/40'}`}>
            {customText.length}/100
          </div>
        </Section>

        {!isEmpty && (
          <div className="flex gap-2 pt-1">
            <button
              onClick={() => setShowReset(true)}
              className="px-4 py-2.5 rounded-xl border border-red-200/50 bg-white/10 backdrop-blur-sm text-xs font-medium text-red-400 transition-all hover:bg-red-500/10"
            >
              <Trash2 className="size-3.5 inline mr-1.5" />
              Сбросить
            </button>
            <button
              onClick={handleSave}
              disabled={!hasChanges || saved}
              className={cn(
                'flex-1 px-6 py-2.5 rounded-xl text-xs font-medium uppercase tracking-wider transition-all',
                !hasChanges || saved
                  ? 'bg-white/10 backdrop-blur-sm text-muted-foreground/40 cursor-default border border-white/10'
                  : 'bg-primary/20 backdrop-blur-sm border border-primary/30 text-primary hover:bg-primary/30 hover:shadow-[0_0_30px_rgba(108,60,225,0.15)] active:scale-[0.97]'
              )}
            >
              {saved ? (
                <>
                  <Check className="size-3.5 inline mr-1.5" />
                  Сохранено
                </>
              ) : (
                'Сохранить'
              )}
            </button>
          </div>
        )}

        {showReset && (
          <>
            <div className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm" onClick={() => setShowReset(false)} />
            <div className="fixed left-1/2 top-1/2 z-50 w-80 -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white/90 backdrop-blur-xl border border-white/30 p-6 shadow-2xl">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-base font-light text-foreground">Сбросить анкету?</h3>
                <button onClick={() => setShowReset(false)} className="text-muted-foreground/60 hover:text-foreground">
                  <X className="size-4.5" />
                </button>
              </div>
              <p className="text-sm text-muted-foreground/70 font-light mb-6">
                Все данные анкеты будут удалены. Это действие нельзя отменить.
              </p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowReset(false)}
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