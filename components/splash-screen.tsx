'use client'

import { useEffect, useState } from 'react'
import { AidermyLogo } from './aidermy-logo'

export function SplashScreen() {
  const [isVisible, setIsVisible] = useState(true)
  const [fadeOut, setFadeOut] = useState(false)

  useEffect(() => {
    // Через 1.5 секунды начинаем исчезать
    const timer = setTimeout(() => {
      setFadeOut(true)
    }, 1500)

    // Через 2 секунды полностью убираем
    const hideTimer = setTimeout(() => {
      setIsVisible(false)
    }, 2000)

    return () => {
      clearTimeout(timer)
      clearTimeout(hideTimer)
    }
  }, [])

  if (!isVisible) return null

  return (
    <div
      className={`fixed inset-0 z-[999] flex flex-col items-center justify-center bg-[#FAF9F6] transition-opacity duration-500 ${
        fadeOut ? 'opacity-0' : 'opacity-100'
      }`}
    >
      <div className="animate-pulse">
        <AidermyLogo />
      </div>
      <p className="mt-4 text-sm text-muted-foreground animate-pulse">
        Загрузка...
      </p>
    </div>
  )
}