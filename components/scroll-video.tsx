'use client'

import { useEffect, useRef } from 'react'

/**
 * ScrollVideo — видео, прогресс которого управляется скроллом.
 *
 * - при скролле вниз видео плавно «проигрывается» вперёд;
 * - при обратном скролле — назад;
 * - нет автовоспроизведения, прогресс привязан к положению блока на экране.
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

    let target = 0
    let current = 0
    let raf = 0

    const compute = () => {
      const rect = video.getBoundingClientRect()
      const vh = window.innerHeight || 1
      const total = Math.max(rect.height + vh, 1)
      const scrolled = vh - rect.top
      target = Math.min(1, Math.max(0, scrolled / total))
    }

    const tick = () => {
      // Плавная интерполяция к цели — без рывков.
      current += (target - current) * 0.09
      if (Math.abs(target - current) < 0.0005) current = target
      const dur = video.duration
      if (dur && isFinite(dur)) {
        const t = current * dur
        if (Math.abs(video.currentTime - t) > 0.02) video.currentTime = t
      }
      raf = requestAnimationFrame(tick)
    }

    compute()
    window.addEventListener('scroll', compute, { passive: true, capture: true })
    window.addEventListener('resize', compute)
    raf = requestAnimationFrame(tick)

    return () => {
      window.removeEventListener('scroll', compute, { capture: true } as EventListenerOptions)
      window.removeEventListener('resize', compute)
      cancelAnimationFrame(raf)
    }
  }, [])

  return <video ref={videoRef} src={src} muted playsInline preload="auto" className={className} aria-hidden />
}
