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
  const frameRef = useRef<number>(0)

  const current = STEPS.find((s) => s.id === step) || STEPS[0]
  const stepIndex = STEPS.findIndex((s) => s.id === step)

  useEffect(() => {
    let raf = 0
    let timeout = 0

    const measure = () => {
      const el = document.querySelector(current.target)
      if (!el) {
        setRect(null)
        return
      }
      const r = el.getBoundingClientRect()
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height })
    }

    // Двойной RAF + таймаут, чтобы дождаться окончания layout после смены шага/вкладки.
    raf = requestAnimationFrame(() => {
      raf = requestAnimationFrame(measure)
    })
    timeout = window.setTimeout(measure, 300)

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
      cancelAnimationFrame(raf)
      cancelAnimationFrame(frameRef.current)
      clearTimeout(timeout)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll, { capture: true } as EventListenerOptions)
    }
  }, [step, current.target])

  // Клик по подсвеченной цели (например, по вкладке) — авто-переход на следующий шаг.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const el = (e.target as Element | null)?.closest?.(current.target)
      if (!el) return
      if (step === 'profile') {
        onGoToProfile()
        onNext('quiz')
      } else if (step === 'shelf') {
        onGoToShelf()
        onNext('shelves')
      }
    }
    document.addEventListener('click', onClick, { capture: true })
    return () => document.removeEventListener('click', onClick, { capture: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Для высокой цели показываем подсказку сверху, чтобы не перекрывать нижние кнопки
  // (например, «Сохранить» в профиле). Для компактной цели — снизу, если она в верхней части.
  const isTall = rect ? rect.height > window.innerHeight * 0.55 : false
  const placeBelow = rect ? (!isTall && rect.top < window.innerHeight * 0.55) : true

  return (
    <div className="pointer-events-none fixed inset-0 z-[90]">
      {rect ? (
        <>
          {/* Spotlight: 4 затемнённых прямоугольника вокруг цели — блокируют клики,
              оставляя саму цель кликабельной и подсвеченной. */}
          <div className="pointer-events-auto absolute bg-black/60" style={{ top: 0, left: 0, right: 0, height: Math.max(rect.top, 0) }} />
          <div className="pointer-events-auto absolute bg-black/60" style={{ top: rect.top + rect.height, left: 0, right: 0, bottom: 0 }} />
          <div className="pointer-events-auto absolute bg-black/60" style={{ top: rect.top, left: 0, width: Math.max(rect.left, 0), height: rect.height }} />
          <div className="pointer-events-auto absolute bg-black/60" style={{ top: rect.top, left: rect.left + rect.width, right: 0, height: rect.height }} />
          {/* Кольцо подсветки цели */}
          <div
            className="pointer-events-none absolute rounded-xl ring-4 ring-white"
            style={{ top: rect.top - 4, left: rect.left - 4, width: rect.width + 8, height: rect.height + 8 }}
          />
        </>
      ) : (
        <div className="pointer-events-auto absolute inset-0 bg-black/60" />
      )}

      <div
        className="pointer-events-auto absolute left-1/2 z-10 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 rounded-2xl bg-white p-3.5 shadow-2xl animate-modal-panel"
        style={
          rect
            ? placeBelow
              ? { top: Math.min(rect.top + rect.height + 12, window.innerHeight - 200) }
              : { bottom: Math.max(window.innerHeight - rect.top + 12, 12) }
            : { top: '50%', transform: 'translate(-50%, -50%)' }
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
        <h3 className="text-sm font-medium text-foreground">{current.title}</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground/80">{current.text}</p>
        <div className="mt-2.5 flex items-center gap-2">
          <button onClick={onSkip} className="shrink-0 rounded-lg px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-gray-50">
            Пропустить
          </button>
          <button
            onClick={handleCta}
            className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-primary py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {current.cta}
            <ChevronRight className="size-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
