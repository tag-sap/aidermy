'use client'

import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import type { CheckResult, SkinProfile } from '@/lib/store'

function ScoreRing({ score }: { score: number }) {
  const size = 160
  const stroke = 12
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const id = requestAnimationFrame(() => setProgress(score))
    return () => cancelAnimationFrame(id)
  }, [score])

  const offset = circumference - (progress / 100) * circumference

  const ringColor = score >= 70 ? '#FF4F00' : score >= 40 ? '#FF7A3A' : '#CC3F00'
  const glowColor = score >= 70 ? 'rgba(255,79,0,0.4)' : 'rgba(255,122,58,0.4)'

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(0,0,0,0.06)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={ringColor}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            transition: 'stroke-dashoffset 1s cubic-bezier(0.16, 1, 0.3, 1)',
            filter: `drop-shadow(0 0 12px ${glowColor})`,
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-bold text-gray-900">{score}%</span>
        <span className="text-xs text-gray-500">совместимость</span>
      </div>
    </div>
  )
}

export function ResultSheet({
  isOpen,
  result,
  loading,
  onClose,
  profile,
  onResultUpdate,
}: {
  isOpen: boolean
  result: CheckResult | null
  loading: boolean
  onClose: () => void
  profile: SkinProfile
  onResultUpdate: (data: CheckResult) => void
}) {
  const [isVisible, setIsVisible] = useState(false)
  const [ingredientsInput, setIngredientsInput] = useState('')
  const [isCheckingIngredients, setIsCheckingIngredients] = useState(false)

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => setIsVisible(true), 10)
      return () => clearTimeout(timer)
    } else {
      setIsVisible(false)
      setIngredientsInput('')
    }
  }, [isOpen])

  const handleClose = () => {
    setIsVisible(false)
    setTimeout(() => {
      onClose()
    }, 300)
  }

  const handleCheckWithIngredients = async () => {
    if (!ingredientsInput.trim() || !result) return

    setIsCheckingIngredients(true)
    try {
      const response = await fetch('/api/check-with-ingredients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          product_name: result.product,
          skin_type: result.skinType || profile.skinType,
          profile: {
            name: profile.name || '',
            age: profile.age || '',
            concerns: profile.concerns || [],
            allergies: profile.allergies || [],
            custom_text: profile.customText || '',
          },
          ingredients: ingredientsInput,
        }),
      })

      if (!response.ok) {
        throw new Error(`Ошибка: ${response.status}`)
      }

      const data = await response.json()
      const fullResult = {
        ...data,
        product: result.product,
        skinType: result.skinType || profile.skinType,
        createdAt: Date.now(),
      }
      onResultUpdate(fullResult)
      setIngredientsInput('')
    } catch (error) {
      console.error('Ошибка проверки с составом:', error)
    } finally {
      setIsCheckingIngredients(false)
    }
  }

  if (!isOpen) return null

  const showIngredientsInput = result?.summary?.includes("НЕИЗВЕСТНЫЙ СОСТАВ") ||
    result?.summary?.toLowerCase().includes("не знаю") ||
    result?.summary?.toLowerCase().includes("неизвестный") ||
    (result?.safe_ingredients?.length === 0 && result?.caution_ingredients?.length === 0)

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-300 ${isVisible ? 'opacity-100' : 'opacity-0'
        }`}
      style={{ backgroundColor: 'rgba(0,0,0,0.4)' }}
    >
      <button
        type="button"
        aria-label="Закрыть"
        onClick={handleClose}
        className="absolute inset-0"
      />

      <div
        className={`relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl transition-all duration-300 ${isVisible ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
          }`}
        style={{
          transform: isVisible ? 'scale(1)' : 'scale(0.92)',
          opacity: isVisible ? 1 : 0,
        }}
        role="dialog"
        aria-modal="true"
      >
        <button
          type="button"
          onClick={handleClose}
          aria-label="Закрыть"
          className="absolute right-4 top-4 text-gray-400 transition-colors hover:text-gray-900"
        >
          <X className="size-5" />
        </button>

        {loading ? (
          <div className="flex flex-col items-center gap-5 py-10">
            <div
              className="size-16 rounded-full border-4 border-gray-200 border-t-orange-500"
              style={{ animation: 'spin-slow 0.8s linear infinite' }}
            />
            <p className="text-sm text-gray-500">AI анализирует состав…</p>
          </div>
        ) : result ? (
          <div className="flex flex-col items-center gap-5">
            <div className="text-center">
              <p className="text-xs uppercase tracking-widest text-gray-400">
                Результат проверки
              </p>
              <ScrambleText
                as="h2"
                text={result.product}
                revealDelay={45}
                className="mt-1 block text-2xl font-bold text-gray-900"
              />
            </div>

            <ScoreRing score={result.score} />

            <div className="w-full rounded-xl bg-orange-50/60 p-4 text-center border border-orange-200/50">
              <ScrambleText
                as="p"
                text={result.verdict}
                startDelay={200}
                revealDelay={40}
                className="block text-lg font-bold text-orange-600"
              />
              <ScrambleText
                as="p"
                text={result.summary}
                startDelay={400}
                speed={20}
                revealDelay={14}
                className="mt-2 block text-sm leading-relaxed text-gray-700"
              />
            </div>

            {showIngredientsInput && (
              <div className="w-full mt-2">
                <p className="text-sm text-gray-500">
                  AI не знает точный состав этого продукта. Введите его вручную:
                </p>
                <textarea
                  value={ingredientsInput}
                  onChange={(e) => setIngredientsInput(e.target.value)}
                  placeholder="Aqua, Glycerin, Cetearyl Alcohol..."
                  className="w-full rounded-md border border-gray-300 p-2 mt-2 text-sm focus:border-orange-500 focus:outline-none"
                  rows={2}
                />
                <button
                  onClick={handleCheckWithIngredients}
                  disabled={!ingredientsInput.trim() || isCheckingIngredients}
                  className="w-full rounded-md bg-primary py-2.5 mt-2 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                  {isCheckingIngredients ? 'Анализируем...' : 'Отправить состав'}
                </button>
              </div>
            )}

            <div className="flex w-full gap-3">
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 rounded-md border border-gray-200 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
              >
                Закрыть
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 rounded-md bg-primary py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90"
              >
                Сохранить
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}