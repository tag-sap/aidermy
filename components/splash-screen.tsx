'use client'

import { useEffect, useState } from 'react'

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
      className={`fixed inset-0 z-[999] flex items-center justify-center bg-[#FAF9F6] transition-opacity duration-500 ${
        fadeOut ? 'opacity-0' : 'opacity-100'
      }`}
    >
      <div className="flex flex-col items-center gap-5">
        <div className="relative flex size-16 items-center justify-center">
          <div className="absolute inset-0 animate-spin rounded-full border-[3px] border-[#151515]/10 border-t-[#151515]" />
          <span className="font-[family-name:var(--font-playfair)] text-2xl leading-none text-[#151515]">
            a
          </span>
        </div>
        <span className="text-[11px] font-medium uppercase tracking-[0.25em] text-[#151515]/50">
          Загрузка
        </span>
      </div>
    </div>
  )
}