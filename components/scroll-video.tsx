'use client'

import { useEffect, useRef } from 'react'

/**
 * ScrollVideo — видео, прогресс которого управляется скроллом.
 *
 * Позиция блока пересчитывается каждый кадр (requestAnimationFrame),
 * поэтому реагирует на скролл сразу, без задержек, в любом скролл-контейнере.
 */
export function ScrollVideo({ src, className }: { src: string; className?: string }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    video.muted = true
    video.playsInline = true
    video.pause()
    if (video.readyState >= 1) video.currentTime = 0

    let current = 0
    let raf = 0

    const tick = () => {
      // Читаем актуальную позицию каждый кадр — никакой зависимости от событий scroll.
      const rect = video.getBoundingClientRect()
      const vh = window.innerHeight || 1
      const total = Math.max(rect.height + vh, 1)
      const scrolled = vh - rect.top
      const target = Math.min(1, Math.max(0, scrolled / total))

      // Быстрая, но плавная интерполяция — без ощущения отставания.
      current += (target - current) * 0.25
      if (Math.abs(target - current) < 0.0005) current = target

      const dur = video.duration
      if (dur && isFinite(dur)) {
        const t = current * dur
        if (Math.abs(video.currentTime - t) > 0.03) video.currentTime = t
      }
      raf = requestAnimationFrame(tick)
    }

    raf = requestAnimationFrame(tick)

    return () => cancelAnimationFrame(raf)
  }, [])

  return <video ref={videoRef} src={src} muted playsInline preload="auto" className={className} aria-hidden />
}
