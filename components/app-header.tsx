'use client'

import { useState } from 'react'
import { User, X } from 'lucide-react'
import { AidermyLogo } from '@/components/aidermy-logo'

export function AppHeader({ onProfile }: { onProfile: () => void }) {
  const [showHelp, setShowHelp] = useState(false)

  return (
    <>
      {/* === ХЕДЕР === */}
      <header className="relative z-20 flex w-full flex-col items-center pt-6 pb-1 md:fixed md:left-6 md:top-4 md:z-30 md:w-auto md:pt-0">
        {/* Логотип — слева на компе, по центру на мобилке */}
        <div className="md:order-1">
          <AidermyLogo />
        </div>

        {/* === КНОПКИ: СПРАВА НА КОМПЕ, СПРАВА НА МОБИЛКЕ === */}
        <div className="absolute right-4 top-3 flex items-center gap-2 md:fixed md:right-6 md:top-4 md:z-40">
          <button
            type="button"
            aria-label="Помощь"
            onClick={() => setShowHelp(!showHelp)}
            className="relative z-50 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
          >
            <span className="text-sm font-bold">?</span>
          </button>

          <button
            type="button"
            aria-label="Профиль"
            onClick={onProfile}
            className="flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
          >
            <User className="size-4" />
          </button>
        </div>
      </header>

      {/* === ПОПАП ПОМОЩИ === */}
      {showHelp && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm"
            onClick={() => setShowHelp(false)}
          />
          <div className="fixed right-4 top-20 z-50 w-64 rounded-lg bg-white p-4 shadow-xl border border-primary/10 md:right-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-foreground">Помощь</h3>
              <button
                onClick={() => setShowHelp(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>
            <p className="mb-3 text-xs text-muted-foreground">
              Есть вопросы? Напишите нам!
            </p>
            <div className="flex flex-col gap-2">
              <a
                href="https://t.me/your_telegram"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded-md border border-primary/15 px-3 py-2 text-sm text-foreground transition-colors hover:bg-primary/5 hover:border-primary/30"
              >
                <span className="text-base">📱</span>
                Telegram
              </a>
              <a
                href="mailto:your@email.com"
                className="flex items-center gap-2 rounded-md border border-primary/15 px-3 py-2 text-sm text-foreground transition-colors hover:bg-primary/5 hover:border-primary/30"
              >
                <span className="text-base">✉️</span>
                Email
              </a>
            </div>
          </div>
        </>
      )}
    </>
  )
}