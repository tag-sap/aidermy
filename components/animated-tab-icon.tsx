'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

interface AnimatedTabIconProps {
  frames: string[]
  idleSrc?: string
  active: boolean
  hovered: boolean
  className?: string
}

const FRAME_MS = 55

/**
 * Иконка вкладки из готовых storyboard-кадров (0..n-1) с pixel-art рендерингом.
 *
 * - Desktop hover: frame 0 → ... → последний; при уходе — назад к frame 0.
 * - Клик/выбор: если hover уже довёл до последнего кадра — только bounce (scale),
 *   без повторного проигрывания кадров.
 * - Mobile (hover нет): выбор вкладки проигрывает 0 → последний, без bounce.
 * - Переключение вкладки корректно возвращает предыдущую в frame 0.
 *
 * Анимация идёт по requestAnimationFrame с привязкой ко времени (без дрейфа
 * setTimeout и без накопления/пропуска кадров). Все кадры предзагружаются,
 * чтобы браузер не подгружал их на лету во время анимации.
 */
export function AnimatedTabIcon({ frames, idleSrc, active, hovered, className }: AnimatedTabIconProps) {
  const [frame, setFrame] = useState(0)
  const [bounce, setBounce] = useState(false)
  const rafRef = useRef<number>(0)
  const frameRef = useRef(0)
  const bounceTimerRef = useRef<number>(0)
  const prevActiveRef = useRef(active)

  const last = Math.max(frames.length - 1, 0)

  const cancelAnim = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = 0
    }
  }, [])

  const apply = useCallback((idx: number) => {
    frameRef.current = idx
    setFrame(idx)
  }, [])

  // Плавный переход из текущего кадра к target: один кадр за FRAME_MS.
  const playTo = useCallback(
    (target: number) => {
      cancelAnim()
      const from = frameRef.current
      if (from === target) return
      const start = performance.now()
      const step = (now: number) => {
        const steps = Math.floor((now - start) / FRAME_MS)
        const raw = target > from ? from + steps : from - steps
        const idx = target > from ? Math.min(raw, target) : Math.max(raw, target)
        if (idx !== frameRef.current) apply(idx)
        if (idx === target) return
        rafRef.current = requestAnimationFrame(step)
      }
      rafRef.current = requestAnimationFrame(step)
    },
    [cancelAnim, apply]
  )

  // Предзагрузка всех кадров + idle-картинки; повторяется при возврате на вкладку
  // (после долгого бездействия браузер может выгрузить изображения из памяти).
  useEffect(() => {
    const preload = () => {
      const urls = [...frames]
      if (idleSrc) urls.push(idleSrc)
      for (const u of urls) {
        const img = new Image()
        img.src = u
      }
    }
    preload()
    const onVisible = () => { if (document.visibilityState === 'visible') preload() }
    const onPageShow = () => preload()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('pageshow', onPageShow)
    window.addEventListener('focus', preload)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('pageshow', onPageShow)
      window.removeEventListener('focus', preload)
    }
  }, [frames, idleSrc])

  // Инициализация: активная вкладка сразу на последнем кадре.
  useEffect(() => {
    apply(active ? last : 0)
    prevActiveRef.current = active
    return () => {
      cancelAnim()
      if (bounceTimerRef.current) window.clearTimeout(bounceTimerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Hover (только desktop — hovered задаётся родителем по pointerenter для mouse).
  useEffect(() => {
    if (hovered) {
      if (frameRef.current < last) playTo(last)
    } else if (!active && frameRef.current > 0) {
      playTo(0)
    }
  }, [hovered, active, playTo, last])

  // Выбор вкладки (клик/тап).
  useEffect(() => {
    const was = prevActiveRef.current
    prevActiveRef.current = active
    if (active && !was) {
      // Bounce (scale-up) — на десктопе при клике даже если hover-анимация ещё не доиграла.
      if (hovered || frameRef.current >= last) {
        setBounce(true)
        if (bounceTimerRef.current) window.clearTimeout(bounceTimerRef.current)
        bounceTimerRef.current = window.setTimeout(() => setBounce(false), 560)
      }
      if (frameRef.current < last) playTo(last)
    } else if (!active && was) {
      // Предыдущая вкладка играет анимацию в обратную сторону (reverse).
      playTo(0)
    }
  }, [active, hovered, playTo, last])

  return (
    <img
      src={frame === 0 && idleSrc ? idleSrc : (frames[Math.min(frame, last)] ?? frames[0])}
      alt=""
      aria-hidden="true"
      draggable={false}
      className={cn(className ?? 'block w-full', bounce && 'tab-icon-bounce')}
      style={{
        imageRendering: 'pixelated',
        // Исходники 128×128 с пустыми 48px сверху и снизу — обрезаем до содержимого (128×32).
        aspectRatio: '4 / 1',
        objectFit: 'cover',
        objectPosition: 'center',
      }}
    />
  )
}
