'use client'

import { useEffect, useState } from 'react'
import { X, Sparkles, Clock, AlertCircle, CheckCircle, LoaderCircle } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import { MarkupText } from '@/components/markup-text'
import type { CheckResult, GoalEvidence, SkinProfile } from '@/lib/store'
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
    if (s >= 80) return { ring: '#D6F264', glow: 'rgba(214,242,100,0.35)', text: '#4a5d00' }
    if (s >= 60) return { ring: '#C9E84F', glow: 'rgba(214,242,100,0.3)', text: '#4a5d00' }
    if (s >= 40) return { ring: '#151515', glow: 'rgba(21,21,21,0.2)', text: '#151515' }
    return { ring: '#151515', glow: 'rgba(21,21,21,0.12)', text: '#151515' }
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

const GOAL_VERDICT_LABELS = {
  supports: 'Поддерживает',
  neutral: 'Нейтрально',
  may_hinder: 'Может мешать',
  insufficient_data: 'Недостаточно данных',
} as const

function evidenceNames(item: GoalEvidence, verdict: GoalEvidence['evidence'][number]['verdict']) {
  return [...new Set(item.evidence.filter((evidence) => evidence.verdict === verdict).map((evidence) => evidence.ingredient))]
}

function fragmentsToText(value: unknown): string | null {
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      if (Array.isArray(parsed)) return fragmentsToText(parsed)
    } catch {
      return value || null
    }
    return value || null
  }
  if (Array.isArray(value)) {
    const text = value
      .map((item) => (typeof item === 'string' ? item : item && typeof item === 'object' && 'text' in item ? String(item.text || '') : ''))
      .filter(Boolean)
      .join(' ')
    return text || null
  }
  return null
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
  const [reportModalOpen, setReportModalOpen] = useState(false)

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
            structured: profile.structured || null,
          },
          ingredients: ingredientsInput,
        }),
      })
      if (!response.ok) throw new Error(`Ошибка: ${response.status}`)
      const data = await response.json()
      onResultUpdate({
        ...data,
        analysis_id: data.analysis_id ?? null,
        slug: data.slug || result.slug,
        product: productNameInput.trim() || result.product,
        skinType: result.skinType || profile.skinType,
        createdAt: Date.now(),
      })
      setProductNameInput('')
      setIngredientsInput('')
    } catch (error) { console.error('Ошибка проверки с составом:', error) }
    finally { setIsCheckingIngredients(false) }
  }

  // Генерация подробного описания (Слой 2). LLM объясняет уже готовый результат,
  // НЕ пересчитывает процент и НЕ меняет verdict.
  const handleGetDetails = async () => {
    if ((!result?.slug && !result?.analysis_id) || gettingDetails) return
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
        body: JSON.stringify({ slug: result.slug || '', analysis_id: result.analysis_id ?? null }),
      })
      const d = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(d.detail || 'Не удалось подготовить подробный анализ')
      onResultUpdate({
        ...result,
        score: typeof d.score === 'number' ? d.score : result.score,
        verdict: typeof d.verdict === 'string' ? d.verdict : result.verdict,
        report: fragmentsToText(d.review) ?? result.report,
        report_ready: d.report_ready === true,
        expectations: d.expectations ?? result.expectations,
      })
      if (d.report_ready === true) setReportModalOpen(true)
    } catch {
      setDetailsError('Не удалось подготовить подробный анализ')
    } finally {
      setGettingDetails(false)
    }
  }

  if (!isOpen) return null

  const showIngredientsInput = result?.summary?.includes("НЕИЗВЕСТНЫЙ СОСТАВ")
  const reportReady = Boolean(result?.report_ready || (result?.report && result.report !== result.summary))


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
      <div className={cn('relative flex max-h-[calc(100dvh-1.5rem)] w-[calc(100vw-1.5rem)] max-w-md md:max-w-3xl flex-col overflow-hidden transition-all duration-300', isVisible ? 'scale-100 opacity-100' : 'scale-95 opacity-0')} style={{
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
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-gray-100/60 px-4 pt-4 pb-3 md:px-6 md:pt-5">
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
          <button type="button" aria-label="Закрыть отчёт" onClick={handleClose} className="shrink-0 rounded-md p-1 text-foreground/40 transition-colors hover:bg-gray-100 hover:text-foreground/70"><X className="size-5" /></button>
        </div>

        {loading ? (
          <div className="flex flex-col items-center gap-3 py-10">
            <div className="relative"><div className="size-12 rounded-full border-4 border-primary/20 border-t-primary animate-spin" /><div className="absolute inset-0 rounded-full border-4 border-primary/5 animate-pulse" /></div>
            <p className="text-sm text-muted-foreground/70 font-light">Анализируем состав…</p>
            <p className="max-w-[280px] text-center text-xs leading-relaxed text-muted-foreground/50 font-light">Уточняем данные по ингредиентам, чтобы расчёт был точнее</p>
          </div>
        ) : result ? (
          <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 md:px-6 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <div className="flex flex-col gap-3">

            <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-center">
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                {result.image_url && <div className="hidden size-14 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-gray-100 bg-white/60 sm:flex"><img src={result.image_url} alt={result.product} className="h-full w-full object-contain p-1" /></div>}
                {typeof result.score === 'number' ? (
                  <ScoreRing score={result.score} />
                ) : (
                  <div className="flex size-[124px] shrink-0 flex-col items-center justify-center rounded-full border border-gray-200 text-muted-foreground/50">
                    <span className="text-2xl font-light">—</span>
                    <span className="text-[10px] font-light">нет оценки</span>
                  </div>
                )}
                <div className="min-w-0">
                  <p className={cn('text-base font-medium', typeof result.score === 'number' && result.score >= 70 ? 'text-primary' : typeof result.score === 'number' && result.score >= 40 ? 'text-primary/70' : 'text-muted-foreground')}>{result.verdict}</p>
                  <p className="text-xs text-muted-foreground/50 font-light">
                    {typeof result.score === 'number' ? 'SCORE · VERDICT' : 'оценка пока недоступна'}
                  </p>
                </div>
              </div>
            </div>

            {!reportReady && result.goal_evidence && result.goal_evidence.length > 0 && (
              <Section icon={Sparkles} title="Под ваши задачи" className="border-primary/10">
                <p className="mb-2 text-[11px] text-muted-foreground/60">
                  По доступным данным о свойствах ингредиентов; это не оценка клинической эффективности.
                </p>
                <div className="space-y-2">
                  {result.goal_evidence.map((item) => (
                    <div key={item.concern_id} className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
                      <span className="min-w-0 break-words text-sm text-foreground/80">{item.label}</span>
                      <span className="shrink-0 text-xs font-medium text-foreground/65">
                        {GOAL_VERDICT_LABELS[item.verdict]}
                      </span>
                      {(['supports', 'may_hinder', 'neutral'] as const).map((evidenceVerdict) => {
                        const names = evidenceNames(item, evidenceVerdict)
                        if (!names.length) return null
                        const visibleNames = names.slice(0, 5)
                        const label = evidenceVerdict === 'supports'
                          ? 'Факторы в пользу'
                          : evidenceVerdict === 'may_hinder'
                            ? 'Возможные препятствия'
                            : 'Нейтральные данные'
                        return (
                          <span key={evidenceVerdict} className="min-w-0 break-words text-[11px] text-muted-foreground/60 sm:basis-full">
                            {label}: {visibleNames.join(', ')}{names.length > visibleNames.length ? ` и ещё ${names.length - visibleNames.length}` : ''}
                          </span>
                        )
                      })}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <>
              <Section icon={Sparkles} title="Результат" className="border-primary/10">
                <p className="text-sm text-foreground/80 leading-relaxed font-light">{result.summary}</p>
              </Section>

              {reportReady && result.report && (
                <div className="hidden md:block animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <Section icon={Sparkles} title="Почему такой результат" className="border-primary/10 p-6">
                    <p className="text-xl leading-[1.75] text-foreground/90 font-light">
                      <MarkupText text={result.report} />
                    </p>
                  </Section>
                </div>
              )}

              {reportReady && result.expectations && (
                <div className="hidden md:block animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <Section icon={AlertCircle} title="Чего ожидать" className="border-amber-100/50 p-5">
                    <div className="space-y-2 text-base leading-relaxed text-foreground/80 font-light">
                      {result.expectations.when && (
                        <p>
                          <span className="font-medium text-foreground/80">Когда:</span>{' '}
                          {result.expectations.when}
                        </p>
                      )}
                      {result.expectations.normal && (
                        <p className="flex items-start gap-2">
                          <CheckCircle className="size-4 text-primary/60 mt-1 flex-shrink-0" />
                          <span><MarkupText text={result.expectations.normal} /></span>
                        </p>
                      )}
                      {result.expectations.danger && (
                        <p className="flex items-start gap-2">
                          <AlertCircle className="size-4 text-red-400/60 mt-1 flex-shrink-0" />
                          <span><MarkupText text={result.expectations.danger} /></span>
                        </p>
                      )}
                    </div>
                  </Section>
                </div>
              )}
            </>


            {showIngredientsInput && (
              <div className="rounded-xl bg-white/60 backdrop-blur-md p-3 border border-gray-100">
                <p className="text-xs text-muted-foreground/70 font-light mb-1.5">Уточните состав продукта (INCI)</p>
                <input type="text" value={productNameInput} onChange={(e) => setProductNameInput(e.target.value)} placeholder="Название продукта" className="w-full rounded-lg bg-white/70 border border-gray-200 px-3 py-2 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all" />
                <textarea value={ingredientsInput} onChange={(e) => setIngredientsInput(e.target.value)} placeholder="Aqua, Glycerin..." className="w-full rounded-lg bg-white/70 border border-gray-200 px-3 py-2 mt-1.5 text-sm text-foreground/80 placeholder:text-muted-foreground/40 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/10 transition-all resize-none" rows={2} />
                <button onClick={handleCheckWithIngredients} disabled={!ingredientsInput.trim() || isCheckingIngredients} className="w-full rounded-lg bg-primary/15 text-primary text-sm font-medium py-2 mt-1.5 transition-all hover:bg-primary/25 disabled:opacity-40 disabled:cursor-not-allowed">{isCheckingIngredients ? 'Анализируем...' : 'Проверить состав →'}</button>
              </div>
            )}

            <div className="flex gap-2 pt-0.5">
              {typeof result.score === 'number' && !reportReady ? (
                <div className="flex flex-1 flex-col gap-2">
                  {detailsError && <p className="text-center text-xs text-red-500">{detailsError}</p>}
                  <button
                    type="button"
                    onClick={handleGetDetails}
                    disabled={gettingDetails || (!result.slug && !result.analysis_id)}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-50"
                  >
                    {gettingDetails ? (
                      <>
                        <LoaderCircle className="size-4 animate-spin" />
                        Готовим отчёт...
                      </>
                    ) : detailsError ? 'Повторить' : 'Посмотреть отчёт'}
                  </button>
                </div>
              ) : null}
              <button onClick={handleClose} className="flex-1 rounded-lg border border-gray-200/60 py-2.5 text-sm font-medium text-muted-foreground transition-all hover:bg-gray-50">Закрыть</button>
            </div>
            </div>
          </div>
        ) : null}
      </div>

      {reportModalOpen && reportReady && result.report && (
        <div className="absolute inset-0 z-[95] flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop md:hidden" onClick={() => setReportModalOpen(false)}>
          <div
            className="flex max-h-[80dvh] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-white/50 bg-white/75 p-4 backdrop-blur-xl animate-modal-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex shrink-0 items-center justify-between">
              <h2 className="text-base font-normal text-foreground">Почему такой результат</h2>
              <button type="button" onClick={() => setReportModalOpen(false)} className="relative z-10 shrink-0 text-muted-foreground hover:text-foreground" aria-label="Закрыть отчёт">
                <X className="size-4" />
              </button>
            </div>
            <div className="min-h-0 overflow-y-auto overflow-x-hidden pr-1">
              <p className="text-xl leading-[1.75] text-foreground/90 font-light">
                <MarkupText text={result.report} />
              </p>
              {result.expectations && (
                <div className="mt-5 border-t border-gray-200/60 pt-4">
                  <div className="mb-2 flex items-center gap-1.5">
                    <AlertCircle className="size-4 text-primary/60" strokeWidth={1.5} />
                    <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Чего ожидать</h4>
                  </div>
                  <div className="space-y-2 text-base leading-relaxed text-foreground/80 font-light">
                    {result.expectations.when && (
                      <p><span className="font-medium text-foreground/80">Когда:</span>{' '}{result.expectations.when}</p>
                    )}
                    {result.expectations.normal && (
                      <p className="flex items-start gap-2">
                        <CheckCircle className="size-4 text-primary/60 mt-1 flex-shrink-0" />
                        <span><MarkupText text={result.expectations.normal} /></span>
                      </p>
                    )}
                    {result.expectations.danger && (
                      <p className="flex items-start gap-2">
                        <AlertCircle className="size-4 text-red-400/60 mt-1 flex-shrink-0" />
                        <span><MarkupText text={result.expectations.danger} /></span>
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}