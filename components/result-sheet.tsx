'use client'

import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import type { CheckResult, SkinProfile } from '@/lib/store'
import { cn } from '@/lib/utils'

function ScoreRing({ score }: { score: number }) {
  const size = 140
  const stroke = 10
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const id = requestAnimationFrame(() => setProgress(score))
    return () => cancelAnimationFrame(id)
  }, [score])

  const offset = circumference - (progress / 100) * circumference

  const ringColor = score >= 70 ? '#2E7D32' : score >= 40 ? '#4CAF50' : '#1B5E20'
  const glowColor = score >= 70 ? 'rgba(46,125,50,0.4)' : 'rgba(76,175,80,0.4)'

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
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
        <span className="text-3xl font-normal text-gray-900">{score}%</span>
        <span className="text-[10px] text-gray-500">совместимость</span>
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
  const [productNameInput, setProductNameInput] = useState('')
  const [ingredientsInput, setIngredientsInput] = useState('')
  const [isCheckingIngredients, setIsCheckingIngredients] = useState(false)
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => setIsVisible(true), 10)
      return () => clearTimeout(timer)
    } else {
      setIsVisible(false)
      setProductNameInput('')
      setIngredientsInput('')
      setImageLoaded(false)
      setImageError(false)
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
          product_name: productNameInput.trim() || result.product,
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
        product: productNameInput.trim() || result.product,
        skinType: result.skinType || profile.skinType,
        createdAt: Date.now(),
      }
      onResultUpdate(fullResult)
      setProductNameInput('')
      setIngredientsInput('')
    } catch (error) {
      console.error('Ошибка проверки с составом:', error)
    } finally {
      setIsCheckingIngredients(false)
    }
  }

  if (!isOpen) return null

  const showIngredientsInput = result?.summary?.includes("НЕИЗВЕСТНЫЙ СОСТАВ")

  const renderWithColors = (text: string) => {
    if (!text) return null
    return (
      <span
        dangerouslySetInnerHTML={{
          __html: text
            .replace(/<good>/g, '<span style="color: #22c55e; font-weight: 500;">')
            .replace(/<bad>/g, '<span style="color: #ef4444; font-weight: 500;">')
            .replace(/<\/good>/g, '</span>')
            .replace(/<\/bad>/g, '</span>')
        }}
      />
    )
  }

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
        className={`relative w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl transition-all duration-300 max-h-[90vh] overflow-y-auto ${isVisible ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
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
          className="absolute right-3 top-3 text-gray-400 transition-colors hover:text-gray-900 z-10"
        >
          <X className="size-5" />
        </button>

        {loading ? (
          <div className="flex flex-col items-center gap-5 py-10">
            <div
              className="size-16 rounded-full border-4 border-gray-200 border-t-primary"
              style={{ animation: 'spin-slow 0.8s linear infinite' }}
            />
            <p className="text-sm text-gray-500">AI анализирует состав…</p>
          </div>
        ) : result ? (
          <div className="flex flex-col items-center gap-4">
            <div className="text-center">
              <p className="text-[10px] uppercase tracking-widest text-gray-400">
                Результат проверки
              </p>
              <ScrambleText
                as="h2"
                text={result.product}
                revealDelay={45}
                className="mt-1 block text-xl font-normal text-gray-900"
              />
            </div>

            {/* КАРТИНКА ПРОДУКТА */}
            {result.image_url && (
              <div className="w-full flex justify-center">
                <div className="w-32 h-32 rounded-xl overflow-hidden bg-gray-100 flex items-center justify-center border border-gray-200 flex-shrink-0">
                  <img
                    src={result.image_url}
                    alt={result.product}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none'
                    }}
                  />
                </div>
              </div>
            )}

            <ScoreRing score={result.score} />

            {/* Вердикт */}
            <div className="w-full rounded-xl bg-primary/10 p-3 text-center border border-primary/20">
              <ScrambleText
                as="p"
                text={result.verdict}
                startDelay={200}
                revealDelay={40}
                className="block text-base font-normal text-primary"
              />
            </div>

            {/* Резюме с цветами */}
            {result.summary && (
              <div className="w-full bg-gray-50 rounded-xl p-4 border border-gray-100">
                <h4 className="text-sm font-medium text-gray-700 mb-1">📋 Резюме</h4>
                <p className="text-sm text-gray-600 leading-relaxed">
                  {renderWithColors(result.summary)}
                </p>
              </div>
            )}

            {/* Активные ингредиенты */}
            {result.active_ingredients && (
              <div className="w-full bg-gray-50 rounded-xl p-4 border border-gray-100">
                <h4 className="text-sm font-medium text-gray-700 mb-2">🧪 Активный ингредиент</h4>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-gray-900">{result.active_ingredients.name}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                    #{result.active_ingredients.position} в составе
                  </span>
                  <span className={cn(
                    'text-xs px-2 py-0.5 rounded-full',
                    result.active_ingredients.concentration === 'высокая' && 'bg-green-100 text-green-700',
                    result.active_ingredients.concentration === 'средняя' && 'bg-yellow-100 text-yellow-700',
                    result.active_ingredients.concentration === 'низкая' && 'bg-red-100 text-red-700',
                  )}>
                    {result.active_ingredients.concentration}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  Эффективность: {result.active_ingredients.effectiveness}
                </p>
              </div>
            )}

            {/* Как применять */}
            {result.how_to_use && (
              <div className="w-full bg-blue-50 rounded-xl p-4 border border-blue-200">
                <h4 className="text-sm font-medium text-blue-700 mb-2">💡 Как применять</h4>
                <div className="space-y-1 text-sm text-blue-800">
                  <p><span className="font-medium">Нанесение:</span> {result.how_to_use.application}</p>
                  <p><span className="font-medium">Время:</span> {result.how_to_use.time}</p>
                  {result.how_to_use.note && (
                    <p className="text-blue-700 text-xs mt-1">
                      {renderWithColors(result.how_to_use.note)}
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Чего ожидать */}
            {result.expectations && (
              <div className="w-full bg-purple-50 rounded-xl p-4 border border-purple-200">
                <h4 className="text-sm font-medium text-purple-700 mb-2">⏳ Чего ожидать</h4>
                <div className="space-y-2 text-sm">
                  <p><span className="font-medium text-purple-800">Когда:</span> {result.expectations.when}</p>
                  <p className="text-purple-700 text-xs">
                    <span className="font-medium">🟢 Норма:</span> {renderWithColors(result.expectations.normal)}
                  </p>
                  <p className="text-purple-700 text-xs">
                    <span className="font-medium">🔴 Тревога:</span> {renderWithColors(result.expectations.danger)}
                  </p>
                </div>
              </div>
            )}

            {/* Безопасные ингредиенты */}
            {result.safe_ingredients && result.safe_ingredients.length > 0 && (
              <div className="w-full bg-green-50 rounded-xl p-4 border border-green-200">
                <h4 className="text-sm font-medium text-green-700 mb-2">✅ Безопасные ингредиенты</h4>
                <div className="flex flex-wrap gap-1.5">
                  {result.safe_ingredients.map((ing) => (
                    <span key={ing} className="px-2.5 py-1 bg-green-100 text-green-700 text-xs rounded-full border border-green-200">
                      {ing}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Осторожные ингредиенты */}
            {result.caution_ingredients && result.caution_ingredients.length > 0 && (
              <div className="w-full bg-red-50 rounded-xl p-4 border border-red-200">
                <h4 className="text-sm font-medium text-red-700 mb-2">⚠️ Требуют осторожности</h4>
                <div className="flex flex-wrap gap-1.5">
                  {result.caution_ingredients.map((ing) => (
                    <span key={ing} className="px-2.5 py-1 bg-red-100 text-red-700 text-xs rounded-full border border-red-200">
                      {ing}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {showIngredientsInput && (
              <div className="w-full">
                <p className="text-xs text-gray-500 mb-1">
                  Уточните название и введите состав (INCI):
                </p>
                <input
                  type="text"
                  value={productNameInput}
                  onChange={(e) => setProductNameInput(e.target.value)}
                  placeholder="Название продукта"
                  className="w-full rounded-md border border-gray-300 p-2 text-sm focus:border-primary focus:outline-none"
                />
                <textarea
                  value={ingredientsInput}
                  onChange={(e) => setIngredientsInput(e.target.value)}
                  placeholder="Aqua, Glycerin, Cetearyl Alcohol..."
                  className="w-full rounded-md border border-gray-300 p-2 mt-1 text-sm focus:border-primary focus:outline-none"
                  rows={2}
                />
                <button
                  onClick={handleCheckWithIngredients}
                  disabled={!ingredientsInput.trim() || isCheckingIngredients}
                  className="w-full rounded-md bg-primary py-2 mt-2 text-sm font-normal text-white transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                  {isCheckingIngredients ? 'Анализируем...' : 'Отправить'}
                </button>
              </div>
            )}

            <div className="flex w-full gap-2 sticky bottom-0 bg-white pt-2">
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 rounded-md border border-gray-200 py-2 text-sm font-normal text-gray-600 transition-colors hover:bg-gray-50"
              >
                Закрыть
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 rounded-md bg-primary py-2 text-sm font-normal text-white transition-colors hover:bg-primary/90"
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