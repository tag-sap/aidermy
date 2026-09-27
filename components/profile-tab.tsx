'use client'

import { forwardRef, useImperativeHandle, useMemo } from 'react'
import { RotateCcw } from 'lucide-react'
import type { SkinProfile } from '@/lib/store'
import { SKIN_TYPE_OPTIONS, CONCERN_CARDS, INTOLERANCE_OPTIONS, THERAPY_OPTIONS } from '@/lib/profile-questionnaire'

interface ProfileTabProps {
  profile: SkinProfile
  onSave: (p: SkinProfile) => void
  onStartQuiz?: () => void
}

export const ProfileTab = forwardRef<{ getDraft: () => SkinProfile }, ProfileTabProps>(
  ({ profile, onSave, onStartQuiz }, ref) => {
    useImperativeHandle(ref, () => ({ getDraft: () => profile }), [profile])

    const structured = profile.structured

    const skinLabel = useMemo(() => {
      const id = structured?.skin_type
      return (SKIN_TYPE_OPTIONS.find(o => o.id === id)?.label ?? profile.skinType) || 'Не указан'
    }, [structured, profile.skinType])

    const concerns = useMemo(() => {
      const ids = new Set(structured?.concerns ?? [])
      const rows: string[] = []
      for (const card of CONCERN_CARDS) {
        const opts = card.questions.flatMap(q => q.options).filter(o => ids.has(o.id))
        if (opts.length) rows.push(`${card.shortLabel}: ${opts.map(o => o.label).join(', ')}`)
        else if (ids.has(card.id)) rows.push(card.shortLabel)
      }
      return rows
    }, [structured])

    const intolerances = useMemo(() => {
      return (structured?.intolerances ?? [])
        .map(id => (typeof id === 'string' ? (INTOLERANCE_OPTIONS.find(o => o.id === id)?.label ?? id) : ''))
        .filter(Boolean)
    }, [structured])

    const therapy = useMemo(() => {
      return (structured?.therapy ?? []).map(t => THERAPY_OPTIONS.find(o => o.id === t.id)?.label ?? t.id)
    }, [structured])

    const hasData = Boolean(structured || profile.skinType)

    return (
      <div className="w-full space-y-6">
        <div className="space-y-4">
          {hasData ? (
            <>
              <div className="rounded-2xl border border-gray-200/60 p-4">
                <p className="text-xs text-muted-foreground">Тип кожи</p>
                <p className="mt-1 text-lg font-advaken text-foreground">{skinLabel}</p>
              </div>

              {concerns.length > 0 && (
                <div className="rounded-2xl border border-gray-200/60 p-4">
                  <p className="text-xs text-muted-foreground">Беспокойства</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {concerns.map((c, i) => (
                      <span key={i} className="rounded-full bg-muted px-3 py-1 text-xs text-foreground/80">{c}</span>
                    ))}
                  </div>
                </div>
              )}

              {intolerances.length > 0 && (
                <div className="rounded-2xl border border-gray-200/60 p-4">
                  <p className="text-xs text-muted-foreground">Избегаю ингредиенты</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {intolerances.map((x, i) => (
                      <span key={i} className="rounded-full bg-muted px-3 py-1 text-xs text-foreground/80">{x}</span>
                    ))}
                  </div>
                </div>
              )}

              {therapy.length > 0 && (
                <div className="rounded-2xl border border-gray-200/60 p-4">
                  <p className="text-xs text-muted-foreground">Активное лечение</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {therapy.map((x, i) => (
                      <span key={i} className="rounded-full bg-muted px-3 py-1 text-xs text-foreground/80">{x}</span>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Анкета ещё не пройдена. Пройдите опрос, чтобы подобрать уход под вашу кожу.</p>
          )}
        </div>

        {onStartQuiz && (
          <button
            onClick={onStartQuiz}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <RotateCcw className="size-4" />
            {hasData ? 'Пройти опрос заново' : 'Пройти опрос'}
          </button>
        )}
      </div>
    )
  }
)

ProfileTab.displayName = 'ProfileTab'
