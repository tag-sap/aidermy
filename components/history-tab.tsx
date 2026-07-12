'use client'

import { Trash2 } from 'lucide-react'
import { ScrambleText } from '@/components/scramble-text'
import type { CheckResult } from '@/lib/store'

function formatDate(ts: number) {
  return new Date(ts).toLocaleString('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function HistoryTab({
  history,
  onClear,
}: {
  history: CheckResult[]
  onClear: () => void
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
              className="card-soft relative flex items-center justify-between gap-4 rounded-md px-5 py-4"
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