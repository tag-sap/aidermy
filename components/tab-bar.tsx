'use client'

import { useState } from 'react'
import { Search, Home, QrCode } from 'lucide-react'
import { cn } from '@/lib/utils'
import { AnimatedTabIcon } from '@/components/animated-tab-icon'

export type TabId = 'home' | 'catalog' | 'shelf' | 'profile'

interface TabItem {
  id: TabId
  label: string
  icon?: typeof Search
  idle?: string
  hover?: string
  circle?: boolean
}

const TABS: TabItem[] = [
  { id: 'home', label: 'главная', icon: Home, circle: true },
  {
    id: 'catalog',
    label: 'Каталог',
    idle: '/icons/catalog_idle.png',
    hover: '/icons/catalog_hover.gif',
  },
  {
    id: 'shelf',
    label: 'Моя полка',
    idle: '/icons/my_shelf_idle.png',
    hover: '/icons/my_shelf_hover.gif',
  },
  {
    id: 'profile',
    label: 'Профиль',
    idle: '/icons/profile_idle.png',
    hover: '/icons/profile_hover.gif',
  },
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
      {/* Плавающая кнопка «Проверить продукт» — по центру, над вкладкой «Моя полка» */}
      {isAuthenticated && (
        <button
          type="button"
          onClick={onCheck}
          aria-label="Проверить продукт"
          className="group absolute -top-24 left-1/2 z-40 flex size-16 -translate-x-1/2 items-center justify-center rounded-2xl border border-white/30 bg-primary/90 text-primary-foreground shadow-lg backdrop-blur-md transition-transform hover:scale-105"
        >
          <QrCode className="size-7" strokeWidth={1.9} />
          <span className="pointer-events-none absolute -top-9 whitespace-nowrap rounded-lg bg-foreground/90 px-2 py-1 text-[10px] text-background opacity-0 shadow backdrop-blur-sm transition-opacity group-hover:opacity-100">
            Проверить продукт
          </span>
        </button>
      )}

      <div className="mx-auto flex w-full max-w-md items-end justify-around px-2 pt-2 pb-4 md:max-w-3xl lg:max-w-5xl xl:max-w-6xl">
        {visibleTabs.map(tab => {
          const isActive = active === tab.id

          // Вкладки-изображения: каталог / полка / профиль (название уже в картинке).
          if (tab.idle && tab.hover) {
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
                  idleSrc={tab.idle}
                  gifSrc={tab.hover}
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