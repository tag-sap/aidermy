'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

interface AnimatedTabIconProps {
  frames: string[]
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
 */
export function AnimatedTabIcon({ frames, active, hovered, className }: AnimatedTabIconProps) {
  const [frame, setFrame] = useState(0)
  const [bounce, setBounce] = useState(false)
  const timerRef = useRef<number>(0)
  const frameRef = useRef(0)
  const prevActiveRef = useRef(active)

  const last = Math.max(frames.length - 1, 0)

  const stop = useCallback(() => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current)
      timerRef.current = 0
    }
  }, [])

  const apply = useCallback((idx: number) => {
    frameRef.current = idx
    setFrame(idx)
  }, [])

  const play = useCallback(
    (toLast: boolean) => {
      stop()
      const target = toLast ? last : 0
      if (frameRef.current === target) return
      const step = () => {
        const next = frameRef.current + (toLast ? 1 : -1)
        if (toLast ? next >= target : next <= target) {
          apply(target)
          return
        }
        apply(next)
        timerRef.current = window.setTimeout(step, FRAME_MS)
      }
      step()
    },
    [last, apply, stop]
  )

  // Инициализация: активная вкладка сразу на последнем кадре.
  useEffect(() => {
    apply(active ? last : 0)
    prevActiveRef.current = active
    return () => stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Hover (только desktop — hovered задаётся родителем по pointerenter для mouse).
  useEffect(() => {
    if (hovered) {
      if (frameRef.current < last) play(true)
    } else if (!active && frameRef.current > 0) {
      play(false)
    }
  }, [hovered, active, play, last])

  // Выбор вкладки (клик).
  useEffect(() => {
    const was = prevActiveRef.current
    prevActiveRef.current = active
    if (active && !was) {
      if (frameRef.current >= last) {
        // Уже на последнем кадре (hover довёл) — только bounce, без повтора кадров.
        setBounce(true)
        window.setTimeout(() => setBounce(false), 560)
      } else {
        play(true)
      }
    } else if (!active && was) {
      // Предыдущая вкладка возвращается в исходное состояние.
      stop()
      apply(0)
    }
  }, [active, play, apply, last, stop])

  return (
    <img
      src={frames[Math.min(frame, last)] ?? frames[0]}
      alt=""
      aria-hidden="true"
      draggable={false}
      className={cn(className ?? 'block w-full', bounce && 'tab-icon-bounce')}
      style={{ imageRendering: 'pixelated' }}
    />
  )
}
