'use client'

import { Search, History, User, Sparkles, LayoutGrid } from 'lucide-react'
import { cn } from '@/lib/utils'

export type TabId = 'catalog' | 'history' | 'shelf' | 'profile'

const TABS: { id: TabId | 'check'; label: string; icon: typeof Search; circle?: boolean }[] = [
  { id: 'catalog', label: 'Каталог', icon: LayoutGrid, circle: true },
  { id: 'check', label: 'Проверить', icon: Search, circle: true },
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
    if (!isAuthenticated && (tab.id === 'history' || tab.id === 'profile' || tab.id === 'shelf')) {
      return false
    }
    return true
  })

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-30 bg-background/80 backdrop-blur-sm border-t border-gray-200/50 pb-[env(safe-area-inset-bottom,0px)]"
      aria-label="Основная навигация"
    >
      <div className="mx-auto flex w-full max-w-md items-end justify-around px-2 pt-1.5 pb-2 md:max-w-3xl lg:max-w-5xl xl:max-w-6xl">
        {visibleTabs.map(({ id, label, icon: Icon, circle }) => {
          const isActive = active === id

          if (circle) {
            return (
              <button
                key={id}
                type="button"
                onClick={() => (id === 'check' ? onCheck() : onChange(id as TabId))}
                aria-current={isActive ? 'page' : undefined}
                data-active={isActive ? 'true' : 'false'}
                className="relative -mt-6 flex flex-1 flex-col items-center gap-0.5"
              >
                <span
                  className={cn(
                    'tab-circle flex size-14 items-center justify-center rounded-full border',
                    isActive
                      ? 'bg-primary text-primary-foreground border-primary shadow-[0_8px_24px_rgba(78,159,110,0.4)]'
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