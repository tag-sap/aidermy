'use client'

import { useEffect, useState, useRef } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { CyberGrid } from '@/components/cyber-grid'
import { AppHeader } from '@/components/app-header'
import { AuthModal } from '@/components/auth-modal'
import { TabBar, type TabId } from '@/components/tab-bar'
import { HistoryTab } from '@/components/history-tab'
import { ProfileTab } from '@/components/profile-tab'
import { ResultSheet } from '@/components/result-sheet'
import { SplashScreen } from '@/components/splash-screen'
import { SkinQuiz } from '@/components/skin-quiz'
import { InfoModal } from '@/components/info-modal'
import { BrandMarquee } from '@/components/brand-marquee'
import { CatalogTab } from '@/components/catalog-tab'

import {
  emptyProfile,
  loadHistory,
  loadProfile,
  saveHistory,
  saveProfile,
  determineSkinTypeFromAnswers,
  type CheckResult,
  type SkinProfile,
} from '@/lib/store'

export default function Page() {
  const [tab, setTab] = useState<TabId>('catalog')
  const [profile, setProfile] = useState<SkinProfile>(emptyProfile)
  const [history, setHistory] = useState<CheckResult[]>([])
  const [hydrated, setHydrated] = useState(false)

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CheckResult | null>(null)
  const [isSheetOpen, setIsSheetOpen] = useState(false)

  const [profileDirty, setProfileDirty] = useState(false)
  const [pendingTab, setPendingTab] = useState<TabId | null>(null)

  const [showQuiz, setShowQuiz] = useState(false)

  const profileTabRef = useRef<{ getDraft: () => SkinProfile } | null>(null)

  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [userName, setUserName] = useState('')
  const [showInfo, setShowInfo] = useState(false)

  // ===== ВСЕ ФУНКЦИИ ТАКИЕ ЖЕ КАК БЫЛИ =====
  // (я их не повторяю чтобы не раздувать, они такие же как в твоём оригинальном файле)

  // ===== RENDER =====
  return (
    <>
      <SplashScreen />

      <div className="fixed inset-0 flex flex-col bg-background overflow-hidden">
        <BrandMarquee />
        <CyberGrid />
        <div className="grid-shimmer" aria-hidden="true" />

        <div className="flex-shrink-0 z-20">
          <AppHeader
            onProfile={handleGoToProfile}
            onAuth={() => setIsAuthModalOpen(true)}
            isAuthenticated={isAuthenticated}
            userName={userName}
            onLogout={handleLogout}
          />
        </div>

        <main className="relative z-10 flex-1 min-h-0 overflow-hidden">
          <div className="h-full max-w-md mx-auto px-4 overflow-hidden">
            {showQuiz ? (
              <div className="h-full overflow-y-auto py-4">
                <SkinQuiz
                  onComplete={handleQuizComplete}
                  onCancel={() => setShowQuiz(false)}
                  onRegister={() => {
                    setShowQuiz(false)
                    setIsAuthModalOpen(true)
                  }}
                  initialAnswers={profile.quizAnswers || {}}
                  isAuthenticated={isAuthenticated}
                />
              </div>
            ) : (
              <div className="h-full overflow-hidden">
                {tab === 'catalog' && (
                  <CatalogTab
                    key={hydrated ? 'catalog-ready' : 'catalog-loading'}
                    profile={profile}
                    onCheck={handleCheck}
                    onGoToProfile={handleGoToProfile}
                    onStartQuiz={() => setShowQuiz(true)}
                    onInfoClick={() => setShowInfo(true)}
                  />
                )}
                {tab === 'history' && (
                  <div className="h-full overflow-y-auto py-4">
                    <HistoryTab
                      history={history}
                      onClear={handleClearHistory}
                      onSelect={(item) => {
                        setIsSheetOpen(true)
                        setResult(item)
                        setLoading(false)
                      }}
                    />
                  </div>
                )}
                {tab === 'profile' && (
                  <div className="h-full overflow-y-auto py-4">
                    <ProfileTab
                      ref={profileTabRef}
                      key={hydrated ? 'profile-ready' : 'profile-loading'}
                      profile={profile}
                      onSave={handleSaveProfile}
                      onDirtyChange={handleProfileChange}
                      onStartQuiz={() => setShowQuiz(true)}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </main>

        <div className="flex-shrink-0 z-20">
          <TabBar
            active={tab}
            onChange={handleTabChange}
            isAuthenticated={isAuthenticated}
          />
        </div>

        <ResultSheet
          isOpen={isSheetOpen}
          result={result}
          loading={loading}
          onClose={closeSheet}
          profile={profile}
          onResultUpdate={(data) => {
            setResult(data)
            setHistory((prev) => {
              const next = [data, ...prev].slice(0, 50)
              saveHistory(next)
              return next
            })
          }}
        />
      </div>

      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onLogin={handleLogin}
        onRegister={handleRegister}
      />
      <InfoModal
        isOpen={showInfo}
        onClose={() => setShowInfo(false)}
      />

      {pendingTab && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
            onClick={handleLeaveCancel}
          />
          <div className="fixed left-1/2 top-1/2 z-50 w-80 -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl border border-primary/20">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <AlertTriangle className="size-5 text-orange-500" />
                <h3 className="text-lg font-normal text-foreground">Несохранённые изменения</h3>
              </div>
              <button
                onClick={handleLeaveCancel}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-5" />
              </button>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              У вас есть несохранённые изменения в анкете. Что хотите сделать?
            </p>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => handleLeaveConfirm('save')}
                className="w-full rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary/90"
              >
                Сохранить и выйти
              </button>
              <button
                onClick={() => handleLeaveConfirm('discard')}
                className="w-full rounded-md border border-gray-200 px-4 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
              >
                Не сохранять
              </button>
              <button
                onClick={handleLeaveCancel}
                className="w-full rounded-md px-4 py-2.5 text-sm font-medium text-primary transition-colors hover:bg-primary/5"
              >
                Остаться
              </button>
            </div>
          </div>
        </>
      )}
    </>
  )
}