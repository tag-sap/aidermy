'use client'

import { useEffect, useRef } from 'react'

/**
 * PingPongVideo — видео, которое само плавно проигрывается вперёд и назад
 * (пинг-понг), без управления скроллом.
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

    let raf = 0
    let direction = 1 // 1 — вперёд, -1 — назад

    const tick = () => {
      const dur = video.duration
      if (dur && isFinite(dur) && video.readyState >= 1) {
        let t = video.currentTime + direction * (1 / 60)
        if (t >= dur) {
          t = dur
          direction = -1
        } else if (t <= 0) {
          t = 0
          direction = 1
        }
        video.currentTime = t
      }
      raf = requestAnimationFrame(tick)
    }

    const start = () => {
      video.currentTime = 0
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(tick)
    }

    if (video.readyState >= 1) {
      start()
    } else {
      video.addEventListener('loadedmetadata', start, { once: true })
    }

    return () => {
      cancelAnimationFrame(raf)
      video.removeEventListener('loadedmetadata', start)
    }
  }, [])

  return <video ref={videoRef} src={src} muted playsInline preload="auto" className={className} aria-hidden />
}
