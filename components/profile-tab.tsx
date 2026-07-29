'use client'

import { forwardRef, useState, useImperativeHandle, useRef } from 'react'
import { Check, X } from 'lucide-react'
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
    // ПРОСТО ПОЛЯ
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

    return (
      <div className="h-full flex flex-col overflow-y-auto pb-24 space-y-3">
        {/* ПОЛЕ ИМЯ */}
        <div className="bg-white/20 backdrop-blur-xl border border-white/20 rounded-2xl p-4">
          <input
            type="text"
            value={name}
            onChange={(e) => { setName(e.target.value); setSaved(false) }}
            placeholder="Ваше имя..."
            className="w-full bg-transparent text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:outline-none"
          />
        </div>

        {/* ТИП КОЖИ */}
        <div className="bg-white/20 backdrop-blur-xl border border-white/20 rounded-2xl p-4">
          <div className="flex flex-wrap gap-1.5">
            {SKIN_TYPES.map((t) => (
              <Chip key={t} label={t} active={skinType === t} onClick={() => { setSkinType(t); setSaved(false) }} />
            ))}
          </div>
        </div>

        {/* ВОЗРАСТ */}
        <div className="bg-white/20 backdrop-blur-xl border border-white/20 rounded-2xl p-4">
          <div className="flex flex-wrap gap-1.5">
            {AGE_GROUPS.map((a) => (
              <Chip key={a} label={a} active={age === a} onClick={() => { setAge(a); setSaved(false) }} />
            ))}
          </div>
        </div>

        {/* ПРОБЛЕМЫ */}
        <div className="bg-white/20 backdrop-blur-xl border border-white/20 rounded-2xl p-4">
          <div className="flex flex-wrap gap-1.5">
            {SKIN_CONCERNS.map((c) => (
              <Chip key={c} label={c} active={concerns.includes(c)} onClick={() => toggle('concerns', c)} />
            ))}
          </div>
        </div>

        {/* АЛЛЕРГИИ */}
        <div className="bg-white/20 backdrop-blur-xl border border-white/20 rounded-2xl p-4">
          <div className="flex flex-wrap gap-1.5">
            {ALLERGIES.map((a) => (
              <Chip key={a} label={a} active={allergies.includes(a)} onClick={() => toggle('allergies', a)} />
            ))}
          </div>
        </div>

        {/* ТЕКСТАРЯ */}
        <div className="bg-white/20 backdrop-blur-xl border border-white/20 rounded-2xl p-4">
          <textarea
            value={customText}
            onChange={(e) => { setCustomText(e.target.value); setSaved(false) }}
            placeholder="Опишите проблему..."
            className="w-full bg-transparent text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:outline-none resize-none"
            rows={2}
          />
        </div>

        {/* КНОПКИ */}
        {!isEmpty && (
          <div className="flex gap-2">
            <button
              onClick={() => setShowReset(true)}
              className="px-4 py-2.5 rounded-xl border border-red-200/50 text-xs text-red-400"
            >
              Сбросить
            </button>
            <button
              onClick={handleSave}
              disabled={!hasChanges || saved}
              className={cn(
                'flex-1 px-6 py-2.5 rounded-xl text-xs font-medium transition-all',
                !hasChanges || saved
                  ? 'bg-white/10 text-muted-foreground/40 cursor-default'
                  : 'bg-primary/20 text-primary hover:bg-primary/30'
              )}
            >
              {saved ? '✅ Сохранено' : 'Сохранить'}
            </button>
          </div>
        )}

        {/* ПОПАП СБРОСА */}
        {showReset && (
          <>
            <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setShowReset(false)} />
            <div className="fixed left-1/2 top-1/2 z-50 w-80 -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white/90 backdrop-blur-xl border border-white/30 p-6">
              <h3 className="text-base font-light mb-2">Сбросить анкету?</h3>
              <p className="text-sm text-muted-foreground/70 mb-4">Данные будут удалены.</p>
              <div className="flex gap-2">
                <button onClick={() => setShowReset(false)} className="flex-1 px-4 py-2 rounded-xl border text-xs">Отмена</button>
                <button onClick={handleReset} className="flex-1 px-4 py-2 rounded-xl bg-red-500/20 text-red-400 text-xs">Сбросить</button>
              </div>
            </div>
          </>
        )}
      </div>
    )
  }
)

ProfileTab.displayName = 'ProfileTab'