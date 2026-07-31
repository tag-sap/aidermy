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

  // page.tsx — обновляем loadHistoryFromServer

  const loadHistoryFromServer = async (token: string) => {
    try {
      const res = await fetch('/api/auth/history', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        if (data.history) {
          setHistory(data.history)
          saveHistory(data.history)
        }
      }
    } catch (error) {
      console.error('Ошибка загрузки истории:', error)
    }
  }

  // ===== ЭФФЕКТЫ - ТОЛЬКО ПРИ ЗАГРУЗКЕ =====
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

  // ТОЛЬКО ОДИН РАЗ ПРИ МОНТИРОВАНИИ
  useEffect(() => {
    const savedProfile = loadProfile()
    setProfile(savedProfile)
    setHistory(loadHistory())
    setHydrated(true)

    if (savedProfile.quizAnswers && Object.keys(savedProfile.quizAnswers).length > 0 && !savedProfile.skinType) {
      const determined = determineSkinTypeFromAnswers(savedProfile.quizAnswers)
      const newProfile = { ...savedProfile, skinType: determined, skinTypeDetermined: determined }
      setProfile(newProfile)
      saveProfile(newProfile)
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

  // ===== ПРОФИЛЬ - ПРОСТО СОХРАНЯЕМ =====
  const handleSaveProfile = async (p: SkinProfile) => {
    setProfile(p)
    saveProfile(p)

    const token = localStorage.getItem('token')
    if (token) {
      try {
        const userRes = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (!userRes.ok) throw new Error('Не удалось получить данные пользователя')

        const userData = await userRes.json()

        await fetch('/api/auth/profile', {
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

        console.log('✅ Профиль сохранён на сервере')
      } catch (error) {
        console.error('Ошибка сохранения профиля:', error)
      }
    }
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
      if (token) {
        try {
          // Получаем user_id из токена или просто шлём запрос
          await fetch('/api/auth/history', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`
            },
            body: JSON.stringify({
              result: fullResult
              // user_id получим на сервере из токена
            })
          })
        } catch (error) {
          console.error('Ошибка сохранения истории:', error)
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
    setTab(newTab)
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
    </>
  )
}