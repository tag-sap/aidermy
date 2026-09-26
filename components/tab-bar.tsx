'use client'

import { Search, User, Sparkles, LayoutGrid, Home, QrCode } from 'lucide-react'
import { cn } from '@/lib/utils'

export type TabId = 'home' | 'catalog' | 'shelf' | 'profile'

const TABS: { id: TabId; label: string; icon: typeof Search; circle?: boolean }[] = [
  { id: 'home', label: 'Главная', icon: Home, circle: true },
  { id: 'catalog', label: 'Каталог', icon: LayoutGrid, circle: true },
  { id: 'shelf', label: 'Моя полка', icon: Sparkles, circle: true },
  { id: 'profile', label: 'Профиль', icon: User, circle: true },
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
      {/* Плавающая кнопка «Проверить продукт» — по центру, над вкладкой «Моя полка» */}
      {isAuthenticated && (
        <button
          type="button"
          onClick={onCheck}
          aria-label="Проверить продукт"
          className="group absolute -top-16 left-1/2 z-40 flex size-16 -translate-x-1/2 items-center justify-center rounded-2xl border border-white/30 bg-primary/90 text-primary-foreground shadow-lg backdrop-blur-md transition-transform hover:scale-105"
        >
          <QrCode className="size-7" strokeWidth={1.9} />
          <span className="pointer-events-none absolute -top-9 whitespace-nowrap rounded-lg bg-foreground/90 px-2 py-1 text-[10px] text-background opacity-0 shadow backdrop-blur-sm transition-opacity group-hover:opacity-100">
            Проверить продукт
          </span>
        </button>
      )}

      <div className="mx-auto flex w-full max-w-md items-end justify-around px-2 pt-2 pb-4 md:max-w-3xl lg:max-w-5xl xl:max-w-6xl">
        {visibleTabs.map(({ id, label, icon: Icon, circle }) => {
          const isActive = active === id

          if (circle) {
            return (
              <button
                key={id}
                type="button"
                onClick={() => onChange(id)}
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
              onClick={() => onChange(id)}
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