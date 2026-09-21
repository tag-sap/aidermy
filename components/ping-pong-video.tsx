'use client'

import { useEffect, useRef } from 'react'

/**
 * PingPongVideo — видео, которое само плавно проигрывается вперёд и назад.
 *
 * Запускаем цикл сразу (не ждём canplay — из-за этого видео могло не стартовать),
 * шаг считаем по реальному прошедшему времени, чтобы скорость была одинаковой
 * на 60/120 Гц и вперёд/назад.
 */
export function PingPongVideo({ src, className }: { src: string; className?: string }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    video.muted = true
    video.playsInline = true
    video.loop = false
    video.pause()
    try {
      video.currentTime = 0
    } catch {
      /* ignore */
    }

    let direction = 1 // 1 — вперёд, -1 — назад
    let raf = 0
    let lastTs = 0

    const tick = (ts: number) => {
      const dur = video.duration
      if (dur && isFinite(dur) && video.readyState >= 1) {
        const delta = lastTs ? Math.min((ts - lastTs) / 1000, 0.1) : 0
        lastTs = ts
        let t = video.currentTime + direction * delta
        if (t >= dur - 0.05) {
          t = dur
          direction = -1
        } else if (t <= 0.05) {
          t = 0
          direction = 1
        }
        if (Math.abs(video.currentTime - t) > 0.02) {
          video.currentTime = t
        }
      }
      raf = requestAnimationFrame(tick)
    }

    raf = requestAnimationFrame(tick)

    return () => cancelAnimationFrame(raf)
  }, [])

  return <video ref={videoRef} src={src} muted playsInline preload="auto" className={className} aria-hidden />
}
