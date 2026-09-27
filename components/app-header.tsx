'use client'

import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { X, LogIn, Compass, ClipboardList, Send, Mail } from 'lucide-react'
import { useScrollLock } from '@/lib/use-scroll-lock'

interface AppHeaderProps {
  onOpenAccount: () => void
  onAuth: () => void
  isAuthenticated?: boolean
  userName?: string
  avatarUrl?: string
  onReplayGuide?: () => void
  onReplayQuiz?: () => void
  onCheck?: () => void
}

export function AppHeader({
  onOpenAccount,
  onAuth,
  isAuthenticated = false,
  userName = '',
  avatarUrl = '',
  onReplayGuide,
  onReplayQuiz,
  onCheck
}: AppHeaderProps) {
  const [showHelp, setShowHelp] = useState(false)
  const [helpPos, setHelpPos] = useState<{ top: number; right: number } | null>(null)
  const helpBtnRef = useRef<HTMLButtonElement | null>(null)

  useScrollLock(showHelp)

  const toggleHelp = () => {
    if (showHelp) {
      setShowHelp(false)
      setHelpPos(null)
      return
    }
    const btn = helpBtnRef.current
    if (btn) {
      const rect = btn.getBoundingClientRect()
      setHelpPos({ top: rect.bottom + 8, right: Math.max(8, window.innerWidth - rect.right) })
    } else {
      setHelpPos({ top: 56, right: 16 })
    }
    setShowHelp(true)
  }

  const handleProfileClick = () => {
    if (isAuthenticated) {
      onOpenAccount()
    } else {
      onAuth()
    }
  }

  return (
    <>
      <header className="relative z-20 w-full">
        <div
          className="flex w-full items-center justify-between gap-3 rounded-2xl px-4 py-3 md:px-5"
          style={{ backgroundColor: '#D6F264' }}
        >
          <img src="/main_logo.png" alt="aidermy" className="h-9 w-auto pixelated md:h-10" draggable={false} />

          <div className="flex items-center gap-2">
            {onCheck && (
              <button
                type="button"
                onClick={onCheck}
                className="hidden items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-md transition-transform hover:scale-[1.03] active:scale-95 md:inline-flex"
              >
                <img src="/QRCODE.png" alt="" className="size-5 pixelated" draggable={false} />
                Проверить продукт
              </button>
            )}
            <div className="relative">
            <button
              ref={helpBtnRef}
              type="button"
              aria-label="Помощь"
              onClick={toggleHelp}
              className="relative z-50 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
            >
              <span className="text-sm font-normal">?</span>
            </button>

            {/* === ПОПАП ПОМОЩИ — рендерится через portal, чтобы не ограничиваться
                stacking-контекстом header (z-20) и всегда быть поверх интерфейса === */}
            {showHelp && typeof document !== 'undefined' && createPortal(
              <>
                <div
                  className="fixed inset-0 z-[95] bg-black/20 backdrop-blur-sm animate-modal-backdrop"
                  onClick={() => setShowHelp(false)}
                />
                <div
                  className="fixed z-[96] w-64 max-w-[calc(100vw-2rem)] origin-top-right rounded-xl bg-white p-4 shadow-xl border border-primary/15 animate-help-popover"
                  style={{ top: helpPos?.top ?? 56, right: helpPos?.right ?? 16 }}
                >
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
              </>,
              document.body,
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
        </div>
      </header>
    </>
  )
}