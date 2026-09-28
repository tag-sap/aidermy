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
      {/* Гифка с прозрачным фоном — показываем как есть, без дополнительной подложки */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/loading.gif" alt="Загрузка" className="h-auto w-40" />
    </div>
  )
}