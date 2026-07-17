'use client'

import { useEffect, useState, useRef } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { CyberGrid } from '@/components/cyber-grid'
import { AppHeader } from '@/components/app-header'
import { AuthModal } from '@/components/auth-modal'
import { TabBar, type TabId } from '@/components/tab-bar'
import { CheckerTab } from '@/components/checker-tab'
import { HistoryTab } from '@/components/history-tab'
import { ProfileTab } from '@/components/profile-tab'
import { ResultSheet } from '@/components/result-sheet'
import { SplashScreen } from '@/components/splash-screen'
import {
  emptyProfile,
  isProfileComplete,
  loadHistory,
  loadProfile,
  mockCheck,
  saveHistory,
  saveProfile,
  type CheckResult,
  type SkinProfile,
} from '@/lib/store'

export default function Page() {
  const [tab, setTab] = useState<TabId>('checker')
  const [profile, setProfile] = useState<SkinProfile>(emptyProfile)
  const [history, setHistory] = useState<CheckResult[]>([])
  const [hydrated, setHydrated] = useState(false)

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CheckResult | null>(null)
  const [isSheetOpen, setIsSheetOpen] = useState(false)

  const [profileDirty, setProfileDirty] = useState(false)
  const [pendingTab, setPendingTab] = useState<TabId | null>(null)

  const profileTabRef = useRef<{ getDraft: () => SkinProfile } | null>(null)

  // === АВТОРИЗАЦИЯ ===
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [userName, setUserName] = useState('')

  // Проверяем токен при загрузке
  useEffect(() => {
    // Проверка токена из localStorage
    const token = localStorage.getItem('token')
    if (token) {
      setIsAuthenticated(true)
      const savedName = localStorage.getItem('userName')
      if (savedName) setUserName(savedName)
    }

    // Обработка токена из URL (Google OAuth)
    const urlParams = new URLSearchParams(window.location.search)
    const urlToken = urlParams.get('token')
    if (urlToken) {
      localStorage.setItem('token', urlToken)
      setIsAuthenticated(true)
      fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${urlToken}` }
      })
        .then(res => res.json())
        .then(data => {
          const name = data.name || 'Пользователь'
          setUserName(name)
          localStorage.setItem('userName', name)
        })
        .catch(() => {
          setUserName('Пользователь')
          localStorage.setItem('userName', 'Пользователь')
        })
      window.history.replaceState({}, '', '/')
    }
  }, [])

  useEffect(() => {
    setProfile(loadProfile())
    setHistory(loadHistory())
    setHydrated(true)
  }, [])

  // === ОБРАБОТЧИКИ АВТОРИЗАЦИИ ===
  const handleLogin = async (email: string, password: string) => {
    console.log('Login:', email, password)
    setIsAuthenticated(true)
    setUserName(email.split('@')[0])
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('userName', email.split('@')[0])
  }

  const handleRegister = async (email: string, password: string, name: string) => {
    console.log('Register:', email, password, name)
    setIsAuthenticated(true)
    setUserName(name || email.split('@')[0])
    localStorage.setItem('token', 'fake-token')
    localStorage.setItem('userName', name || email.split('@')[0])
  }

  const handleLogout = () => {
    setIsAuthenticated(false)
    setUserName('')
    localStorage.removeItem('token')
    localStorage.removeItem('userName')
  }

  const handleSaveProfile = (p: SkinProfile) => {
    setProfile(p)
    saveProfile(p)
    setProfileDirty(false)
  }

  const handleProfileChange = (dirty: boolean) => {
    setProfileDirty(dirty)
  }

  const handleClearHistory = () => {
    setHistory([])
    saveHistory([])
  }

  const handleCheck = async (product: string, skinType: string) => {
    setIsSheetOpen(true)
    setResult(null)
    setLoading(true)

    try {
      const response = await fetch('/api/check', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(isAuthenticated && { Authorization: `Bearer ${localStorage.getItem('token')}` }),
        },
        body: JSON.stringify({
          product_name: product,
          skin_type: skinType,
          profile: {
            name: profile.name || '',
            age: profile.age || '',
            concerns: profile.concerns || [],
            allergies: profile.allergies || [],
            custom_text: profile.customText || '',
          },
        }),
      })

      if (!response.ok) {
        throw new Error(`Ошибка: ${response.status}`)
      }

      const data = await response.json()

      const fullResult = {
        ...data,
        product: product,
        skinType: skinType,
        createdAt: Date.now(),
      }

      setResult(fullResult)
      setLoading(false)

      setHistory((prev) => {
        const next = [fullResult, ...prev].slice(0, 50)
        saveHistory(next)
        return next
      })

    } catch (error) {
      console.error('Ошибка проверки:', error)
      setLoading(false)
    }
  }

  const closeSheet = () => {
    setIsSheetOpen(false)
    setResult(null)
    setLoading(false)
  }

  const handleGoToProfile = () => {
    if (!isAuthenticated) {
      setIsAuthModalOpen(true)
      return
    }
    setTab('profile')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleTabChange = (newTab: TabId) => {
    if (newTab === tab) return

    if (profileDirty && tab === 'profile') {
      setPendingTab(newTab)
      return
    }

    setTab(newTab)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleLeaveConfirm = (action: 'save' | 'discard') => {
    if (action === 'save' && profileTabRef.current) {
      const draft = profileTabRef.current.getDraft()
      handleSaveProfile(draft)
    }

    setProfileDirty(false)
    setPendingTab(null)

    if (pendingTab) {
      setTab(pendingTab)
      setPendingTab(null)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const handleLeaveCancel = () => {
    setPendingTab(null)
  }

  return (
    <>
      <SplashScreen />

      <div className="relative min-h-screen overflow-hidden bg-background">
        <CyberGrid />
        <div className="grid-shimmer" aria-hidden="true" />

        <AppHeader
          onProfile={handleGoToProfile}
          onAuth={() => setIsAuthModalOpen(true)}
          isAuthenticated={isAuthenticated}
          userName={userName}
          onLogout={handleLogout}
        />

        <main className="relative z-10 mx-auto flex min-h-screen max-w-md flex-col px-5 pb-36 pt-4">
          <div className="mt-6 flex-1">
            <div className="tab-content-wrapper">
              {tab === 'checker' && (
                <div className="tab-content">
                  <CheckerTab
                    key={hydrated ? 'checker-ready' : 'checker-loading'}
                    profile={profile}
                    profileComplete={hydrated && isProfileComplete(profile)}
                    onCheck={handleCheck}
                    onGoToProfile={handleGoToProfile}
                  />
                </div>
              )}
              {tab === 'history' && (
                <div className="tab-content">
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
                <div className="tab-content">
                  <ProfileTab
                    ref={profileTabRef}
                    key={hydrated ? 'profile-ready' : 'profile-loading'}
                    profile={profile}
                    onSave={handleSaveProfile}
                    onDirtyChange={handleProfileChange}
                  />
                </div>
              )}
            </div>
          </div>
        </main>

        <TabBar active={tab} onChange={handleTabChange} />

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

      {/* === МОДАЛКА АВТОРИЗАЦИИ === */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        onLogin={handleLogin}
        onRegister={handleRegister}
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
                <h3 className="text-lg font-semibold text-foreground">Несохранённые изменения</h3>
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