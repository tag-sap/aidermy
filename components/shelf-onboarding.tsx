'use client'

import { useState } from 'react'
import { X, ChevronLeft, ChevronRight, UserRound, PackagePlus, Wand2, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useScrollLock } from '@/lib/use-scroll-lock'

interface ShelfOnboardingProps {
  onClose: () => void
  onGoToProfile: () => void
}

const STEPS = [
  {
    icon: UserRound,
    title: 'Уточните информацию о коже',
    text: 'Дополните данные о типе кожи, проблемах и аллергиях — так персональный анализ будет точнее.',
    cta: 'Заполнить профиль',
    action: 'profile' as const,
  },
  {
    icon: PackagePlus,
    title: 'Наполняйте полку',
    text: 'Добавляйте любимую косметику и смотрите, насколько каждое средство подходит вашей коже.',
    cta: 'Далее',
    action: 'next' as const,
  },
  {
    icon: Wand2,
    title: 'Не знаете, что поставить?',
    text: 'Воспользуйтесь автоподбором — система подберёт средства, подходящие именно вам.',
    cta: 'Начать',
    action: 'done' as const,
  },
]

export function ShelfOnboarding({ onClose, onGoToProfile }: ShelfOnboardingProps) {
  const [step, setStep] = useState(0)
  const current = STEPS[step]
  const Icon = current.icon

  useScrollLock(true)

  const handleCta = () => {
    if (current.action === 'profile') {
      onGoToProfile()
    } else if (current.action === 'next') {
      setStep((s) => s + 1)
    } else {
      onClose()
    }
  }

  const handleNext = () => setStep((s) => Math.min(s + 1, STEPS.length - 1))
  const handleBack = () => setStep((s) => Math.max(s - 1, 0))

  return (
    <div className="fixed inset-0 z-[85] flex items-end justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop sm:items-center" onClick={onClose}>
      <div className="w-full max-w-sm rounded-3xl bg-white p-5 shadow-2xl animate-modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <span className="inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-primary">
            <Sparkles className="size-3.5" />
            Знакомство с полкой
          </span>
          <button onClick={onClose} className="text-muted-foreground/60 hover:text-foreground" aria-label="Закрыть">
            <X className="size-4" />
          </button>
        </div>

        {/* прогресс */}
        <div className="mb-4 flex gap-1">
          {STEPS.map((_, i) => (
            <div key={i} className={cn('h-1 flex-1 rounded-full transition-colors', i <= step ? 'bg-primary' : 'bg-gray-200')} />
          ))}
        </div>

        {/* контент шага */}
        <div className="flex flex-col items-center text-center">
          <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Icon className="size-7" strokeWidth={1.75} />
          </div>
          <h3 className="mt-3 text-lg font-normal text-foreground">{current.title}</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground/80">{current.text}</p>
        </div>

        {/* кнопки */}
        <div className="mt-5 flex items-center gap-2">
          {step > 0 ? (
            <button
              onClick={handleBack}
              className="flex items-center justify-center gap-1 rounded-xl border border-gray-200 px-4 py-2.5 text-sm text-foreground/70 transition-colors hover:bg-gray-50"
            >
              <ChevronLeft className="size-4" />
              Назад
            </button>
          ) : (
            <button
              onClick={onClose}
              className="rounded-xl border border-gray-200 px-4 py-2.5 text-sm text-foreground/70 transition-colors hover:bg-gray-50"
            >
              Пропустить
            </button>
          )}

          <button
            onClick={handleCta}
            className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90"
          >
            {current.cta}
            {current.action === 'next' && <ChevronRight className="size-4" />}
          </button>
        </div>

        {/* подсказка по шагам */}
        {step < STEPS.length - 1 && current.action !== 'profile' && (
          <button onClick={handleNext} className="mt-3 w-full text-center text-xs text-muted-foreground/50 hover:text-primary">
            Пропустить шаг
          </button>
        )}
      </div>
    </div>
  )
}
