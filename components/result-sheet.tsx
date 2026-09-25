'use client'

import { useEffect, useState } from 'react'
import { X, Sparkles, Clock, AlertCircle, CheckCircle, FileText, LoaderCircle } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import { MarkupText } from '@/components/markup-text'
import type { CheckResult, SkinProfile } from '@/lib/store'
import { cn } from '@/lib/utils'
import { useScrollLock } from '@/lib/use-scroll-lock'

function ScoreRing({ score }: { score: number }) {
  const size = 124
  const stroke = 7
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const id = requestAnimationFrame(() => setProgress(score))
    return () => cancelAnimationFrame(id)
  }, [score])

  const offset = circumference - (progress / 100) * circumference

  const getColors = (s: number) => {
    if (s >= 80) return { ring: '#F5C900', glow: 'rgba(245,201,0,0.35)', text: '#7A5E00' }
    if (s >= 60) return { ring: '#E0B400', glow: 'rgba(245,201,0,0.3)', text: '#7A5E00' }
    if (s >= 40) return { ring: '#8B5CF6', glow: 'rgba(139,92,246,0.3)', text: '#6D28D9' }
    return { ring: '#FF4D3D', glow: 'rgba(255,77,61,0.3)', text: '#D63B2E' }
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
          stroke="rgba(108,60,225,0.08)"
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
            transition: 'stroke-dashoffset 1.2s cubic-bezier(0.16,1,0.3,1)',
            filter: `drop-shadow(0 0 16px ${colors.glow})`,
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-light" style={{ color: colors.text }}>{score}%</span>
        <span className="text-[10px] text-muted-foreground/50 font-light tracking-wider">совместимость</span>
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
  const [gettingDetails, setGettingDetails] = useState(false)
  const [detailsError, setDetailsError] = useState('')

  useScrollLock(isOpen)

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
    setTimeout(() => onClose(), 300)
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
      if (!response.ok) throw new Error(`Ошибка: ${response.status}`)
      const data = await response.json()
      onResultUpdate({ ...data, product: productNameInput.trim() || result.product, skinType: result.skinType || profile.skinType, createdAt: Date.now() })
      setProductNameInput('')
      setIngredientsInput('')
    } catch (error) { console.error('Ошибка проверки с составом:', error) }
    finally { setIsCheckingIngredients(false) }
  }

  // Генерация подробного описания (Слой 2). LLM объясняет уже готовый результат,
  // НЕ пересчитывает процент и НЕ меняет verdict.
  const handleGetDetails = async () => {
    if (!result?.slug || gettingDetails) return
    setGettingDetails(true)
    setDetailsError('')
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
      const res = await fetch('/api/analysis/report', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ slug: result.slug }),
      })
      const d = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(d.detail || 'Не удалось подготовить подробный анализ')
      onResultUpdate({ ...result, report: d.review ?? result.report })
    } catch {
      setDetailsError('Не удалось подготовить подробный анализ')
    } finally {
      setGettingDetails(false)
    }
  }

  if (!isOpen) return null

  const showIngredientsInput = result?.summary?.includes("НЕИЗВЕСТНЫЙ СОСТАВ")


  const Section = ({ icon: Icon, title, children, className, onClick }: any) => (
    <div onClick={onClick} className={cn('rounded-xl p-3 border transition-all duration-300 bg-white/60 backdrop-blur-md border-gray-100/60 hover:border-primary/20 shadow-[0_4px_16px_rgba(108,60,225,0.04)]', onClick && 'cursor-pointer', className)}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <Icon className="size-4 text-primary/60" strokeWidth={1.5} />
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{title}</h4>
      </div>
      {children}
    </div>
  )

  return (
    <div className={cn('fixed inset-0 z-[90] flex items-center justify-center p-3 transition-opacity duration-300', isVisible ? 'opacity-100' : 'opacity-0 pointer-events-none')} style={{ backgroundColor: 'rgba(0,0,0,0.15)', transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)' }}>
      <button type="button" onClick={handleClose} className="absolute inset-0" />
      <div className={cn('relative flex max-h-[90dvh] w-full max-w-md md:max-w-3xl flex-col overflow-hidden transition-all duration-300', isVisible ? 'scale-100 opacity-100' : 'scale-95 opacity-0')} style={{
        transform: isVisible ? 'scale(1) translateY(0)' : 'scale(0.96) translateY(14px)',
        transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)',
        opacity: isVisible ? 1 : 0,
        borderRadius: '20px',
        background: 'rgba(255,255,255,0.9)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.5)',
        boxShadow: '0 8px 40px rgba(108,60,225,0.10)'
      }}>
        {/* Sticky-заголовок с крестиком — доступен при прокрутке. */}
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-gray-100/60 px-5 pt-5 pb-3 md:px-6">
          {loading ? (
            <p className="text-sm text-muted-foreground/70 font-light">Анализируем состав…</p>
          ) : result ? (
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.15em] text-muted-foreground/50 font-light">Результат проверки</p>
              <ScrambleText as="h2" text={result.product} revealDelay={45} className="mt-0.5 block text-base md:text-lg font-light text-foreground" />
            </div>
          ) : (
            <span />
          )}
          <button type="button" onClick={handleClose} className="shrink-0 rounded-md p-1 text-foreground/40 transition-colors hover:bg-gray-100 hover:text-foreground/70"><X className="size-5" /></button>
        </div>

        {loading ? (
          <div className="flex flex-col items-center gap-3 py-10">
            <div className="relative"><div className="size-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin" /><div className="absolute inset-0 rounded-full border-4 border-primary/5 animate-pulse" /></div>
            <p className="text-sm text-muted-foreground/70 font-light">Анализируем состав…</p>
            <p className="max-w-[280px] text-center text-xs leading-relaxed text-muted-foreground/50 font-light">Уточняем данные по ингредиентам, чтобы расчёт был точнее</p>
          </div>
        ) : result ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 md:px-6 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <div className="flex flex-col gap-3">

            <div className="flex flex-col sm:flex-row sm:items-center gap-4">
              <div className="flex items-center gap-3">
                {result.image_url && <div className="w-14 h-14 rounded-xl overflow-hidden bg-white/60 flex items-center justify-center border border-gray-100 flex-shrink-0"><img src={result.image_url} alt={result.product} className="w-full h-full object-contain p-1" /></div>}
                <ScoreRing score={result.score} />
                <div>
                  <p className={cn('text-base font-medium', result.score >= 70 ? 'text-primary' : result.score >= 40 ? 'text-primary/70' : 'text-muted-foreground')}>{result.verdict}</p>
                  <p className="text-xs text-muted-foreground/50 font-light">на основе состава</p>
                </div>
              </div>
            </div>

            {result.report ? (
              <>
                <Section icon={Sparkles} title="Общий вывод" className="border-primary/10">
                  <p className="text-sm text-foreground/80 leading-relaxed font-light"><MarkupText text={result.report} /></p>
                </Section>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {result.active_ingredients && (
                    <Section icon={Sparkles} title="Ключевой ингредиент" className="border-purple-100/50">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-sm font-medium text-foreground/80">{result.active_ingredients.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">#{result.active_ingredients.position}</span>
                      </div>
                      <p className="text-xs text-muted-foreground/60 font-light mt-1">
                        Значимый для вашего анализа компонент
                      </p>
                    </Section>
                  )}

                  {result.how_to_use && (
                    <Section icon={Clock} title="Как применять" className="border-blue-100/50">
                      <div className="space-y-0.5 text-xs text-foreground/70 font-light">
                        <p><span className="font-medium text-foreground/80">Нанесение:</span> {result.how_to_use.application}</p>
                        <p><span className="font-medium text-foreground/80">Время:</span> {result.how_to_use.time}</p>
                        {result.how_to_use.note && <p className="text-[11px] text-muted-foreground/60 mt-0.5"><MarkupText text={result.how_to_use.note} /></p>}
                      </div>
                    </Section>
                  )}

                  {result.expectations && (
                    <Section icon={AlertCircle} title="Чего ожидать" className="border-amber-100/50">
                      <div className="space-y-0.5 text-xs text-foreground/70 font-light">
                        <p><span className="font-medium text-foreground/80">Когда:</span> {result.expectations.when}</p>
                        <p className="text-[11px] flex items-start gap-1"><CheckCircle className="size-3.5 text-primary/60 mt-0.5 flex-shrink-0" /><span><MarkupText text={result.expectations.normal} /></span></p>
                        <p className="text-[11px] flex items-start gap-1"><AlertCircle className="size-3.5 text-red-400/60 mt-0.5 flex-shrink-0" /><span><MarkupText text={result.expectations.danger} /></span></p>
                      </div>
                    </Section>
                  )}
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center gap-2 py-2">
                {detailsError && <p className="text-center text-xs text-red-500">{detailsError}</p>}
                <button
                  onClick={handleGetDetails}
                  disabled={gettingDetails}
                  className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
                >
                  {gettingDetails ? (
                    <>
                      <LoaderCircle className="size-4 animate-spin" />
                      Готовим подробный анализ...
                    </>
                  ) : (
                    <>
                      <FileText className="size-4" />
                      Показать подробности
                    </>
                  )}
                </button>
              </div>
            )}


            {showIngredientsInput && (
              <div className="rounded-xl bg-white/60 backdrop-blur-md p-3 border border-gray-100">
                <p className="text-xs text-muted-foreground/70 font-light mb-1.5">Уточните состав продукта (INCI)</p>
                <input type="text" value={productNameInput} onChange={(e) => setProductNameInput(e.target.value)} placeholder="Название продукта" className="w-full rounded-lg bg-white/70 border border-gray-200 px-3 py-2 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all" />
                <textarea value={ingredientsInput} onChange={(e) => setIngredientsInput(e.target.value)} placeholder="Aqua, Glycerin..." className="w-full rounded-lg bg-white/70 border border-gray-200 px-3 py-2 mt-1.5 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all resize-none" rows={2} />
                <button onClick={handleCheckWithIngredients} disabled={!ingredientsInput.trim() || isCheckingIngredients} className="w-full rounded-lg bg-primary/15 text-primary text-sm font-medium py-2 mt-1.5 transition-all hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed">{isCheckingIngredients ? 'Анализируем...' : 'Проверить состав →'}</button>
              </div>
            )}

            <div className="flex gap-2 pt-0.5">
              <button onClick={handleClose} className="flex-1 rounded-lg border border-gray-200/60 py-2.5 text-sm font-medium text-muted-foreground transition-all hover:bg-gray-50">Закрыть</button>
            </div>
            </div>
          </div>
        ) : null}
      </div>

    </div>
  )
}