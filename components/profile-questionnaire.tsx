'use client'

import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ProcedureItem, StructuredProfile, TherapyItem } from '@/lib/store'
import {
  ACID_OPTIONS,
  AGE_OPTIONS,
  CONCERN_CARDS,
  INTOLERANCE_OPTIONS,
  PROCEDURE_OPTIONS,
  PROCEDURE_PERIODS,
  RETINOID_OPTIONS,
  SKIN_TYPE_OPTIONS,
  THERAPY_OPTIONS,
  structuredToQuizState,
} from '@/lib/profile-questionnaire'

interface Props {
  initial?: StructuredProfile | null
  onSave: (structured: StructuredProfile) => void
  onCancel?: () => void
}

export function ProfileQuestionnaire({ initial, onSave, onCancel }: Props) {
  const init = useMemo(() => structuredToQuizState(initial), [initial])
  const [skinType, setSkinType] = useState<string | null>(init.skinType)
  const [age, setAge] = useState<string | null>(init.age)
  const [selectedCards, setSelectedCards] = useState<string[]>(init.selectedCards)
  const [answers, setAnswers] = useState<Record<string, Record<string, string[]>>>(init.answers)
  const [therapyEnabled, setTherapyEnabled] = useState<boolean | null>(init.therapyEnabled)
  const [therapyIds, setTherapyIds] = useState<string[]>(init.therapyIds)
  const [retinoid, setRetinoid] = useState<string | null>(init.retinoid)
  const [acids, setAcids] = useState<string[]>(init.acids)
  const [procedures, setProcedures] = useState<Record<string, string>>(init.procedures)
  const [intolerances, setIntolerances] = useState<string[]>(init.intolerances)
  const allergies = initial?.allergies ?? []

  const toggleCard = (id: string) => {
    setSelectedCards(prev => {
      if (prev.includes(id)) {
        setAnswers(a => {
          const copy = { ...a }
          delete copy[id]
          return copy
        })
        return prev.filter(c => c !== id)
      }
      return [...prev, id]
    })
  }

  const toggleAnswer = (branchId: string, questionId: string, optionId: string) => {
    setAnswers(prev => {
      const q = prev[branchId]?.[questionId] ?? []
      const next = q.includes(optionId) ? q.filter(x => x !== optionId) : [...q, optionId]
      return { ...prev, [branchId]: { ...prev[branchId], [questionId]: next } }
    })
  }

  const toggleInList = (list: string[], set: (v: string[]) => void, id: string) =>
    set(list.includes(id) ? list.filter(x => x !== id) : [...list, id])

  const specificIds = useMemo(() => {
    const out: string[] = []
    for (const branch of CONCERN_CARDS) {
      for (const q of branch.questions) {
        for (const id of answers[branch.id]?.[q.id] ?? []) out.push(id)
      }
    }
    return out
  }, [answers])

  const therapyItems = useMemo<TherapyItem[]>(() => {
    const items: TherapyItem[] = []
    for (const id of therapyIds) {
      if (id === 'topical_retinoid' && retinoid) {
        items.push({ id: retinoid, active: true })
      } else if (id === 'acid_therapy') {
        for (const a of acids) items.push({ id: a, active: true })
      } else if (id !== 'topical_retinoid' && id !== 'acid_therapy') {
        items.push({ id, active: true })
      }
    }
    return items
  }, [therapyIds, retinoid, acids])

  const procedureItems = useMemo<ProcedureItem[]>(
    () => Object.entries(procedures).map(([id, period]) => ({ id, period })),
    [procedures]
  )

  const handleSave = () => {
    const structured: StructuredProfile = {
      skin_type: skinType && skinType !== 'unknown' ? skinType : null,
      age,
      concerns: [...selectedCards, ...specificIds],
      imperfections: [],
      states: [],
      therapy: therapyItems,
      procedures: procedureItems,
      goals: [],
      intolerances: intolerances,
      allergies: allergies,
    }
    onSave(structured)
  }

  // Шаги опроса: тип кожи → что беспокоит → каждое беспокойство → терапия → процедуры → ингредиенты.
  const steps = useMemo(() => {
    const s: { id: string; card?: (typeof CONCERN_CARDS)[number] }[] = [
      { id: 'skin' },
      { id: 'concerns' },
    ]
    for (const cardId of selectedCards) {
      const card = CONCERN_CARDS.find(c => c.id === cardId)
      if (card) s.push({ id: `concern:${card.id}`, card })
    }
    s.push({ id: 'therapy' }, { id: 'procedures' }, { id: 'intolerances' })
    return s
  }, [selectedCards])

  const [step, setStep] = useState(0)
  const current = steps[Math.min(step, steps.length - 1)]
  const isLast = step >= steps.length - 1
  const canNext = current.id !== 'skin' || skinType !== null

  return (
    <div className="flex flex-col">
      {/* Прогресс */}
      <div className="mb-4 flex items-center gap-3">
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">{step + 1}/{steps.length}</span>
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${((step + 1) / steps.length) * 100}%` }} />
        </div>
      </div>

      <div className="pb-24">
        {current.id === 'skin' && (
          <div className="space-y-6">
            <section>
              <h3 className="mb-2 text-sm font-medium text-foreground">Какой у вас тип кожи?</h3>
              <div className="flex flex-wrap gap-2">
                {SKIN_TYPE_OPTIONS.map(o => (
                  <button key={o.id} onClick={() => setSkinType(o.id)}
                    className={cn('rounded-full border px-3.5 py-1.5 text-sm transition-colors',
                      skinType === o.id ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-foreground/70 hover:border-primary/30')}>
                    {o.label}
                  </button>
                ))}
              </div>
            </section>
            <section>
              <h3 className="mb-2 text-sm font-medium text-foreground">Возраст</h3>
              <div className="flex flex-wrap gap-2">
                {AGE_OPTIONS.map(o => (
                  <button key={o.id} onClick={() => setAge(o.id)}
                    className={cn('rounded-full border px-3.5 py-1.5 text-sm transition-colors',
                      age === o.id ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-foreground/70 hover:border-primary/30')}>
                    {o.label}
                  </button>
                ))}
              </div>
            </section>
          </div>
        )}

        {current.id === 'concerns' && (
          <section>
            <h3 className="mb-2 text-sm font-medium text-foreground">Что вас беспокоит?</h3>
            <p className="mb-3 text-xs text-muted-foreground/70">Выберите всё, что к вам относится — дальше пройдём по каждому пункту отдельно.</p>
            <div className="grid grid-cols-2 gap-2">
              {CONCERN_CARDS.map(card => {
                const active = selectedCards.includes(card.id)
                return (
                  <button key={card.id} type="button" onClick={() => toggleCard(card.id)}
                    className={cn('flex items-center justify-between rounded-xl border px-3 py-3 text-left text-sm transition-colors',
                      active ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-foreground/80 hover:border-primary/30')}>
                    <span>{card.shortLabel}</span>
                    <span className={cn('flex size-4 shrink-0 items-center justify-center rounded-full border text-[10px]',
                      active ? 'border-primary bg-primary text-primary-foreground' : 'border-gray-300')}>
                      {active ? '✓' : ''}
                    </span>
                  </button>
                )
              })}
            </div>
          </section>
        )}

        {current.card && (
          <section>
            <h3 className="mb-3 text-sm font-medium text-foreground">{current.card.label}</h3>
            <div className="space-y-4">
              {current.card.questions.map(q => (
                <div key={q.id}>
                  <p className="mb-1.5 text-xs text-muted-foreground">{q.label}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {q.options.map(o => {
                      const checked = (answers[current.card!.id]?.[q.id] ?? []).includes(o.id)
                      return (
                        <button key={o.id} onClick={() => toggleAnswer(current.card!.id, q.id, o.id)}
                          className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                            checked ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/60 hover:border-primary/30')}>
                          {o.label}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {current.id === 'therapy' && (
          <section>
            <h3 className="mb-2 text-sm font-medium text-foreground">Используете сейчас лечение или активные средства?</h3>
            <div className="mb-2 flex gap-2">
              {[{ v: true, l: 'Да' }, { v: false, l: 'Нет' }].map(o => (
                <button key={String(o.v)}
                  onClick={() => { setTherapyEnabled(o.v); if (!o.v) { setTherapyIds([]); setRetinoid(null); setAcids([]) } }}
                  className={cn('rounded-full border px-3.5 py-1.5 text-sm transition-colors',
                    therapyEnabled === o.v ? 'border-primary bg-primary/5 text-primary' : 'border-gray-200 text-foreground/70')}>
                  {o.l}
                </button>
              ))}
            </div>
            {therapyEnabled && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {THERAPY_OPTIONS.map(o => (
                    <button key={o.id} onClick={() => toggleInList(therapyIds, setTherapyIds, o.id)}
                      className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                        therapyIds.includes(o.id) ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/60')}>
                      {o.label}
                    </button>
                  ))}
                </div>
                {therapyIds.includes('topical_retinoid') && (
                  <div>
                    <p className="mb-1 text-xs text-muted-foreground">Какой ретиноид?</p>
                    <div className="flex flex-wrap gap-1.5">
                      {RETINOID_OPTIONS.map(o => (
                        <button key={o.id} onClick={() => setRetinoid(o.id)}
                          className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                            retinoid === o.id ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/60')}>
                          {o.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {therapyIds.includes('acid_therapy') && (
                  <div>
                    <p className="mb-1 text-xs text-muted-foreground">Какие кислоты?</p>
                    <div className="flex flex-wrap gap-1.5">
                      {ACID_OPTIONS.map(o => (
                        <button key={o.id} onClick={() => toggleInList(acids, setAcids, o.id)}
                          className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                            acids.includes(o.id) ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/60')}>
                          {o.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {current.id === 'procedures' && (
          <section>
            <h3 className="mb-2 text-sm font-medium text-foreground">Были ли недавно процедуры?</h3>
            <div className="flex flex-wrap gap-1.5">
              {PROCEDURE_OPTIONS.map(o => {
                const selected = o.id in procedures
                return (
                  <div key={o.id} className="space-y-1">
                    <button
                      onClick={() => setProcedures(prev => {
                        const c = { ...prev }
                        if (selected) delete c[o.id]; else c[o.id] = '<7 days'
                        return c
                      })}
                      className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                        selected ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/60')}>
                      {o.label}
                    </button>
                    {selected && (
                      <div className="flex flex-wrap gap-1">
                        {PROCEDURE_PERIODS.map(p => (
                          <button key={p.id} onClick={() => setProcedures(prev => ({ ...prev, [o.id]: p.id }))}
                            className={cn('rounded-full border px-2 py-0.5 text-[10px] transition-colors',
                              procedures[o.id] === p.id ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/50')}>
                            {p.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {current.id === 'intolerances' && (
          <section>
            <h3 className="mb-2 text-sm font-medium text-foreground">Есть ингредиенты, которые вы избегаете?</h3>
            <div className="flex flex-wrap gap-1.5">
              {INTOLERANCE_OPTIONS.map(o => (
                <button key={o.id} onClick={() => toggleInList(intolerances, setIntolerances, o.id)}
                  className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                    intolerances.includes(o.id) ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/60')}>
                  {o.label}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Футер навигации — sticky, всегда видимый */}
      <div className="sticky bottom-0 z-10 -mx-4 border-t border-gray-200/50 bg-background px-4 pt-3 pb-[calc(env(safe-area-inset-bottom,0px)+0.75rem)]">
        <div className="flex gap-2">
          {step > 0 && (
            <button type="button" onClick={() => setStep(step - 1)}
              className="flex items-center justify-center gap-1 rounded-xl border border-gray-200 px-4 py-2.5 text-sm text-muted-foreground transition-colors hover:bg-gray-50">
              <ChevronLeft className="size-4" /> Назад
            </button>
          )}
          {isLast ? (
            <button type="button" onClick={handleSave}
              className="flex flex-1 items-center justify-center rounded-xl bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90">
              Сохранить
            </button>
          ) : (
            <button type="button" onClick={() => setStep(step + 1)} disabled={!canNext}
              className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40">
              Далее <ChevronRight className="size-4" />
            </button>
          )}
        </div>
        {onCancel && (
          <button type="button" onClick={onCancel}
            className="mt-2 w-full text-center text-xs text-muted-foreground/60 transition-colors hover:text-foreground">
            Отмена
          </button>
        )}
      </div>
    </div>
  )
}
