'use client'

import { useState, useEffect, useRef } from 'react'
import { User, X, LogOut, Settings, Heart, History } from 'lucide-react'
import { AidermyLogo } from '@/components/aidermy-logo'

interface AppHeaderProps {
  onProfile: () => void
  onAuth: () => void
  isAuthenticated?: boolean
  userName?: string
  onLogout?: () => void
}

export function AppHeader({
  onProfile,
  onAuth,
  isAuthenticated = false,
  userName = '',
  onLogout
}: AppHeaderProps) {
  const [showHelp, setShowHelp] = useState(false)
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [isCompact, setIsCompact] = useState(false)
  const logoRef = useRef<HTMLDivElement>(null)
  const buttonsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const checkOverlap = () => {
      if (logoRef.current && buttonsRef.current) {
        const logoRect = logoRef.current.getBoundingClientRect()
        const buttonsRect = buttonsRef.current.getBoundingClientRect()
        const overlap = logoRect.right > buttonsRect.left - 10
        setIsCompact(overlap)
      }
    }
    
    checkOverlap()
    window.addEventListener('resize', checkOverlap)
    setTimeout(checkOverlap, 500)
    return () => window.removeEventListener('resize', checkOverlap)
  }, [])

  const handleProfileClick = () => {
    if (isAuthenticated) {
      setShowUserMenu(!showUserMenu)
    } else {
      onAuth()
    }
  }

  return (
    <>
      <header className="relative z-20 flex w-full flex-col items-center pt-6 pb-1 md:fixed md:left-6 md:top-4 md:z-30 md:w-auto md:pt-0">
        <div 
          ref={logoRef}
          className={`md:order-1 transition-all duration-500 ${
            isCompact ? 'transform -rotate-90 origin-center' : ''
          }`}
        >
          <AidermyLogo isCompact={isCompact} />
        </div>

        <div 
          ref={buttonsRef}
          className="absolute right-4 top-3 flex items-center gap-2 md:fixed md:right-6 md:top-4 md:z-40"
        >
          <button
            type="button"
            aria-label="Помощь"
            onClick={() => setShowHelp(!showHelp)}
            className="relative z-50 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10"
          >
            <span className="text-sm font-bold">?</span>
          </button>

          {isAuthenticated ? (
            <button
              type="button"
              onClick={handleProfileClick}
              className="flex size-9 items-center justify-center rounded-md border border-primary/20 bg-white/5 text-primary transition-colors hover:bg-primary/10 relative"
            >
              <span className="text-sm font-bold uppercase">{userName?.[0] || 'U'}</span>
              <span className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-green-500 border-2 border-white" />
            </button>
          ) : (
            <button
              type="button"
              onClick={onAuth}
              className={`flex items-center justify-center rounded-md border border-primary/20 bg-white/5 px-3 py-1.5 text-sm font-medium text-primary transition-all duration-300 hover:bg-primary/10 ${
                isCompact ? 'flex-col px-1.5 py-1.5 text-[11px] leading-none' : ''
              }`}
            >
              {isCompact ? (
                <>
                  <span>В</span>
                  <span>о</span>
                  <span>й</span>
                  <span>т</span>
                  <span>и</span>
                </>
              ) : (
                <>
                  <User className="size-4 mr-1.5" />
                  Войти
                </>
              )}
            </button>
          )}
        </div>
      </header>

      {/* === ВЫПАДАЮЩЕЕ МЕНЮ ПОЛЬЗОВАТЕЛЯ === */}
      {isAuthenticated && showUserMenu && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setShowUserMenu(false)} />
          <div className="fixed right-4 top-16 z-50 w-56 rounded-lg bg-white shadow-xl border border-primary/10 overflow-hidden md:right-6 md:top-14">
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="font-semibold text-sm text-foreground">{userName}</p>
              <p className="text-xs text-muted-foreground">Личный кабинет</p>
            </div>

            <div className="py-1">
              <button
                onClick={() => {
                  setShowUserMenu(false)
                  onProfile()
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-primary/5 transition-colors"
              >
                <Settings className="size-4 text-muted-foreground" />
                Анкета и настройки
              </button>

              <button
                onClick={() => {
                  setShowUserMenu(false)
                  onProfile()
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-primary/5 transition-colors"
              >
                <History className="size-4 text-muted-foreground" />
                История проверок
              </button>

              <button
                onClick={() => {
                  setShowUserMenu(false)
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-primary/5 transition-colors"
              >
                <Heart className="size-4 text-muted-foreground" />
                Избранное
              </button>
            </div>

            <div className="border-t border-gray-100 py-1">
              <button
                onClick={() => {
                  setShowUserMenu(false)
                  onLogout?.()
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-sm text-red-500 hover:bg-red-50 transition-colors"
              >
                <LogOut className="size-4" />
                Выйти
              </button>
            </div>
          </div>
        </>
      )}

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