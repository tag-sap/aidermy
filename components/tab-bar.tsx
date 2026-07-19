'use client'

import { ScanLine, History, User } from 'lucide-react'
import { cn } from '@/lib/utils'

export type TabId = 'checker' | 'history' | 'profile'

const TABS: { id: TabId; label: string; icon: typeof ScanLine }[] = [
  { id: 'checker', label: 'Чекер', icon: ScanLine },
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
  // Фильтруем вкладки - скрываем историю и профиль для неавторизованных
  const visibleTabs = TABS.filter(tab => {
    if (!isAuthenticated && (tab.id === 'history' || tab.id === 'profile')) {
      return false
    }
    return true
  })

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-md"
      aria-label="Основная навигация"
    >
      <div className="panel-strong m-3 flex items-center justify-around rounded-lg px-2 py-2 backdrop-blur-xl">
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