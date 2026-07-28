'use client'

import { ScanLine, History, User, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
export type TabId = 'checker' | 'catalog' | 'history' | 'profile'

const TABS: { id: TabId; label: string; icon: typeof ScanLine }[] = [
  { id: 'checker', label: 'Чекер', icon: ScanLine },
  { id: 'catalog', label: 'Каталог', icon: Search },
  { id: 'history', label: 'История', icon: History },
  { id: 'profile', label: 'Профиль', icon: User },
]

export function TabBar({
  active,
  onChange,
  isAuthenticated = false,
}: {
  active: TabId
  onChange: (id: TabId) => void
  isAuthenticated?: boolean
}) {
  const visibleTabs = TABS.filter(tab => {
    if (!isAuthenticated && (tab.id === 'history' || tab.id === 'profile')) {
      return false
    }
    return true
  })

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-30 bg-background border-t border-gray-200"
      aria-label="Основная навигация"
    >
      <div className="mx-auto max-w-md flex items-center justify-around px-2 py-2">
        {visibleTabs.map(({ id, label, icon: Icon }) => {
          const isActive = active === id
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              aria-current={isActive ? 'page' : undefined}
              className={cn(
                'flex flex-1 flex-col items-center gap-1 rounded-md px-2 py-2 transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground',
              )}
            >
              <Icon
                className={cn('size-5', isActive && 'drop-shadow-[0_0_8px_rgba(255,79,0,0.6)]')}
                strokeWidth={2}
              />
              <span className="text-[11px] font-normal">{label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}