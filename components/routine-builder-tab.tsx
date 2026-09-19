'use client'

import { useState } from 'react'
import { Wand2, Sparkles, ArrowRight, LoaderCircle, CheckCircle2, ListChecks, User, Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { isProfileComplete, type SkinProfile } from '@/lib/store'

type RoutineProduct = {
    name: string
    brand: string
    slug: string
    image_url: string
    score: number
    matched_actives: string[]
    allergy_hits: string[]
}

type RoutineStep = {
    step: string
    category: string
    weight: number
    products: RoutineProduct[]
}

type Routine = {
    name: string
    description: string
    goal: string
    goal_title: string
    skin_type: string
    steps: RoutineStep[]
    total_weight: number
}

const EXAMPLES = ['Увлажнение', 'Защита от солнца', 'Лечение акне', 'Антивозраст', 'Осветление', 'Успокоение']

export function RoutineBuilderTab({
    profile,
    isAuthenticated,
    onGoToProfile,
    onStartQuiz,
    onAuth,
}: {
    profile: SkinProfile
    isAuthenticated: boolean
    onGoToProfile: () => void
    onStartQuiz: () => void
    onAuth: () => void
}) {
    const [query, setQuery] = useState('')
    const [loading, setLoading] = useState(false)
    const [routine, setRoutine] = useState<Routine | null>(null)
    const [error, setError] = useState('')
    const [needProfile, setNeedProfile] = useState(false)
    const [shelfName, setShelfName] = useState('')
    const [saving, setSaving] = useState(false)
    const [savedMsg, setSavedMsg] = useState('')
    const [selected, setSelected] = useState<Record<string, string>>({})

    const profileReady = isProfileComplete(profile)

    const handleSubmit = async () => {
        const q = query.trim()
        if (!q || loading) return
        if (!profileReady) {
            setNeedProfile(true)
            return
        }
        setNeedProfile(false)
        setLoading(true)
        setError('')
        setRoutine(null)
        setSavedMsg('')
        try {
            const res = await fetch('/api/routine/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: q,
                    profile: {
                        name: profile.name || '',
                        skin_type: profile.skinType || '',
                        age: profile.age || '',
                        concerns: profile.concerns || [],
                        allergies: profile.allergies || [],
                        custom_text: profile.customText || '',
                        quiz_answers: profile.quizAnswers || {},
                        skin_type_determined: profile.skinTypeDetermined || '',
                    },
                }),
            })
            if (!res.ok) throw new Error('Не удалось подобрать уход')
            const data = await res.json()
            setRoutine(data)
            setShelfName(data.name || '')
            const sel: Record<string, string> = {}
            ;(data.steps || []).forEach((s: RoutineStep) => {
                if (s.products?.[0]) sel[s.step] = s.products[0].slug
            })
            setSelected(sel)
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Не удалось подобрать уход')
        } finally {
            setLoading(false)
        }
    }

    const handleAddToShelf = async () => {
        if (!routine) return
        if (!isAuthenticated) {
            onAuth()
            return
        }
        setSaving(true)
        setSavedMsg('')
        try {
            const token = localStorage.getItem('token')
            const items = routine.steps
                .map((s) => {
                    const slug = selected[s.step]
                    return slug ? { slug, category: s.step } : null
                })
                .filter(Boolean) as { slug: string; category: string }[]
            const res = await fetch('/api/routine/to-shelf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({ name: shelfName.trim() || routine.name, items }),
            })
            const data = await res.json()
            setSavedMsg(data.added > 0 ? `Добавлено на полку: ${data.added} продуктов` : 'Эти продукты уже есть на полке')
        } catch {
            setSavedMsg('Не удалось добавить на полку')
        } finally {
            setSaving(false)
        }
    }

    const reset = () => {
        setRoutine(null)
        setError('')
        setSavedMsg('')
        setNeedProfile(false)
        setQuery('')
        setSelected({})
    }

    const selectProduct = (step: string, slug: string) => {
        setSelected((prev) => ({ ...prev, [step]: slug }))
    }

    return (
        <div className="no-scrollbar h-full overflow-y-auto py-4">
            <div className="mb-4">
                <h1 className="flex items-center gap-2 text-xl font-light text-foreground">
                    <Wand2 className="size-5 text-primary" strokeWidth={1.75} />
                    Подбор ухода
                </h1>
                <p className="mt-1 text-xs text-muted-foreground/70">
                    Опишите, какой уход хотите собрать — мы подберём схему и продукты под ваш профиль
                </p>
            </div>

            {!profileReady && !needProfile && (
                <div className="mb-3 flex items-center gap-2 rounded-xl border border-amber-200/60 bg-amber-50/50 px-3 py-2 text-[11px] text-amber-700/80">
                    <User className="size-3.5 shrink-0" />
                    Для точного подбора заполните профиль кожи или пройдите быстрый квиз.
                </div>
            )}

            <div className="rounded-2xl border border-white/40 bg-white/40 p-4 backdrop-blur-sm">
                <textarea
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault()
                            handleSubmit()
                        }
                    }}
                    rows={2}
                    placeholder="Например: хочу уход с упором на увлажнение…"
                    className="w-full resize-none rounded-xl border border-gray-200/60 bg-white/70 px-3 py-2.5 text-sm focus:border-primary/40 focus:outline-none"
                />
                <div className="mt-2 flex flex-wrap gap-1.5">
                    {EXAMPLES.map((ex) => (
                        <button
                            key={ex}
                            type="button"
                            onClick={() => setQuery((prev) => (prev ? prev : `Хочу уход: ${ex.toLowerCase()}`))}
                            className="rounded-full border border-gray-200/70 px-2.5 py-1 text-[10px] text-muted-foreground/70 transition-colors hover:border-primary/30 hover:text-primary"
                        >
                            {ex}
                        </button>
                    ))}
                </div>
                <button
                    onClick={handleSubmit}
                    disabled={loading || !query.trim()}
                    className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                >
                    {loading ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                    {loading ? 'Подбираем…' : 'Подобрать уход'}
                </button>
                {error && <p className="mt-2 text-[11px] text-red-500/80">{error}</p>}
            </div>

            {needProfile && (
                <div className="mt-3 rounded-2xl border border-primary/20 bg-primary/5 p-4 text-center">
                    <div className="mx-auto mb-2 flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                        <ListChecks className="size-5" strokeWidth={1.5} />
                    </div>
                    <h2 className="text-sm font-medium text-foreground">Сначала заполните профиль кожи</h2>
                    <p className="mt-1 text-[11px] text-muted-foreground/70">
                        Чтобы подобрать уход, нам нужно знать ваш тип кожи, проблемы и аллергии.
                    </p>
                    <div className="mt-3 flex flex-col gap-2">
                        <button onClick={onStartQuiz} className="w-full rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90">
                            Пройти быстрый квиз
                        </button>
                        <button onClick={onGoToProfile} className="w-full rounded-xl border border-gray-200 py-2.5 text-sm text-foreground/80 transition-colors hover:bg-gray-50">
                            Заполнить профиль вручную
                        </button>
                    </div>
                </div>
            )}

            {routine && (
                <div className="mt-4">
                    <div className="rounded-2xl border border-primary/20 bg-white/50 p-4 backdrop-blur-sm">
                        <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 flex-1">
                                <input
                                    value={shelfName}
                                    onChange={(e) => setShelfName(e.target.value)}
                                    className="w-full rounded-lg bg-transparent text-lg font-light text-foreground focus:outline-none"
                                    aria-label="Название ухода"
                                />
                                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[9px] text-primary">{routine.goal_title}</span>
                                    {routine.skin_type && (
                                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[9px] text-muted-foreground/70">{routine.skin_type}</span>
                                    )}
                                </div>
                            </div>
                            <button onClick={reset} className="shrink-0 text-[10px] text-muted-foreground/60 hover:text-primary">
                                Новый подбор
                            </button>
                        </div>
                        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground/70">{routine.description}</p>
                        <p className="mt-2 text-[10px] text-muted-foreground/50">Выберите по одному продукту на каждый шаг — отмеченные попадут на полку.</p>

                        <button
                            onClick={handleAddToShelf}
                            disabled={saving}
                            className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-2.5 text-sm text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
                        >
                            {saving ? <LoaderCircle className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
                            {saving ? 'Добавляем…' : 'Добавить набор на полку'}
                        </button>
                        {!isAuthenticated && <p className="mt-1.5 text-center text-[10px] text-muted-foreground/50">Понадобится войти в аккаунт</p>}
                        {savedMsg && <p className="mt-2 text-center text-[11px] text-primary">{savedMsg}</p>}
                    </div>

                    <div className="mt-3 space-y-3">
                        {routine.steps.map((step) => (
                            <div key={step.step} className="rounded-2xl border border-white/40 bg-white/40 p-3 backdrop-blur-sm">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium text-foreground/90">{step.step}</span>
                                        <span className="text-[10px] text-muted-foreground/50">{step.weight}%</span>
                                    </div>
                                    <ArrowRight className="size-3.5 text-muted-foreground/30" />
                                </div>
                                <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                                    <div className="h-full rounded-full bg-primary/70 transition-all" style={{ width: `${step.weight}%` }} />
                                </div>
                                <div className="mt-2.5 space-y-2">
                                    {step.products.map((p) => {
                                        const isSelected = selected[step.step] === p.slug
                                        return (
                                            <button
                                                key={p.slug}
                                                type="button"
                                                onClick={() => selectProduct(step.step, p.slug)}
                                                className={cn(
                                                    'flex w-full items-center gap-2.5 rounded-xl border p-2 text-left transition-all',
                                                    isSelected ? 'border-primary/40 bg-primary/5' : 'border-transparent hover:bg-white/60'
                                                )}
                                            >
                                                <div className="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white/70">
                                                    {p.image_url ? (
                                                        <img src={p.image_url} alt="" className="h-full w-full object-contain p-1" />
                                                    ) : (
                                                        <Sparkles className="size-4 text-muted-foreground/30" />
                                                    )}
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <p className="truncate text-[11px] font-medium text-foreground/80">{p.name}</p>
                                                    <p className="truncate text-[9px] text-muted-foreground/50">{p.brand}</p>
                                                </div>
                                                {p.matched_actives.length > 0 && (
                                                    <div className="hidden shrink-0 flex-wrap justify-end gap-1 sm:flex">
                                                        {p.matched_actives.slice(0, 3).map((a) => (
                                                            <span key={a} className="rounded-full bg-primary/5 px-1.5 py-0.5 text-[8px] text-primary/70">{a}</span>
                                                        ))}
                                                    </div>
                                                )}
                                                <span className={cn('flex size-4 shrink-0 items-center justify-center rounded-full border transition-colors', isSelected ? 'border-primary bg-primary text-white' : 'border-gray-300')}>
                                                    {isSelected && <Check className="size-2.5" strokeWidth={3} />}
                                                </span>
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="h-24" />
                </div>
            )}
        </div>
    )
}
