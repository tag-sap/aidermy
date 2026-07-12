'use client'

import { useEffect, useState, type ElementType } from 'react'

export function ScrambleText({
  text,
  className,
  as: Tag = 'span',
  startDelay = 0,
  revealDelay = 40,
  speed = 40,
}: {
  text: string
  className?: string
  as?: ElementType
  startDelay?: number
  revealDelay?: number
  speed?: number
}) {
  const [opacity, setOpacity] = useState(0)

  useEffect(() => {
    const timer = setTimeout(() => {
      setOpacity(1)
    }, startDelay)

    return () => {
      clearTimeout(timer)
    }
  }, [startDelay])

  return (
    <Tag
      className={className}
      aria-label={text}
      style={{
        opacity,
        transition: 'opacity 0.6s ease-out',
        display: 'inline-block',
      }}
    >
      {text}
    </Tag>
  )
}