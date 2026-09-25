'use client'

import { Search, History, User, Sparkles, LayoutGrid, Home, QrCode } from 'lucide-react'
import { cn } from '@/lib/utils'

export type TabId = 'home' | 'catalog' | 'history' | 'shelf' | 'profile'

const TABS: { id: TabId | 'check'; label: string; icon: typeof Search; circle?: boolean; primary?: boolean }[] = [
  { id: 'home', label: 'Главная', icon: Home, circle: true },
  { id: 'catalog', label: 'Каталог', icon: LayoutGrid, circle: true },
  { id: 'check', label: 'Проверить продукт', icon: QrCode, circle: true, primary: true },
  { id: 'shelf', label: 'Моя полка', icon: Sparkles, circle: true },
  { id: 'profile', label: 'Профиль', icon: User, circle: true },
  { id: 'history', label: 'История', icon: History, circle: true },
]

export function TabBar({
  active,
  onChange,
  onCheck,
  isAuthenticated = false,
}: {
  active: TabId
  onChange: (id: TabId) => void
  onCheck: () => void
  isAuthenticated?: boolean
}) {
  const visibleTabs = TABS.filter(tab => {
    // Гостям доступна только «Главная» (лендинг) — каталог, проверка и полка скрыты.
    if (!isAuthenticated) return tab.id === 'home'
    // Авторизованным «Главная» не нужна — стартовая вкладка «Моя полка».
    return tab.id !== 'home'
  })

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-30 bg-background/80 backdrop-blur-sm border-t border-gray-200/50 pb-[env(safe-area-inset-bottom,0px)]"
      aria-label="Основная навигация"
    >
      <div className="mx-auto flex w-full max-w-md items-end justify-around px-2 pt-2 pb-4 md:max-w-3xl lg:max-w-5xl xl:max-w-6xl">
        {visibleTabs.map(({ id, label, icon: Icon, circle, primary }) => {
          const isActive = active === id

          if (primary) {
            return (
              <button
                key={id}
                type="button"
                onClick={onCheck}
                aria-current={isActive ? 'page' : undefined}
                data-active={isActive ? 'true' : 'false'}
                data-tour={id}
                className="relative -mt-9 flex flex-1 flex-col items-center gap-0.5"
              >
                <span
                  className={cn(
                    'flex size-16 items-center justify-center rounded-2xl border bg-primary text-primary-foreground border-primary/30 shadow-[0_10px_30px_rgba(108,60,225,0.4)] transition-transform hover:scale-[1.03]'
                  )}
                >
                  <Icon className="size-7" strokeWidth={1.9} />
                </span>
                <span className="text-[9px] font-medium leading-none text-primary">{label}</span>
              </button>
            )
          }

          if (circle) {
            return (
              <button
                key={id}
                type="button"
                onClick={() => (id === 'check' ? onCheck() : onChange(id as TabId))}
                aria-current={isActive ? 'page' : undefined}
                data-active={isActive ? 'true' : 'false'}
                data-tour={id}
                className="relative -mt-6 flex flex-1 flex-col items-center gap-0.5"
              >
                <span
                  className={cn(
                    'tab-circle flex size-14 items-center justify-center rounded-full border',
                    isActive
                      ? 'bg-primary text-primary-foreground border-primary shadow-[0_8px_24px_rgba(21,21,21,0.4)]'
                      : 'bg-white text-muted-foreground border-gray-200/70 shadow-sm hover:border-primary/40 hover:text-primary'
                  )}
                >
                  <Icon className="tab-circle-icon size-6" strokeWidth={2} />
                </span>
                <span className={cn('text-[9px] font-normal leading-none', isActive ? 'text-primary' : 'text-muted-foreground')}>
                  {label}
                </span>
              </button>
            )
          }

          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id as TabId)}
              aria-current={isActive ? 'page' : undefined}
              data-active={isActive ? 'true' : 'false'}
              data-tour={id}
              className={cn(
                'nav-link-animated flex flex-1 flex-col items-center gap-0.5 rounded-md px-2 py-1.5 transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground'
              )}
            >
              <Icon
                className={cn('size-4.5', isActive && 'drop-shadow-[0_0_8px_rgba(108,60,225,0.3)]')}
                strokeWidth={2}
              />
              <span className="text-[9px] font-normal leading-none">{label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}