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

  // ===== ЗАГРУЗКА С СЕРВЕРА =====
  const loadProfileFromServer = async (token: string) => {
    try {
      const res = await fetch('/api/auth/profile/me', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        if (data.profile) {
          setProfile(data.profile)
          saveProfile(data.profile)
        }
      }
    } catch (error) {
      console.error('Ошибка загрузки профиля:', error)
    }
  }

  const loadHistoryFromServer = async (token: string) => {
    try {
      const res = await fetch('/api/auth/history', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        console.log('📦 История с сервера:', data)  // <-- ДОБАВЬ ЭТО
        if (data.history && Array.isArray(data.history)) {
          setHistory(data.history)
          saveHistory(data.history)
        }
      }
    } catch (error) {
      console.error('Ошибка загрузки истории:', error)
    }
  }

  // ===== ЭФФЕКТЫ =====
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      setIsAuthenticated(true)
      const savedName = localStorage.getItem('userName')
      if (savedName) setUserName(savedName)
      loadProfileFromServer(token)
      loadHistoryFromServer(token)
    }

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
          loadProfileFromServer(urlToken)
          loadHistoryFromServer(urlToken)
        })
        .catch(() => {
          setUserName('Пользователь')
          localStorage.setItem('userName', 'Пользователь')
        })
      window.history.replaceState({}, '', '/')
    }
  }, [])

  useEffect(() => {
    const savedProfile = loadProfile()
    setProfile(savedProfile)
    setHistory(loadHistory())
    setHydrated(true)

    if (savedProfile.quizAnswers && Object.keys(savedProfile.quizAnswers).length > 0 && !savedProfile.skinType) {
      const determined = determineSkinTypeFromAnswers(savedProfile.quizAnswers)
      setProfile(prev => ({ ...prev, skinType: determined, skinTypeDetermined: determined }))
      saveProfile({ ...savedProfile, skinType: determined, skinTypeDetermined: determined })
    }
  }, [])

  // ===== АВТОРИЗАЦИЯ =====
  const handleLogin = async (email: string, password: string) => {
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })

      if (!res.ok) {
        const error = await res.json()
        throw new Error(error.detail || 'Ошибка входа')
      }

      const data = await res.json()
      const token = data.access_token

      localStorage.setItem('token', token)
      localStorage.setItem('userName', data.user?.name || email.split('@')[0])

      setIsAuthenticated(true)
      setUserName(data.user?.name || email.split('@')[0])

      await loadProfileFromServer(token)
      await loadHistoryFromServer(token)
    } catch (error) {
      console.error('Ошибка входа:', error)
      const message = error instanceof Error ? error.message : 'Не удалось войти'
      alert(message)
    }
  }

  const handleRegister = async (email: string, password: string, name: string) => {
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, name })
      })

      if (!res.ok) {
        const error = await res.json()
        throw new Error(error.detail || 'Ошибка регистрации')
      }

      const data = await res.json()
      alert(data.message || 'Регистрация успешна! Подтвердите email.')
    } catch (error) {
      console.error('Ошибка регистрации:', error)
      const message = error instanceof Error ? error.message : 'Не удалось зарегистрироваться'
      alert(message)
    }
  }

  const handleLogout = () => {
    setIsAuthenticated(false)
    setUserName('')
    setProfile(emptyProfile)
    setHistory([])
    localStorage.removeItem('token')
    localStorage.removeItem('userName')
    localStorage.removeItem('aidermy:profile')
    localStorage.removeItem('aidermy:history')
    setTab('catalog')
  }

  // ===== ПРОФИЛЬ =====
  const handleSaveProfile = async (p: SkinProfile) => {
    setProfile(p)
    saveProfile(p)
    setProfileDirty(false)

    const token = localStorage.getItem('token')
    if (token) {
      try {
        const userRes = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (!userRes.ok) throw new Error('Не удалось получить данные пользователя')

        const userData = await userRes.json()

        const res = await fetch('/api/auth/profile', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`
          },
          body: JSON.stringify({
            user_id: userData.id,
            profile: p
          })
        })

        if (!res.ok) {
          const error = await res.json()
          throw new Error(error.detail || 'Ошибка сохранения')
        }

        console.log('✅ Профиль сохранён на сервере')
      } catch (error) {
        console.error('Ошибка сохранения профиля:', error)
      }
    }
  }

  const handleProfileChange = (dirty: boolean) => {
    setProfileDirty(dirty)
  }

  // ===== ИСТОРИЯ =====
  const handleClearHistory = () => {
    setHistory([])
    saveHistory([])
  }

  // ===== КВИЗ =====
  const handleQuizComplete = (answers: Record<string, string>, skinType: string) => {
    const updatedProfile = {
      ...profile,
      quizAnswers: answers,
      skinType: skinType,
      skinTypeDetermined: skinType,
    }
    setProfile(updatedProfile)
    saveProfile(updatedProfile)
    setShowQuiz(false)
    setTab('catalog')
  }

  // ===== ПРОВЕРКА =====
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
            quiz_answers: profile.quizAnswers || {},
            skin_type_determined: profile.skinTypeDetermined || '',
          },
        }),
      })

      if (!response.ok) {
        throw new Error(`Ошибка: ${response.status}`)
      }

      const data = await response.json()

      const productResponse = await fetch(`/api/products?q=${encodeURIComponent(product)}`)
      const productData = await productResponse.json()
      const foundProduct = productData.products?.find((p: any) => {
        const cleanName = p.name.replace(/\n/g, '').replace(/\s+/g, ' ').trim()
        const cleanProduct = product.replace(/\n/g, '').replace(/\s+/g, ' ').trim()
        return cleanName === cleanProduct || p.slug === product.toLowerCase().replace(/ /g, '-')
      })
      const image_url = foundProduct?.image_url || ''

      const fullResult: CheckResult = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        product: product,
        skinType: skinType,
        score: data.score || 0,
        verdict: data.verdict || 'Нет данных',
        summary: data.summary || 'Не удалось получить рекомендацию.',
        stats: data.stats || {},
        skin_type_recommendation: data.skin_type_recommendation || '',
        safe_ingredients: data.safe_ingredients || [],
        caution_ingredients: data.caution_ingredients || [],
        slug: data.slug || '',
        image_url: image_url,
        createdAt: Date.now(),
        active_ingredients: data.active_ingredients,
        how_to_use: data.how_to_use,
        expectations: data.expectations,
      }

      setResult(fullResult)
      setLoading(false)

      setHistory((prev) => {
        const next = [fullResult, ...prev].slice(0, 50)
        saveHistory(next)
        return next
      })

      // Сохраняем историю на сервер
      const token = localStorage.getItem('token')
      if (token && isAuthenticated) {
        try {
          const historyRes = await fetch('/api/auth/history', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`
            },
            body: JSON.stringify({
              result: fullResult
            })
          })
          if (historyRes.ok) {
            console.log('✅ История сохранена на сервере')
          } else {
            const err = await historyRes.text()
            console.error('❌ Ошибка сохранения истории:', err)
          }
        } catch (error) {
          console.error('❌ Ошибка сохранения истории:', error)
        }
      }

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

  // ===== НАВИГАЦИЯ =====
  const handleGoToProfile = () => {
    if (!isAuthenticated) {
      setIsAuthModalOpen(true)
      return
    }
    setTab('profile')
  }

  const handleTabChange = (newTab: TabId) => {
    if (newTab === tab) return

    if (newTab === 'profile' && !isAuthenticated) {
      setIsAuthModalOpen(true)
      return
    }

    if (profileDirty && tab === 'profile') {
      setPendingTab(newTab)
      return
    }

    setTab(newTab)
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
    }
  }

  const handleLeaveCancel = () => {
    setPendingTab(null)
  }

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

        <main className="relative z-10 flex-1 min-h-0 overflow-hidden pb-22">
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