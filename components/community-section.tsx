'use client'

import { useCallback, useEffect, useState } from 'react'
import { Star, LoaderCircle, X, ThumbsUp } from 'lucide-react'
import { cn } from '@/lib/utils'

type CommunityRating = { average: number | null; count: number }
type PersonalizedRating = { available: boolean; count: number; average: number | null }

type Review = {
  id: number
  displayName: string
  avatarUrl: string
  rating: number
  text: string
  usageDuration: string
  tags: string[]
  helpfulCount: number
  isHelpfulByCurrentUser: boolean
  isSimilarProfile: boolean
  isOwn: boolean
  createdAt: string
}

const DURATIONS = [
  { key: 'LESS_THAN_WEEK', label: 'Меньше недели' },
  { key: 'ONE_TO_FOUR_WEEKS', label: '1–4 недели' },
  { key: 'ONE_TO_THREE_MONTHS', label: '1–3 месяца' },
  { key: 'THREE_PLUS_MONTHS', label: '3+ месяца' },
]

const TAGS = [
  { key: 'HYDRATION', label: 'Увлажнение' },
  { key: 'TEXTURE', label: 'Текстура' },
  { key: 'ABSORPTION', label: 'Впитывание' },
  { key: 'COMFORT', label: 'Комфорт' },
  { key: 'SCENT', label: 'Аромат' },
  { key: 'EFFECT', label: 'Эффект' },
  { key: 'IRRITATION', label: 'Раздражение' },
]

const VISIBILITIES = [
  { key: 'ANONYMOUS', label: 'Анонимно' },
  { key: 'NAME', label: 'Показывать имя' },
  { key: 'PUBLIC_PROFILE', label: 'Имя · профиль Aidermy' },
]

const PAGE = 10

function durationLabel(key: string) {
  return DURATIONS.find((d) => d.key === key)?.label || ''
}

function tagLabel(key: string) {
  return TAGS.find((t) => t.key === key)?.label || key
}

function Stars({ value, onChange }: { value: number; onChange?: (v: number) => void }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          disabled={!onChange}
          onClick={() => onChange?.(i)}
          className={cn(onChange ? 'cursor-pointer transition-transform hover:scale-110' : 'cursor-default')}
        >
          <Star className={cn('size-4', i <= value ? 'fill-amber-400 text-amber-400' : 'text-gray-200')} />
        </button>
      ))}
    </div>
  )
}

