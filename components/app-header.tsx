'use client'

import { useState } from 'react'
import { X, LogIn, Compass, ClipboardList, Send, Mail } from 'lucide-react'
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
          <div className="relative">
            <button
              type="button"
              aria-label="Помощь"
              onClick={() => setShowHelp(!showHelp)}
              className="relative z-50 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
            >
              <span className="text-sm font-normal">?</span>
            </button>

            {/* === ПОПАП ПОМОЩИ — привязан к кнопке «?» === */}
            {showHelp && (
              <>
                <div
                  className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm animate-modal-backdrop"
                  onClick={() => setShowHelp(false)}
                />
                <div className="absolute right-0 top-full z-50 mt-2 w-64 origin-top-right rounded-xl bg-white p-4 shadow-xl border border-primary/15 animate-help-popover">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-normal text-foreground">Помощь</h3>
                    <button
                      onClick={() => setShowHelp(false)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="size-4" />
                    </button>
                  </div>
                  <div className="flex flex-col gap-1">
                    {onReplayGuide && (
                      <button
                        onClick={() => { setShowHelp(false); onReplayGuide() }}
                        className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-primary/5"
                      >
                        <Compass className="size-4 shrink-0 text-primary/70" strokeWidth={1.75} />
                        Пройти обучение
                      </button>
                    )}
                    {onReplayQuiz && (
                      <button
                        onClick={() => { setShowHelp(false); onReplayQuiz() }}
                        className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-primary/5"
                      >
                        <ClipboardList className="size-4 shrink-0 text-primary/70" strokeWidth={1.75} />
                        Пройти опросник
                      </button>
                    )}
                    <a
                      href="https://t.me/aidermy_news"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-primary/5"
                    >
                      <Send className="size-4 shrink-0 text-primary/70" strokeWidth={1.75} />
                      Telegram
                    </a>
                    <a
                      href="mailto:lyr.ami.tag@gmail.com"
                      className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-primary/5"
                    >
                      <Mail className="size-4 shrink-0 text-primary/70" strokeWidth={1.75} />
                      Email
                    </a>
                  </div>
                </div>
              </>
            )}
          </div>

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
              <span className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-primary border-2 border-white" />
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
    </>
  )
}