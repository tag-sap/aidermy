'use client'

interface AidermyLogoProps {
  isCompact?: boolean
}

export function AidermyLogo({ isCompact = false }: AidermyLogoProps) {
  return (
    <div className={`logo-enter group flex flex-col items-center md:items-start transition-all duration-300 ${isCompact ? 'scale-75 origin-top-left' : ''
      }`}>
      <span>
        <span className={`font-[family-name:var(--font-playfair)] font-normal tracking-[0.04em] select-none ${isCompact ? 'text-2xl' : 'text-4xl'
          }`}>
          aidermy
        </span>
      </span>
      {!isCompact && (
        <span className="mt-1.5 text-[10px] font-normal tracking-[0.14em] text-primary/70 transition-all duration-300 md:opacity-0 md:group-hover:opacity-100">
          помощник в уходе за твоей кожей
        </span>
      )}
    </div>
  )
}