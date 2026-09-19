'use client'

import { useEffect, useRef } from 'react'

export function CursorGlow() {
  const glowRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!finePointer || reducedMotion) return

    const el = glowRef.current
    if (!el) return

    let mouseX = window.innerWidth / 2
    let mouseY = window.innerHeight / 2
    let glowX = mouseX
    let glowY = mouseY
    let raf = 0

    const animate = () => {
      glowX += (mouseX - glowX) * 0.09
      glowY += (mouseY - glowY) * 0.09
      el.style.transform = `translate3d(${glowX}px, ${glowY}px, 0) translate3d(-50%, -50%, 0)`
      raf = requestAnimationFrame(animate)
    }

    const onMove = (event: PointerEvent) => {
      mouseX = event.clientX
      mouseY = event.clientY

      const target = (event.target as Element | null)?.closest?.('.cta-btn') as HTMLElement | null
      if (target) {
        const rect = target.getBoundingClientRect()
        target.style.setProperty('--mouse-x', `${event.clientX - rect.left}px`)
        target.style.setProperty('--mouse-y', `${event.clientY - rect.top}px`)
      }
    }

    window.addEventListener('pointermove', onMove, { passive: true })
    raf = requestAnimationFrame(animate)

    return () => {
      window.removeEventListener('pointermove', onMove)
      cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <div
      ref={glowRef}
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-[35] h-[420px] w-[420px] rounded-full opacity-55 will-change-transform"
      style={{
        background:
          'radial-gradient(circle at 32% 28%, rgba(255, 186, 220, 0.5), transparent 42%), radial-gradient(circle at 70% 30%, rgba(180, 211, 255, 0.48), transparent 44%), radial-gradient(circle at 50% 70%, rgba(186, 232, 204, 0.48), transparent 48%)',
        filter: 'blur(38px)',
        transform: 'translate3d(-50%, -50%, 0)',
      }}
    />
  )
}
