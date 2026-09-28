'use client'

import { useState } from 'react'
import { Search, Home } from 'lucide-react'
import { cn } from '@/lib/utils'
import { AnimatedTabIcon } from '@/components/animated-tab-icon'

export type TabId = 'home' | 'catalog' | 'shelf' | 'profile'

interface TabItem {
  id: TabId
  label: string
  icon?: typeof Search
  frames?: string[]
  idle?: string
  circle?: boolean
}

const FRAMES = (name: string) => Array.from({ length: 7 }, (_, i) => `/icons/${name}/${i}.gif`)
const IDLE = (name: string) => `/icons/${name}_idle.png`

const TABS: TabItem[] = [
  { id: 'home', label: 'главная', icon: Home, circle: true },
  { id: 'catalog', label: 'Каталог', frames: FRAMES('catalog'), idle: IDLE('catalog') },
  { id: 'shelf', label: 'Моя полка', frames: FRAMES('my_shelf'), idle: IDLE('my_shelf') },
  { id: 'profile', label: 'Профиль', frames: FRAMES('profile'), idle: IDLE('profile') },
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
  const [hoveredId, setHoveredId] = useState<TabId | null>(null)

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
      {/* Плавающая кнопка «Проверить продукт» — по центру, над вкладкой «Моя полка» (только мобилка) */}
      {isAuthenticated && (
        <button
          type="button"
          onClick={onCheck}
          aria-label="Проверить продукт"
          className="absolute -top-24 left-1/2 z-40 flex -translate-x-1/2 items-center justify-center md:hidden"
        >
          <img src="/QRCODE.svg" alt="" className="size-16" draggable={false} />
        </button>
      )}

      <div className="mx-auto flex w-full max-w-md items-end justify-around px-2 pt-2 pb-4 md:max-w-3xl lg:max-w-5xl xl:max-w-6xl">
        {visibleTabs.map(tab => {
          const isActive = active === tab.id

          // Вкладки-анимации: каталог / полка / профиль (кадры storyboard).
          if (tab.frames) {
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onChange(tab.id)}
                aria-label={tab.label}
                aria-current={isActive ? 'page' : undefined}
                data-active={isActive ? 'true' : 'false'}
                data-tour={tab.id}
                onPointerEnter={e => {
                  if (e.pointerType === 'mouse') setHoveredId(tab.id)
                }}
                onPointerLeave={() => setHoveredId(cur => (cur === tab.id ? null : cur))}
                className="relative flex flex-1 flex-col items-center justify-center px-1 py-2"
              >
                <AnimatedTabIcon
                  frames={tab.frames}
                  idleSrc={tab.idle}
                  active={isActive}
                  hovered={hoveredId === tab.id}
                  className="block w-full max-w-[128px]"
                />
              </button>
            )
          }

          const Icon = tab.icon!

          if (tab.circle) {
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onChange(tab.id)}
                aria-current={isActive ? 'page' : undefined}
                data-active={isActive ? 'true' : 'false'}
                data-tour={tab.id}
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
                <span className={cn('font-advaken text-[9px] font-normal leading-none', isActive ? 'text-primary' : 'text-muted-foreground')}>
                  {tab.label}
                </span>
              </button>
            )
          }

          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChange(tab.id)}
              aria-current={isActive ? 'page' : undefined}
              data-active={isActive ? 'true' : 'false'}
              data-tour={tab.id}
              className={cn(
                'nav-link-animated flex flex-1 flex-col items-center gap-0.5 rounded-md px-2 py-1.5 transition-colors',
                isActive ? 'text-primary' : 'text-muted-foreground'
              )}
            >
              <Icon
                className={cn('size-4.5', isActive && 'drop-shadow-[0_0_8px_rgba(108,60,225,0.3)]')}
                strokeWidth={2}
              />
              <span className="font-advaken text-[9px] font-normal leading-none">{tab.label}</span>
            </button>
          )
        })}
      </div>
    </nav>
  )
}