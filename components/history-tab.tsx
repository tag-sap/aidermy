'use client'

import { Trash2 } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import type { CheckResult } from '@/lib/store'

function formatDate(ts: number) {
  // Защита от некорректных данных
  if (!ts || ts === 0 || isNaN(ts)) {
    return 'Дата неизвестна'
  }

  try {
    const date = new Date(ts)
    // Проверяем, что дата валидная
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
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <ScrambleText
          as="h1"
          text="История проверок"
          className="font-serif text-2xl font-bold text-foreground"
        />
        {history.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            aria-label="Очистить историю"
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            <Trash2 className="size-4" />
            Очистить
          </button>
        )}
      </div>

      {history.length === 0 ? (
        <div className="card-soft w-full rounded-md px-6 py-12 text-center">
          <div className="bubble-1 bubble" />
          <div className="bubble-2 bubble" />
          <div className="bubble-3 bubble" />
          <p className="text-sm text-muted-foreground">
            Пока нет проверок. Проверь первое средство на вкладке «Чекер».
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {history.map((item) => (
            <li
              key={item.id}
              onClick={() => onSelect(item)}
              className="card-soft relative flex cursor-pointer items-center justify-between gap-4 rounded-md px-5 py-4 transition-all hover:border-primary/30 hover:shadow-[0_0_20px_rgba(255,79,0,0.06)]"
            >
              <div className="bubble-1 bubble" />
              <div className="bubble-2 bubble" />
              <div className="bubble-3 bubble" />
              <div className="min-w-0">
                <ScrambleText
                  as="p"
                  text={item.product}
                  revealDelay={30}
                  className="block truncate font-serif text-base font-semibold text-foreground"
                />
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {item.skinType} · {formatDate(item.createdAt)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">{item.verdict}</p>
              </div>
              <div className="shrink-0 text-right">
                <span className="text-2xl font-bold text-primary">{item.score}%</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}