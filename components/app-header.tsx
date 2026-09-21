'use client'

import { useState } from 'react'
import { X, LogIn } from 'lucide-react'
import { AidermyLogo } from '@/components/aidermy-logo'
import { useScrollLock } from '@/lib/use-scroll-lock'

interface AppHeaderProps {
  onOpenAccount: () => void
  onAuth: () => void
  isAuthenticated?: boolean
  userName?: string
  avatarUrl?: string
  onReplayGuide?: () => void
  onReplayQuiz?: () => void
}

export function AppHeader({
  onOpenAccount,
  onAuth,
  isAuthenticated = false,
  userName = '',
  avatarUrl = '',
  onReplayGuide,
  onReplayQuiz
}: AppHeaderProps) {
  const [showHelp, setShowHelp] = useState(false)

  useScrollLock(showHelp)

  const handleProfileClick = () => {
    if (isAuthenticated) {
      onOpenAccount()
    } else {
      onAuth()
    }
  }

  return (
    <>
      <header className="relative z-20 flex w-full flex-col items-center pt-8 pb-1 md:pt-8">
        <div className="w-full flex justify-center md:justify-start md:pl-6 transition-all duration-300">
          <AidermyLogo />
        </div>

        <div className="absolute right-4 top-3 flex items-center gap-2 md:right-6 md:top-4">
          <button
            type="button"
            aria-label="Помощь"
            onClick={() => setShowHelp(!showHelp)}
            className="relative z-50 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
          >
            <span className="text-sm font-normal">?</span>
          </button>

          {isAuthenticated ? (
            <button
              type="button"
              onClick={handleProfileClick}
              className="relative flex size-9 items-center justify-center overflow-hidden rounded-full border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
            >
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="text-sm font-normal uppercase">{userName?.[0] || 'U'}</span>
              )}
              <span className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-green-500 border-2 border-white" />
            </button>
          ) : (
            <button
              type="button"
              onClick={onAuth}
              className="flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
              aria-label="Войти"
            >
              <LogIn className="size-5" />
            </button>
          )}
        </div>
      </header>

      {/* === ПОПАП ПОМОЩИ === */}
      {showHelp && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm animate-modal-backdrop"
            onClick={() => setShowHelp(false)}
          />
          <div className="fixed right-4 top-20 z-50 w-64 rounded-lg bg-white p-4 shadow-xl border border-primary/10 md:right-6 animate-modal-panel">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-normal text-foreground">Помощь</h3>
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
              {onReplayGuide && (
                <button
                  onClick={() => { setShowHelp(false); onReplayGuide() }}
                  className="flex items-center gap-2 rounded-md border border-primary/15 px-3 py-2 text-sm text-foreground transition-colors hover:bg-primary/5 hover:border-primary/30"
                >
                  <span className="text-base">🧭</span>
                  Пройти обучение
                </button>
              )}
              {onReplayQuiz && (
                <button
                  onClick={() => { setShowHelp(false); onReplayQuiz() }}
                  className="flex items-center gap-2 rounded-md border border-primary/15 px-3 py-2 text-sm text-foreground transition-colors hover:bg-primary/5 hover:border-primary/30"
                >
                  <span className="text-base">📝</span>
                  Пройти опросник
                </button>
              )}
              <a
                href="https://t.me/aidermy_news"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded-md border border-primary/15 px-3 py-2 text-sm text-foreground transition-colors hover:bg-primary/5 hover:border-primary/30"
              >
                <span className="text-base">📱</span>
                Telegram
              </a>
              <a
                href="mailto:lyr.ami.tag@gmail.com"
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