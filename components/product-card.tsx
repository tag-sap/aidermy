'use client'

import { Sparkles, LoaderCircle, ShieldCheck, FileText, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

export type ProductCardState = 'NOT_ANALYZED' | 'NO_REPORT' | 'HAS_REPORT'

export function deriveCardState(score: number | null | undefined, hasReport: boolean): ProductCardState {
  if (typeof score !== 'number') return 'NOT_ANALYZED'
  return hasReport ? 'HAS_REPORT' : 'NO_REPORT'
}

function scoreColor(s: number) {
  if (s >= 80) return 'text-[#7A5E00]'
  if (s >= 60) return 'text-[#7A5E00]'
  if (s >= 40) return 'text-[#6D28D9]'
  return 'text-[#D63B2E]'
}

export function ProductCard({
  name,
  brand,
  imageUrl,
  category,
  score,
  hasReport = false,
  checking = false,
  scoring = true,
  error,
  onOpen,
  onCheck,
  onGetDescription,
  onViewAnalysis,
  onRetry,
  className,
}: {
  name: string
  brand?: string
  imageUrl?: string
  category?: string
  score: number | null
  hasReport?: boolean
  checking?: boolean
  scoring?: boolean
  error?: string
  onOpen?: () => void
  onCheck?: () => void
  onGetDescription?: () => void
  onViewAnalysis?: () => void
  onRetry?: () => void
  className?: string
}) {
  const state = deriveCardState(score, hasReport)

  return (
    <div
      className={cn(
        'relative flex w-full min-w-0 flex-col overflow-hidden rounded-2xl border border-gray-100 bg-white text-left',
        className,
      )}
    >
      {/* Контент (размывается во время перепроверки) */}
      <div className={cn('flex w-full min-w-0 flex-1 flex-col', checking && 'blur-[2px]')}>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full min-w-0 flex-col text-left focus:outline-none"
        aria-label={name}
      >
        <div className="flex aspect-[4/3] w-full items-center justify-center overflow-hidden bg-gray-50/60 p-2">
          {imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={imageUrl} alt="" className="h-full w-full object-contain" />
          ) : (
            <Sparkles className="size-6 text-muted-foreground/30" />
          )}
        </div>
        <div className="w-full min-w-0 px-3 pt-2">
          {brand ? (
            <p className="truncate text-[10px] uppercase tracking-wide text-muted-foreground/50">{brand}</p>
          ) : null}
          <p className="line-clamp-2 text-sm font-medium leading-snug text-foreground/90">{name}</p>
          {category ? <p className="mt-0.5 truncate text-[11px] text-muted-foreground/50">{category}</p> : null}
        </div>
      </button>

      {/* Состояние персонального анализа */}
      {scoring && (
      <div className="mt-auto w-full px-3 pb-3 pt-2">
        {error ? (
          <div className="flex flex-col items-center gap-1.5 rounded-xl border border-red-100 bg-red-50/60 px-2 py-3 text-center">
            <AlertCircle className="size-4 text-red-500" />
            <p className="text-[11px] leading-snug text-red-500">{error}</p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="rounded-lg border border-red-200 px-2.5 py-1 text-[11px] font-medium text-red-500 transition-colors hover:bg-red-50"
              >
                Повторить
              </button>
            )}
          </div>
        ) : state === 'NOT_ANALYZED' ? (
          <div className="flex flex-col gap-2">
            <p className="text-center text-[11px] leading-snug text-muted-foreground/60">Анализ ещё не выполнен</p>
            {onCheck && (
              <button
                type="button"
                onClick={onCheck}
                className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-primary/30 bg-primary/5 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
              >
                <ShieldCheck className="size-3.5" />
                Проверить совместимость
              </button>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="text-center">
              <span className={cn('text-2xl font-light leading-none', scoreColor(score ?? 0))}>{score}%</span>
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground/60">Совместимость с вашей кожей</p>
            </div>
            {state === 'NO_REPORT' && onGetDescription ? (
              <button
                type="button"
                onClick={onGetDescription}
                className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-primary/30 bg-primary/5 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
              >
                <FileText className="size-3.5" />
                Получить описание
              </button>
            ) : state === 'HAS_REPORT' && onViewAnalysis ? (
              <button
                type="button"
                onClick={onViewAnalysis}
                className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary py-2 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                <ShieldCheck className="size-3.5" />
                Посмотреть анализ
              </button>
            ) : null}
          </div>
        )}
      </div>
      )}
      </div>

      {/* Overlay «Проверяем...» */}
      {checking && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-white/60">
          <LoaderCircle className="size-5 animate-spin text-primary" />
          <span className="text-xs font-medium text-foreground/70">Проверяем...</span>
        </div>
      )}
    </div>
  )
}
