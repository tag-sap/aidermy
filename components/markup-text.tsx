'use client'

import { Fragment, type ReactNode } from 'react'

// Цвета совпадают с палитрой Aidermy (жёлтый / янтарный / красный).
const TAG_COLORS: Record<string, string> = {
  good: '#2E7D4F',
  warning: '#D97706',
  bad: '#EF4444',
}

/**
 * Рендерит текстовый markup с тегами <good>, <warning>, <bad> как цветную разметку.
 * Никогда не показывает сырые теги пользователю.
 */
export function MarkupText({ text, className }: { text?: string | null; className?: string }) {
  if (!text) return null

  const parts = text.split(/(<\/?(?:good|warning|bad)>)/g)
  const stack: string[] = []
  const nodes: ReactNode[] = []
  let key = 0

  for (const part of parts) {
    if (!part) continue
    const match = part.match(/^<\/?(good|warning|bad)>$/)
    if (match) {
      const tag = match[1]
      if (part.startsWith('</')) {
        const idx = stack.lastIndexOf(tag)
        if (idx !== -1) stack.splice(idx, 1)
      } else {
        stack.push(tag)
      }
      continue
    }
    const active = stack[stack.length - 1]
    if (active && TAG_COLORS[active]) {
      nodes.push(
        <span key={key++} style={{ color: TAG_COLORS[active], fontWeight: 500 }}>
          {part}
        </span>,
      )
    } else {
      nodes.push(<Fragment key={key++}>{part}</Fragment>)
    }
  }

  return <span className={className}>{nodes}</span>
}
