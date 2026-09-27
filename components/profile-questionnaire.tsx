'use client'

import { useMemo, useState } from 'react'
import { ChevronDown } from 'lucide-react'
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
  const [age, setAge] = useState<string | null>(null)
  const [selectedCards, setSelectedCards] = useState<string[]>(init.selectedCards)
  const [answers, setAnswers] = useState<Record<string, Record<string, string[]>>>(init.answers)
  const [therapyEnabled, setTherapyEnabled] = useState<boolean | null>(init.therapyEnabled)
  const [therapyIds, setTherapyIds] = useState<string[]>(init.therapyIds)
  const [retinoid, setRetinoid] = useState<string | null>(init.retinoid)
  const [acids, setAcids] = useState<string[]>(init.acids)
  const [procedures, setProcedures] = useState<Record<string, string>>(init.procedures)
  const [intolerances, setIntolerances] = useState<string[]>(init.intolerances)
  const allergies: string[] = [] // (аллергии — отдельный блок, добавляется позже)

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

  return (
    <div className="w-full space-y-5">
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

      <section>
        <h3 className="mb-2 text-sm font-medium text-foreground">Что вас беспокоит?</h3>
        <div className="grid grid-cols-2 gap-2">
          {CONCERN_CARDS.map(card => {
            const active = selectedCards.includes(card.id)
            return (
              <div key={card.id} className="overflow-hidden rounded-xl border">
                <button onClick={() => toggleCard(card.id)}
                  className={cn('flex w-full items-center justify-between px-3 py-2.5 text-left text-sm transition-colors',
                    active ? 'bg-primary/5 text-primary' : 'text-foreground/80 hover:bg-gray-50')}>
                  <span>{card.shortLabel}</span>
                  <ChevronDown className={cn('size-4 transition-transform', active && 'rotate-180')} />
                </button>
                {active && (
                  <div className="space-y-3 border-t border-gray-100 p-3">
                    {card.questions.map(q => (
                      <div key={q.id}>
                        <p className="mb-1.5 text-xs text-muted-foreground">{q.label}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {q.options.map(o => {
                            const checked = (answers[card.id]?.[q.id] ?? []).includes(o.id)
                            return (
                              <button key={o.id} onClick={() => toggleAnswer(card.id, q.id, o.id)}
                                className={cn('rounded-full border px-2.5 py-1 text-xs transition-colors',
                                  checked ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-foreground/60 hover:border-primary/30')}>
                                {o.label}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ))}
      <section className="rounded-xl border border-gray-100 p-3">
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

      <section className="rounded-xl border border-gray-100 p-3">
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

      <section className="rounded-xl border border-gray-100 p-3">
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

      <div className="flex gap-2 pt-2">
        {onCancel && (
          <button onClick={onCancel} className="flex-1 rounded-xl border border-gray-200 py-2.5 text-sm text-foreground/70 transition-colors hover:bg-gray-50">
            Отмена
          </button>
        )}
        <button onClick={handleSave} className="flex-1 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90">
          Сохранить
        </button>
      </div>
    </div>
  )
}
