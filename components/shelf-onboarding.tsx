'use client'

import { useEffect, useRef, useState } from 'react'
import { X, ChevronRight } from 'lucide-react'

export type OnboardingStepId = 'profile' | 'quiz' | 'shelf' | 'shelves'

type TourStep = {
  id: OnboardingStepId
  target: string
  title: string
  text: string
  cta: string
}

const STEPS: TourStep[] = [
  {
    id: 'profile',
    target: '[data-tour="profile"]',
    title: 'Сначала заполним ваш профиль',
    text: 'Откройте вкладку «Профиль» — там вы расскажете о своей коже и предпочтениях.',
    cta: 'Перейти в профиль',
  },
  {
    id: 'quiz',
    target: '[data-tour="quiz"]',
    title: 'Опишите вашу кожу',
    text: 'Заполните анкету: тип кожи, проблемы и предпочтения. Это сделает рекомендации персональными.',
    cta: 'Сохранить и продолжить',
  },
  {
    id: 'shelf',
    target: '[data-tour="shelf"]',
    title: 'Теперь — «Моя полка»',
    text: 'Здесь будет ваша постоянная коллекция ухода.',
    cta: 'Перейти к полке',
  },
  {
    id: 'shelves',
    target: '[data-tour="shelves"]',
    title: 'Ваши полки',
    text: 'Каждая полка соответствует категории. Добавляйте продукты, чтобы видеть их анализ и соответствие вашему профилю.',
    cta: 'Начать',
  },
]

export function ShelfOnboarding({
  step,
  onNext,
  onSkip,
  onGoToProfile,
  onGoToShelf,
  onProfileSaved,
}: {
  step: OnboardingStepId
  onNext: (next: OnboardingStepId) => void
  onSkip: () => void
  onGoToProfile: () => void
  onGoToShelf: () => void
  onProfileSaved: () => void
}) {
  const [rect, setRect] = useState<{ top: number; left: number; width: number; height: number } | null>(null)
  const [position, setPosition] = useState<'below' | 'above'>('below')
  const frameRef = useRef<number>(0)

  const current = STEPS.find((s) => s.id === step) || STEPS[0]
  const stepIndex = STEPS.findIndex((s) => s.id === step)

  useEffect(() => {
    const measure = () => {
      const el = document.querySelector(current.target)
      if (!el) {
        setRect(null)
        return
      }
      const r = el.getBoundingClientRect()
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height })
      setPosition(r.top < 240 ? 'below' : 'above')
    }
    measure()
    const onResize = () => {
      cancelAnimationFrame(frameRef.current)
      frameRef.current = requestAnimationFrame(measure)
    }
    const onScroll = () => {
      cancelAnimationFrame(frameRef.current)
      frameRef.current = requestAnimationFrame(measure)
    }
    window.addEventListener('resize', onResize)
    window.addEventListener('scroll', onScroll, { capture: true, passive: true })
    return () => {
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll, { capture: true } as EventListenerOptions)
      cancelAnimationFrame(frameRef.current)
    }
  }, [step, current.target])

  const handleCta = () => {
    if (step === 'profile') {
      onGoToProfile()
      onNext('quiz')
    } else if (step === 'quiz') {
      onProfileSaved()
      onNext('shelf')
    } else if (step === 'shelf') {
      onGoToShelf()
      onNext('shelves')
    } else {
      onSkip()
    }
  }

  return (
    <div className="fixed inset-0 z-[90]">
      <div className="absolute inset-0 bg-black/50" onClick={onSkip} />

      {rect && (
        <div
          className="absolute rounded-2xl ring-4 ring-white shadow-[0_0_0_9999px_rgba(0,0,0,0.55)]"
          style={{ top: rect.top - 4, left: rect.left - 4, width: rect.width + 8, height: rect.height + 8 }}
        />
      )}

      {rect && (
        <div
          className="absolute left-1/2 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 rounded-2xl bg-white p-4 shadow-2xl animate-modal-panel"
          style={
            position === 'below'
              ? { top: rect.top + rect.height + 12 }
              : { bottom: window.innerHeight - rect.top + 12 }
          }
        >
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] font-medium uppercase tracking-wider text-primary">
              Шаг {stepIndex + 1} из {STEPS.length}
            </span>
            <button onClick={onSkip} className="text-muted-foreground/60 hover:text-foreground" aria-label="Пропустить гид">
              <X className="size-4" />
            </button>
          </div>
          <h3 className="text-base font-normal text-foreground">{current.title}</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground/80">{current.text}</p>
          <div className="mt-3 flex items-center gap-2">
            <button onClick={onSkip} className="rounded-xl px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-gray-50">
              Пропустить
            </button>
            <button
              onClick={handleCta}
              className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-primary py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90"
            >
              {current.cta}
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
