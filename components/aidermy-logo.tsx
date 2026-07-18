'use client'

interface AidermyLogoProps {
  isCompact?: boolean
}

export function AidermyLogo({ isCompact = false }: AidermyLogoProps) {
  return (
    <div className="logo-enter flex flex-col items-center transition-all duration-500">
      <span className="logo-shell">
        <span className="logo-metallic text-5xl font-black tracking-[0.12em] select-none">
          AIDERMY
        </span>
      </span>
      {!isCompact && (
        <span className="mt-1.5 text-[10px] font-medium uppercase tracking-[0.42em] text-primary/70">
          Помощник в уходе за твоей кожей
        </span>
      )}
    </div>
  )
}