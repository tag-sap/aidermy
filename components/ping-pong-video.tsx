'use client'

import { useEffect, useRef } from 'react'

/**
 * PingPongVideo — видео, которое само плавно проигрывается вперёд и назад.
 *
 * Ручной шаг currentTime, но с двумя ключевыми исправлениями:
 * - дожидаемся canplay (достаточно данных), чтобы не зависать на первом кадре;
 * - шаг считаем по реальному прошедшему времени (delta), а не «кадр = 1/60»,
 *   поэтому скорость одинакова на 60 Гц и 120 Гц мониторах.
 */
export function PingPongVideo({ src, className }: { src: string; className?: string }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    video.muted = true
    video.playsInline = true
    video.loop = false
    video.preload = 'auto'

    let direction = 1 // 1 — вперёд, -1 — назад
    let raf = 0
    let lastTs = 0
    let started = false

    const tick = (ts: number) => {
      const dur = video.duration
      if (dur && isFinite(dur) && video.readyState >= 2) {
        const delta = lastTs ? Math.min((ts - lastTs) / 1000, 0.1) : 1 / 30
        lastTs = ts
        let t = video.currentTime + direction * delta
        if (t >= dur - 0.001) {
          t = dur
          direction = -1
        } else if (t <= 0.001) {
          t = 0
          direction = 1
        }
        if (Math.abs(video.currentTime - t) > 0.02) {
          video.currentTime = t
        }
      }
      raf = requestAnimationFrame(tick)
    }

    const start = () => {
      if (started) return
      started = true
      video.currentTime = 0
      lastTs = 0
      raf = requestAnimationFrame(tick)
    }

    if (video.readyState >= 2) {
      start()
    } else {
      video.addEventListener('canplay', start, { once: true })
      video.load()
    }

    return () => {
      cancelAnimationFrame(raf)
      video.removeEventListener('canplay', start)
    }
  }, [])

  return <video ref={videoRef} src={src} muted playsInline preload="auto" className={className} aria-hidden />
}
