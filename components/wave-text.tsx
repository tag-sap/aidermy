'use client'

import { useEffect, useState, useRef, type ElementType } from 'react'

export function WaveText({
  text,
  className,
  as: Tag = 'span',
  startDelay = 0,
}: {
  text: string
  className?: string
  as?: ElementType
  startDelay?: number
}) {
  const [show, setShow] = useState(false)
  const [opacity, setOpacity] = useState(0)
  const [waveActive, setWaveActive] = useState(false)
  const hasEverShown = useRef(false)

  // Вычисляем длительность волны: 2.2с + (количество букв × 0.06с)
  const getWaveDuration = () => {
    const chars = text.split('').filter((c) => c !== ' ').length
    return 2200 + chars * 60 // 60мс на букву
  }

  const startWave = () => {
    setWaveActive(true)
    const duration = getWaveDuration()
    setTimeout(() => {
      setWaveActive(false)
    }, duration)
  }

  // Плавное появление
  useEffect(() => {
    const timer = setTimeout(() => {
      setShow(true)
      const fadeTimer = setTimeout(() => {
        setOpacity(1)
      }, 50)

      if (!hasEverShown.current) {
        const waveTimer = setTimeout(() => {
          startWave()
          hasEverShown.current = true
        }, 600)
        return () => clearTimeout(waveTimer)
      }

      return () => clearTimeout(fadeTimer)
    }, startDelay)
    return () => clearTimeout(timer)
  }, [startDelay]) // eslint-disable-line react-hooks/exhaustive-deps

  // Периодический перезапуск волны каждые 14 секунд
  useEffect(() => {
    if (!show || !hasEverShown.current) return
    const interval = setInterval(() => {
      startWave()
    }, 14000) // 14 секунд (волна ~3.5с + пауза ~10с)
    return () => clearInterval(interval)
  }, [show]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!show) return null

  return (
    <Tag
      className={className}
      aria-label={text}
      style={{
        opacity,
        transition: 'opacity 0.5s ease-out',
      }}
    >
      {text.split('').map((char, index) => {
        if (char === ' ') {
          return <span key={index} className="inline-block w-[0.3em]">&nbsp;</span>
        }
        return (
          <span
            key={index}
            className={`inline-block transition-all duration-300 ${
              waveActive ? 'animate-wave-once' : ''
            }`}
            style={{
              animationDelay: waveActive ? `${index * 0.06}s` : '0s',
              animationFillMode: 'both',
            }}
          >
            {char}
          </span>
        )
      })}
    </Tag>
  )
}