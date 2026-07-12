'use client'

import { cn } from '@/lib/utils'

export function Chip({
  label,
  active = false,
  variant = 'default',
  onClick,
}: {
  label: string
  active?: boolean
  variant?: 'default' | 'gold-outline'
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-md border px-3.5 py-1.5 text-sm font-medium transition-all duration-200',
        'hover:bg-primary/5 active:bg-primary/10',
        active
          ? 'border-primary bg-primary/10 text-primary shadow-[0_0_20px_rgba(255,79,0,0.15)]'
          : variant === 'gold-outline'
            ? 'border-primary/30 bg-transparent text-foreground hover:border-primary'
            : 'border-border/50 bg-transparent text-foreground hover:border-primary/40',
      )}
    >
      {label}
    </button>
  )
}