export function CommunitySection({
  slug,
  isAuthenticated,
  community,
}: {
  slug: string
  isAuthenticated: boolean
  community: { overall: CommunityRating; personalized: PersonalizedRating }
}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const [reviews, setReviews] = useState<Review[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [offset, setOffset] = useState(0)
  const [rating, setRating] = useState(community.overall)
  const [personalized, setPersonalized] = useState(community.personalized)

  const [showForm, setShowForm] = useState(false)
  const [myRating, setMyRating] = useState(0)
  const [text, setText] = useState('')
  const [usage, setUsage] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [visibility, setVisibility] = useState('ANONYMOUS')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState('')

  const loadReviews = useCallback(
    async (nextOffset: number) => {
      const res = await fetch(
        `/api/community/reviews?slug=${encodeURIComponent(slug)}&limit=${PAGE}&offset=${nextOffset}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      )
      if (!res.ok) return
      const data = await res.json()
      if (nextOffset === 0) {
        setReviews(data.reviews || [])
      } else {
        setReviews((prev) => [...prev, ...(data.reviews || [])])
      }
      setTotal(data.total || 0)
      setOffset(nextOffset + (data.reviews || []).length)
    },
    [slug, token],
  )

  const reloadAll = useCallback(async () => {
    setLoading(true)
    await loadReviews(0)
    setLoading(false)
    try {
      const r = await fetch(`/api/community/rating?slug=${encodeURIComponent(slug)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (r.ok) {
        const d = await r.json()
        setRating(d.overall || rating)
        setPersonalized(d.personalized || personalized)
      }
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadReviews, slug, token])

  useEffect(() => {
    reloadAll()
  }, [reloadAll])

  const loadMore = async () => {
    setLoadingMore(true)
    await loadReviews(offset)
    setLoadingMore(false)
  }

  const toggleTag = (key: string) => {
    setTags((prev) => (prev.includes(key) ? prev.filter((t) => t !== key) : [...prev, key]))
  }

  const submitReview = async () => {
    if (myRating < 1 || myRating > 5) {
      setFormError('Выберите оценку')
      return
    }
    setSubmitting(true)
    setFormError('')
    try {
      const res = await fetch('/api/community/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ slug, rating: myRating, text: text.trim(), usage_duration: usage, tags, visibility }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Не удалось сохранить отзыв')
      }
      setShowForm(false)
      setText('')
      setUsage('')
      setTags([])
      await reloadAll()
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Не удалось сохранить отзыв')
    } finally {
      setSubmitting(false)
    }
  }

  const toggleHelpful = async (reviewId: number) => {
    const res = await fetch(`/api/community/reviews/${reviewId}/helpful`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return
    const d = await res.json()
    setReviews((prev) =>
      prev.map((r) =>
        r.id === reviewId ? { ...r, helpfulCount: d.helpfulCount, isHelpfulByCurrentUser: d.helpful } : r,
      ),
    )
  }

  const deleteReview = async (reviewId: number) => {
    const res = await fetch(`/api/community/reviews/${reviewId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    })
    if (res.ok) await reloadAll()
  }

  const hasMore = offset < total


  return (
    <div className="mt-5 border-t border-gray-100 pt-4">
      <h3 className="mb-3 text-sm font-normal text-foreground">Отзывы сообщества</h3>

      <div className="space-y-2">
        <div className="flex items-center justify-between rounded-xl border border-gray-100 bg-gray-50/60 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <span className="text-lg font-normal text-foreground">
              {rating.average != null ? rating.average.toFixed(1) : '—'}
            </span>
            <Stars value={Math.round(rating.average ?? 0)} />
          </div>
          <span className="text-xs text-muted-foreground/60">
            {rating.count > 0 ? `${rating.count} оценок` : 'Пока нет отзывов'}
          </span>
        </div>

        {isAuthenticated && personalized.available && (
          <div className="flex items-center justify-between rounded-xl border border-primary/15 bg-primary/5 px-3 py-2.5">
            <div className="flex items-center gap-2">
              <span className="text-lg font-normal text-primary">{personalized.average?.toFixed(1)}</span>
              <Stars value={Math.round(personalized.average ?? 0)} />
            </div>
            <span className="text-xs text-primary/70">Похожие на ваш профиль · {personalized.count}</span>
          </div>
        )}
      </div>

      {isAuthenticated && (
        <div className="mt-3">
          {!showForm ? (
            <button
              onClick={() => setShowForm(true)}
              className="w-full rounded-xl border border-primary/20 bg-white py-2 text-xs text-primary transition-colors hover:bg-primary/5"
            >
              Оценить продукт
            </button>
          ) : (
            <div className="rounded-xl border border-gray-200 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-foreground">Как вам продукт?</span>
                <button onClick={() => setShowForm(false)} className="text-muted-foreground hover:text-foreground">
                  <X className="size-3.5" />
                </button>
              </div>

              <Stars value={myRating} onChange={setMyRating} />

              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Расскажите о впечатлениях…"
                rows={2}
                className="mt-2 w-full rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-1.5 text-xs focus:border-primary/40 focus:outline-none"
              />

              <p className="mt-2 text-[10px] text-muted-foreground/50">Сколько вы им пользовались?</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {DURATIONS.map((d) => (
                  <button
                    key={d.key}
                    onClick={() => setUsage(d.key)}
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[10px] transition-colors',
                      usage === d.key ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-muted-foreground hover:border-primary/40',
                    )}
                  >
                    {d.label}
                  </button>
                ))}
              </div>

              <p className="mt-2 text-[10px] text-muted-foreground/50">Что можете отметить?</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {TAGS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => toggleTag(t.key)}
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[10px] transition-colors',
                      tags.includes(t.key) ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-muted-foreground hover:border-primary/40',
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              <div className="mt-2 flex flex-wrap gap-1.5">
                {VISIBILITIES.map((v) => (
                  <button
                    key={v.key}
                    onClick={() => setVisibility(v.key)}
                    className={cn(
                      'rounded-full border px-2 py-0.5 text-[10px] transition-colors',
                      visibility === v.key ? 'border-primary bg-primary/10 text-primary' : 'border-gray-200 text-muted-foreground hover:border-primary/40',
                    )}
                  >
                    {v.label}
                  </button>
                ))}
              </div>

              {formError && <p className="mt-2 text-[11px] text-red-500">{formError}</p>}

              <button
                onClick={submitReview}
                disabled={submitting}
                className="mt-3 w-full rounded-xl bg-primary py-2 text-xs text-white transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {submitting ? 'Сохраняем…' : 'Опубликовать'}
              </button>
            </div>
          )}
        </div>
      )}


      {loading ? (
        <div className="flex justify-center py-6">
          <LoaderCircle className="size-5 animate-spin text-primary" />
        </div>
      ) : reviews.length === 0 ? (
        <p className="py-6 text-center text-xs text-muted-foreground/50">Пока нет отзывов</p>
      ) : (
        <div className="mt-3 space-y-3">
          {reviews.map((r) => (
            <div key={r.id} className="rounded-xl border border-gray-100 p-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  {r.avatarUrl ? (
                    <img src={r.avatarUrl} alt="" className="size-5 shrink-0 rounded-full object-cover" />
                  ) : null}
                  <span className="text-xs font-medium text-foreground">{r.displayName}</span>
                  {r.isSimilarProfile && (
                    <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] text-primary">Похожий профиль</span>
                  )}
                </div>
                <Stars value={r.rating} />
              </div>

              {r.text && <p className="mt-1.5 text-xs leading-relaxed text-foreground/70">{r.text}</p>}

              {(r.usageDuration || r.tags.length > 0) && (
                <div className="mt-2 flex flex-wrap items-center gap-1">
                  {r.usageDuration && (
                    <span className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] text-muted-foreground/60">
                      {durationLabel(r.usageDuration)}
                    </span>
                  )}
                  {r.tags.map((t) => (
                    <span key={t} className="rounded-full bg-gray-100 px-1.5 py-0.5 text-[9px] text-muted-foreground/60">
                      {tagLabel(t)}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-2 flex items-center gap-3">
                {isAuthenticated && !r.isOwn && (
                  <button
                    onClick={() => toggleHelpful(r.id)}
                    className={cn(
                      'flex items-center gap-1 text-[10px] transition-colors',
                      r.isHelpfulByCurrentUser ? 'text-primary' : 'text-muted-foreground/60 hover:text-primary',
                    )}
                  >
                    <ThumbsUp className="size-3" />
                    Полезно{r.helpfulCount > 0 ? ` · ${r.helpfulCount}` : ''}
                  </button>
                )}
                {r.isOwn && (
                  <button onClick={() => deleteReview(r.id)} className="text-[10px] text-red-400 transition-colors hover:text-red-500">
                    Удалить
                  </button>
                )}
              </div>
            </div>
          ))}

          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="w-full rounded-xl border border-gray-200 py-2 text-xs text-muted-foreground transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              {loadingMore ? 'Загружаем…' : 'Показать ещё'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

