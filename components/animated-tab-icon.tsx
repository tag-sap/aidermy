'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { decodeGif, type DecodedGif } from '@/lib/gif'

interface AnimatedTabIconProps {
  idleSrc: string
  gifSrc: string
  active: boolean
  hovered: boolean
  className?: string
}

type Direction = 1 | -1 | 0

const ANIMATION_SPEED = 3

/**
 * Иконка вкладки с одноразовой GIF-анимацией (вперёд/назад).
 *
 * - `idleSrc` — обычное состояние (PNG).
 * - `gifSrc` — анимация перехода в активное состояние (GIF, проигрывается
 *   один раз вперёд, а при уходе/деактивации — назад).
 * - `active` — вкладка активна (держим последний кадр).
 * - `hovered` — курсор над вкладкой (desktop, задаётся родителем).
 */
export function AnimatedTabIcon({ idleSrc, gifSrc, active, hovered, className }: AnimatedTabIconProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const offscreenRef = useRef<HTMLCanvasElement | null>(null)
  const idleImgRef = useRef<HTMLImageElement | null>(null)
  const gifRef = useRef<DecodedGif | null>(null)
  const animRef = useRef<{ frame: number; direction: Direction; timer: number }>({
    frame: -1,
    direction: 0,
    timer: 0,
  })
  const initializedRef = useRef(false)
  const [ready, setReady] = useState(false)

  // Загружаем idle-PNG и декодируем GIF один раз.
  useEffect(() => {
    let cancelled = false

    const loadImage = (src: string) =>
      new Promise<HTMLImageElement>((resolve, reject) => {
        const img = new Image()
        img.onload = () => resolve(img)
        img.onerror = reject
        img.src = src
      })

    Promise.all([loadImage(idleSrc), decodeGif(gifSrc)])
      .then(([idleImg, gif]) => {
        if (cancelled) return
        idleImgRef.current = idleImg
        gifRef.current = gif
        setReady(true)
      })
      .catch(() => {
        // Если декодирование не удалось — оставляем кнопку рабочей без анимации.
      })

    return () => {
      cancelled = true
    }
  }, [idleSrc, gifSrc])

  const drawIdle = useCallback(() => {
    const canvas = canvasRef.current
    const img = idleImgRef.current
    const gif = gifRef.current
    if (!canvas || !img || !gif) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const { bbox } = gif
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, bbox.left, bbox.top, bbox.width, bbox.height, 0, 0, canvas.width, canvas.height)
  }, [])

  const drawFrame = useCallback((index: number) => {
    const canvas = canvasRef.current
    const gif = gifRef.current
    if (!canvas || !gif || index < 0 || index >= gif.frames.length) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Кадр рисуем на полноразмерный offscreen-canvas, а затем кадрируем через
    // drawImage (надёжнее, чем putImageData с dirty-rect).
    let off = offscreenRef.current
    if (!off) {
      off = document.createElement('canvas')
      off.width = gif.width
      off.height = gif.height
      offscreenRef.current = off
    }
    const offCtx = off.getContext('2d')
    if (!offCtx) return
    offCtx.putImageData(gif.frames[index].imageData, 0, 0)

    const { bbox } = gif
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(off, bbox.left, bbox.top, bbox.width, bbox.height, 0, 0, canvas.width, canvas.height)
  }, [])

  const stopAnim = useCallback(() => {
    if (animRef.current.timer) {
      window.clearTimeout(animRef.current.timer)
      animRef.current.timer = 0
    }
    animRef.current.direction = 0
  }, [])

  const play = useCallback(
    (direction: 1 | -1) => {
      const gif = gifRef.current
      if (!gif || gif.frames.length === 0) return
      stopAnim()
      animRef.current.direction = direction
      const step = () => {
        const a = animRef.current
        if (a.direction !== direction) return
        const g = gifRef.current
        if (!g) return
        const next = a.frame + direction
        if (direction === 1 && next >= g.frames.length) {
          a.frame = g.frames.length - 1
          a.direction = 0
          drawFrame(a.frame)
          return
        }
        if (direction === -1 && next < 0) {
          a.frame = -1
          a.direction = 0
          drawIdle()
          return
        }
        a.frame = next
        drawFrame(next)
        a.timer = window.setTimeout(step, g.frames[next].delayMs / ANIMATION_SPEED)
      }
      step()
    },
    [drawIdle, drawFrame, stopAnim]
  )

  // Устанавливаем размер canvas и рисуем начальное состояние.
  useEffect(() => {
    if (!ready) return
    const gif = gifRef.current
    const canvas = canvasRef.current
    if (!gif || !canvas) return

    canvas.width = gif.bbox.width
    canvas.height = gif.bbox.height
    canvas.style.aspectRatio = `${gif.bbox.width} / ${gif.bbox.height}`

    if (!initializedRef.current) {
      initializedRef.current = true
      if (active) {
        animRef.current.frame = gif.frames.length - 1
        drawFrame(gif.frames.length - 1)
      } else {
        drawIdle()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready])

  // Реакция на смену цели (active / hover).
  const targetHeld = active || hovered

  useEffect(() => {
    if (!ready || !initializedRef.current) return
    const gif = gifRef.current
    if (!gif || gif.frames.length === 0) return
    const a = animRef.current

    if (targetHeld) {
      if (a.direction === 1 || a.frame === gif.frames.length - 1) return
      play(1)
    } else {
      if (a.direction === -1 || a.frame === -1) return
      play(-1)
    }
  }, [ready, targetHeld, active, play])

  // Очистка таймера при размонтировании.
  useEffect(() => {
    return () => {
      if (animRef.current.timer) window.clearTimeout(animRef.current.timer)
    }
  }, [])

  return <canvas ref={canvasRef} className={className ?? 'block w-full'} aria-hidden="true" />
}
