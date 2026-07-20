'use client'

import { Trash2 } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import type { CheckResult } from '@/lib/store'
import { cn } from '@/lib/utils'
import { useState, useEffect } from 'react'

function formatDate(ts: number) {
  if (!ts || ts === 0 || isNaN(ts)) {
    return 'Дата неизвестна'
  }
  try {
    const date = new Date(ts)
    if (isNaN(date.getTime())) {
      return 'Дата неизвестна'
    }
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return 'Дата неизвестна'
  }
}

export function HistoryTab({
  history,
  onClear,
  onSelect,
}: {
  history: CheckResult[]
  onClear: () => void
  onSelect: (item: CheckResult) => void
}) {
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), 50)
    return () => clearTimeout(timer)
  }, [])

  const cardStyle = "relative overflow-hidden bg-gradient-to-br from-primary/10 via-primary/5 to-transparent rounded-2xl p-5 border border-primary/20 backdrop-blur-sm hover:shadow-md transition-shadow"

  return (
    <div className="flex flex-col gap-5 max-w-md mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-normal text-foreground">История проверок</h1>
        {history.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            aria-label="Очистить историю"
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-red-500"
          >
            <Trash2 className="size-4" />
            Очистить
          </button>
        )}
      </div>

      {history.length === 0 ? (
        <div className={cn(cardStyle, 'card-enter', isVisible && 'card-enter-1')}>
          <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
          <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
          <div className="relative text-center py-8">
            <p className="text-sm text-muted-foreground">
              Пока нет проверок. Проверь первое средство на вкладке «Чекер».
            </p>
          </div>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {history.map((item, index) => (
            <li
              key={item.id}
              onClick={() => onSelect(item)}
              className={cn(
                cardStyle,
                'cursor-pointer transition-all hover:shadow-lg active:scale-[0.98]',
                'card-enter',
                isVisible && `card-enter-${Math.min(index + 1, 6)}`
              )}
              style={{
                animationDelay: `${index * 0.08}s`
              }}
            >
              <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
              <div className="absolute bottom-0 left-0 w-24 h-24 bg-primary/5 rounded-full blur-2xl translate-y-1/2 -translate-x-1/2" />
              <div className="relative flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <ScrambleText
                    as="p"
                    text={item.product}
                    revealDelay={30}
                    className="block font-normal text-foreground text-sm truncate"
                  />
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {item.skinType} · {formatDate(item.createdAt)}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">{item.verdict}</p>
                </div>
                <div className="shrink-0 text-right">
                  <span className="text-2xl font-normal text-primary">{item.score}%</span>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}