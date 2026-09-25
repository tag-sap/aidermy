'use client'

import { Sparkles, LoaderCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

function scoreBadge(s: number) {
  if (s >= 80) return 'bg-[#F5C900]/20 text-[#7A5E00]'
  if (s >= 60) return 'bg-[#F5C900]/15 text-[#7A5E00]'
  if (s >= 40) return 'bg-[#8B5CF6]/10 text-[#6D28D9]'
  return 'bg-[#FF4D3D]/10 text-[#D63B2E]'
}

export function ProductCard({
  name,
  brand,
  imageUrl,
  category,
  score,
  checking = false,
  onOpen,
  className,
}: {
  name: string
  brand?: string
  imageUrl?: string
  category?: string
  score?: number | null
  checking?: boolean
  onOpen?: () => void
  className?: string
}) {

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
          <div className="relative flex aspect-[4/3] w-full items-center justify-center overflow-hidden bg-gray-50/60 p-2">
            {imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={imageUrl} alt="" className="h-full w-full object-contain" />
            ) : (
              <Sparkles className="size-6 text-muted-foreground/30" />
            )}
            {typeof score === 'number' && (
              <span
                className={cn(
                  'absolute left-1.5 top-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-none',
                  scoreBadge(score),
                )}
              >
                {score}%
              </span>
            )}
          </div>
          <div className="w-full min-w-0 px-3 pb-3 pt-2">
            {brand ? (
              <p className="truncate text-[10px] uppercase tracking-wide text-muted-foreground/50">{brand}</p>
            ) : null}
            <p className="line-clamp-2 text-sm font-medium leading-snug text-foreground/90">{name}</p>
            {category ? <p className="mt-0.5 truncate text-[11px] text-muted-foreground/50">{category}</p> : null}
          </div>
        </button>
      </div>

      {/* Overlay «На проверке» (только во время автоматической перепроверки полки) */}
      {checking && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-white/60">
          <LoaderCircle className="size-5 animate-spin text-primary" />
          <span className="text-xs font-medium text-foreground/70">На проверке</span>
        </div>
      )}
    </div>
  )
}
