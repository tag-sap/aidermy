'use client'

import { useEffect, useState } from 'react'
import { X, Sparkles, Clock, AlertCircle, CheckCircle, Info } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import type { CheckResult, SkinProfile } from '@/lib/store'
import { cn } from '@/lib/utils'

function ScoreRing({ score }: { score: number }) {
  const size = 120
  const stroke = 8
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const id = requestAnimationFrame(() => setProgress(score))
    return () => cancelAnimationFrame(id)
  }, [score])

  const offset = circumference - (progress / 100) * circumference

  const getColors = (s: number) => {
    if (s >= 80) {
      return {
        ring: '#6C3CE1',
        glow: 'rgba(108, 60, 225, 0.3)',
        text: '#6C3CE1',
      }
    } else if (s >= 60) {
      return {
        ring: '#8B5CF6',
        glow: 'rgba(139, 92, 246, 0.3)',
        text: '#8B5CF6',
      }
    } else if (s >= 40) {
      return {
        ring: '#A78BFA',
        glow: 'rgba(167, 139, 250, 0.3)',
        text: '#A78BFA',
      }
    } else {
      return {
        ring: '#C4B5FD',
        glow: 'rgba(196, 181, 253, 0.3)',
        text: '#C4B5FD',
      }
    }
  }

  const colors = getColors(score)

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(108, 60, 225, 0.08)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colors.ring}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{
            transition: 'stroke-dashoffset 1.2s cubic-bezier(0.16, 1, 0.3, 1)',
            filter: `drop-shadow(0 0 16px ${colors.glow})`,
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-light" style={{ color: colors.text }}>
          {score}%
        </span>
        <span className="text-[9px] text-muted-foreground/40 font-light tracking-wider">
          совместимость
        </span>
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

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => setIsVisible(true), 10)
      return () => clearTimeout(timer)
    } else {
      setIsVisible(false)
      setProductNameInput('')
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
            .replace(/<good>/g, '<span style="color: #6C3CE1; font-weight: 500;">')
            .replace(/<bad>/g, '<span style="color: #EF4444; font-weight: 500;">')
            .replace(/<\/good>/g, '</span>')
            .replace(/<\/bad>/g, '</span>')
        }}
      />
    )
  }

  const Section = ({ icon: Icon, title, children, className }: any) => (
    <div className={cn(
      'rounded-2xl p-3.5 border transition-all duration-300',
      'bg-white/40 backdrop-blur-md border-white/40',
      'hover:bg-white/60 hover:border-primary/20',
      'shadow-[0_4px_16px_rgba(108,60,225,0.04)]',
      className
    )}>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="size-4 text-primary/60" strokeWidth={1.5} />
        <h4 className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
          {title}
        </h4>
      </div>
      {children}
    </div>
  )

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-400',
        isVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'
      )}
      style={{ backgroundColor: 'rgba(0,0,0,0.15)' }}
    >
      <button
        type="button"
        aria-label="Закрыть"
        onClick={handleClose}
        className="absolute inset-0"
      />

      <div
        className={cn(
          'relative w-full max-w-md p-5 transition-all duration-400 max-h-[90vh] overflow-y-auto',
          isVisible ? 'scale-100 opacity-100' : 'scale-95 opacity-0'
        )}
        style={{
          transform: isVisible ? 'scale(1) translateY(0)' : 'scale(0.95) translateY(10px)',
          opacity: isVisible ? 1 : 0,
          // Прямоугольная трапеция: верхний левый угол торчит вверх
          clipPath: 'polygon(0% 8%, 100% 0%, 100% 100%, 0% 100%)',
          borderRadius: '20px 20px 16px 16px',
          background: 'rgba(255, 255, 255, 0.6)',
          backdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.4)',
          boxShadow: '0 8px 40px rgba(108, 60, 225, 0.08), inset 0 1px 0 rgba(255,255,255,0.6)',
        }}
        role="dialog"
        aria-modal="true"
      >
        <button
          type="button"
          onClick={handleClose}
          aria-label="Закрыть"
          className="absolute right-3 top-3 text-foreground/30 transition-colors hover:text-foreground/60 z-10"
        >
          <X className="size-4.5" />
        </button>

        {loading ? (
          <div className="flex flex-col items-center gap-4 py-12">
            <div className="relative">
              <div className="size-12 rounded-full border-3 border-primary/20 border-t-primary animate-spin" />
              <div className="absolute inset-0 rounded-full border-3 border-primary/5 animate-pulse" />
            </div>
            <p className="text-xs text-muted-foreground/60 font-light">AI анализирует состав...</p>
          </div>
        ) : result ? (
          <div className="flex flex-col gap-3.5">
            {/* Заголовок */}
            <div className="text-center">
              <p className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground/40 font-light">
                Результат проверки
              </p>
              <ScrambleText
                as="h2"
                text={result.product}
                revealDelay={45}
                className="mt-1 block text-base font-light text-foreground"
              />
            </div>

            {/* Картинка + Скрор + Вердикт */}
            <div className="flex items-center gap-4">
              {result.image_url && (
                <div className="w-16 h-16 rounded-2xl overflow-hidden bg-white/40 flex items-center justify-center border border-white/30 flex-shrink-0 backdrop-blur-sm">
                  <img
                    src={result.image_url}
                    alt={result.product}
                    className="w-full h-full object-contain p-1.5"
                  />
                </div>
              )}
              <div className="flex-1 flex items-center gap-3">
                <ScoreRing score={result.score} />
                <div className="flex-1">
                  <p className={cn(
                    'text-sm font-medium',
                    result.score >= 70 ? 'text-primary' :
                      result.score >= 40 ? 'text-primary/70' : 'text-muted-foreground'
                  )}>
                    {result.verdict}
                  </p>
                  <p className="text-[10px] text-muted-foreground/40 font-light mt-0.5">
                    на основе состава
                  </p>
                </div>
              </div>
            </div>

            {/* Резюме */}
            {result.summary && (
              <Section icon={Info} title="Резюме" className="border-primary/10">
                <p className="text-xs text-foreground/70 leading-relaxed font-light">
                  {renderWithColors(result.summary)}
                </p>
              </Section>
            )}

            {/* Активный ингредиент */}
            {result.active_ingredients && (
              <Section icon={Sparkles} title="Активный ингредиент" className="border-purple-100/50">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-medium text-foreground/80">
                    {result.active_ingredients.name}
                  </span>
                  <span className="text-[9px] px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                    #{result.active_ingredients.position}
                  </span>
                  <span className={cn(
                    'text-[9px] px-2 py-0.5 rounded-full',
                    result.active_ingredients.concentration === 'высокая' && 'bg-primary/10 text-primary',
                    result.active_ingredients.concentration === 'средняя' && 'bg-primary/5 text-primary/70',
                    result.active_ingredients.concentration === 'низкая' && 'bg-gray-100 text-muted-foreground',
                  )}>
                    {result.active_ingredients.concentration}
                  </span>
                </div>
                <p className="text-[10px] text-muted-foreground/50 font-light mt-1">
                  Эффективность: {result.active_ingredients.effectiveness}
                </p>
              </Section>
            )}

            {/* Как применять */}
            {result.how_to_use && (
              <Section icon={Clock} title="Как применять" className="border-blue-100/50">
                <div className="space-y-0.5 text-xs text-foreground/70 font-light">
                  <p><span className="font-medium text-foreground/80">Нанесение:</span> {result.how_to_use.application}</p>
                  <p><span className="font-medium text-foreground/80">Время:</span> {result.how_to_use.time}</p>
                  {result.how_to_use.note && (
                    <p className="text-[10px] text-muted-foreground/60 mt-1">
                      {renderWithColors(result.how_to_use.note)}
                    </p>
                  )}
                </div>
              </Section>
            )}

            {/* Чего ожидать */}
            {result.expectations && (
              <Section icon={AlertCircle} title="Чего ожидать" className="border-amber-100/50">
                <div className="space-y-1 text-xs text-foreground/70 font-light">
                  <p><span className="font-medium text-foreground/80">Когда:</span> {result.expectations.when}</p>
                  <p className="text-[10px] flex items-start gap-1.5">
                    <CheckCircle className="size-3 text-primary/60 mt-0.5 flex-shrink-0" />
                    <span>{renderWithColors(result.expectations.normal)}</span>
                  </p>
                  <p className="text-[10px] flex items-start gap-1.5">
                    <AlertCircle className="size-3 text-red-400/60 mt-0.5 flex-shrink-0" />
                    <span>{renderWithColors(result.expectations.danger)}</span>
                  </p>
                </div>
              </Section>
            )}

            {/* Ингредиенты */}
            <div className="grid grid-cols-2 gap-2">
              {result.safe_ingredients && result.safe_ingredients.length > 0 && (
                <Section icon={CheckCircle} title="Безопасные" className="border-green-100/50 col-span-1">
                  <div className="flex flex-wrap gap-1">
                    {result.safe_ingredients.slice(0, 4).map((ing) => (
                      <span key={ing} className="text-[9px] px-2 py-0.5 bg-primary/5 text-primary/70 rounded-full">
                        {ing}
                      </span>
                    ))}
                    {result.safe_ingredients.length > 4 && (
                      <span className="text-[9px] text-muted-foreground/40">+{result.safe_ingredients.length - 4}</span>
                    )}
                  </div>
                </Section>
              )}

              {result.caution_ingredients && result.caution_ingredients.length > 0 && (
                <Section icon={AlertCircle} title="С осторожностью" className="border-red-100/50 col-span-1">
                  <div className="flex flex-wrap gap-1">
                    {result.caution_ingredients.slice(0, 4).map((ing) => (
                      <span key={ing} className="text-[9px] px-2 py-0.5 bg-red-50 text-red-500 rounded-full">
                        {ing}
                      </span>
                    ))}
                    {result.caution_ingredients.length > 4 && (
                      <span className="text-[9px] text-muted-foreground/40">+{result.caution_ingredients.length - 4}</span>
                    )}
                  </div>
                </Section>
              )}
            </div>

            {/* Ввод состава */}
            {showIngredientsInput && (
              <div className="rounded-2xl bg-white/40 backdrop-blur-md p-3.5 border border-white/40">
                <p className="text-[10px] text-muted-foreground/60 font-light mb-2">
                  Уточните состав продукта (INCI)
                </p>
                <input
                  type="text"
                  value={productNameInput}
                  onChange={(e) => setProductNameInput(e.target.value)}
                  placeholder="Название продукта"
                  className="w-full rounded-xl bg-white/40 border border-white/30 px-3 py-2 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all backdrop-blur-sm"
                />
                <textarea
                  value={ingredientsInput}
                  onChange={(e) => setIngredientsInput(e.target.value)}
                  placeholder="Aqua, Glycerin, Cetearyl Alcohol..."
                  className="w-full rounded-xl bg-white/40 border border-white/30 px-3 py-2 mt-1.5 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all backdrop-blur-sm resize-none"
                  rows={2}
                />
                <button
                  onClick={handleCheckWithIngredients}
                  disabled={!ingredientsInput.trim() || isCheckingIngredients}
                  className="w-full rounded-xl bg-primary/15 text-primary text-xs font-medium py-2 mt-2 transition-all hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed backdrop-blur-sm"
                >
                  {isCheckingIngredients ? 'Анализируем...' : 'Проверить состав →'}
                </button>
              </div>
            )}

            {/* Кнопки */}
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 rounded-xl border border-gray-200/50 py-2.5 text-xs font-medium text-muted-foreground transition-all hover:bg-gray-50/50"
              >
                Закрыть
              </button>
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 rounded-xl bg-primary/15 text-primary text-xs font-medium py-2.5 transition-all hover:bg-primary/25"
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