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
import { ShelfTab } from '@/components/shelf-tab'
import { CatalogTab } from '@/components/catalog-tab'
import { WelcomeTab } from '@/components/welcome-tab'
import { ProductModal } from '@/components/product-modal'
import { CheckModal } from '@/components/check-modal'
import { AccountModal } from '@/components/account-modal'
import { useScrollLock } from '@/lib/use-scroll-lock'

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

const normalizeHistoryItem = (item: any): CheckResult => ({
  id: String(item?.id ?? `${item?.product_name ?? item?.product ?? 'history'}-${item?.created_at ?? Date.now()}`),
  product: item?.product_name ?? item?.product ?? 'Неизвестный продукт',
  skinType: item?.skin_type ?? item?.skinType ?? 'Нормальная',
  score: Number(item?.score ?? 50),
  verdict: item?.verdict ?? 'Требует внимания',
  summary: item?.summary ?? 'Не удалось получить рекомендацию.',
  safe_ingredients: Array.isArray(item?.safe_ingredients) ? item.safe_ingredients : [],
  caution_ingredients: Array.isArray(item?.caution_ingredients) ? item.caution_ingredients : [],
  stats: item?.stats ?? {},
  skin_type_recommendation: item?.skin_type_recommendation ?? '',
  slug: item?.slug ?? '',
  image_url: item?.image_url ?? '',
  createdAt: item?.created_at ? new Date(item.created_at).getTime() : Date.now(),
  active_ingredients: item?.active_ingredients ?? undefined,
  how_to_use: item?.how_to_use ?? undefined,
  expectations: item?.expectations ?? undefined,
})

export default function Page() {
  const [tab, setTab] = useState<TabId>('home')
  const [profile, setProfile] = useState<SkinProfile>(emptyProfile)
  const [history, setHistory] = useState<CheckResult[]>([])
  const [hydrated, setHydrated] = useState(false)

  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CheckResult | null>(null)
  const [isSheetOpen, setIsSheetOpen] = useState(false)

  const [profileDirty, setProfileDirty] = useState(false)
  const [pendingTab, setPendingTab] = useState<TabId | null>(null)

  const [showQuiz, setShowQuiz] = useState(false)
  const [catalogSlug, setCatalogSlug] = useState<string | null>(null)

  const profileTabRef = useRef<{ getDraft: () => SkinProfile } | null>(null)
  const lastHistoryMutationRef = useRef(0)
  const mainRef = useRef<HTMLElement | null>(null)

  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [userName, setUserName] = useState('')
  const [userEmail, setUserEmail] = useState('')
  const [avatarUrl, setAvatarUrl] = useState('')
  const [accountModalOpen, setAccountModalOpen] = useState(false)
  const [showInfo, setShowInfo] = useState(false)
  const [checkModalOpen, setCheckModalOpen] = useState(false)

  // ===== ЗАГРУЗКА С СЕРВЕРА =====
  const loadProfileFromServer = async (token: string) => {
    try {
      const res = await fetch('/api/auth/profile/me', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        if (data.profile) {
          const mergedProfile = { ...emptyProfile, ...loadProfile(), ...data.profile }
          setProfile(mergedProfile)
          saveProfile(mergedProfile)
        }
      }
    } catch (error) {
      console.error('Ошибка загрузки профиля:', error)
    }
  }

  const loadHistoryFromServer = async (token: string) => {
    const now = Date.now()
    if (now - lastHistoryMutationRef.current < 1200) {
      console.log('⏭️ Пропускаю перезагрузку истории после локального удаления')
      return
    }

    try {
      const res = await fetch('/api/auth/history', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        const nextHistory = Array.isArray(data.history) ? data.history.map(normalizeHistoryItem) : []
        setHistory(nextHistory)
        saveHistory(nextHistory)
        return
      }
      setHistory([])
      saveHistory([])
    } catch (error) {
      console.error('Ошибка загрузки истории:', error)
      setHistory([])
      saveHistory([])
    }
  }

  const loadUserFromServer = async (token: string) => {
    try {
      const res = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        const name = data.name || 'Пользователь'
        setUserName(name)
        setUserEmail(data.email || '')
        setAvatarUrl(data.avatar_url || '')
        localStorage.setItem('userName', name)
        localStorage.setItem('userEmail', data.email || '')
        localStorage.setItem('avatarUrl', data.avatar_url || '')
      }
    } catch (error) {
      console.error('Ошибка загрузки пользователя:', error)
    }
  }

  // ===== ЭФФЕКТЫ =====
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      setIsAuthenticated(true)
      setTab('shelf')
      const savedName = localStorage.getItem('userName')
      if (savedName) setUserName(savedName)
      const savedEmail = localStorage.getItem('userEmail')
      if (savedEmail) setUserEmail(savedEmail)
      const savedAvatar = localStorage.getItem('avatarUrl')
      if (savedAvatar) setAvatarUrl(savedAvatar)
      loadProfileFromServer(token)
      loadHistoryFromServer(token)
      loadUserFromServer(token)
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
    const token = localStorage.getItem('token')
    const savedProfile = { ...emptyProfile, ...loadProfile() }
    setProfile(savedProfile)

    if (!token) {
      setHistory([])
      saveHistory([])
      localStorage.removeItem('aidermy:history')
    } else {
      setHistory([])
      saveHistory([])
      localStorage.removeItem('aidermy:history')
    }

    setHydrated(true)

    if (savedProfile.quizAnswers && Object.keys(savedProfile.quizAnswers).length > 0 && !savedProfile.skinType) {
      const determined = determineSkinTypeFromAnswers(savedProfile.quizAnswers)
      const normalized = { ...savedProfile, skinType: determined, skinTypeDetermined: determined }
      setProfile(normalized)
      saveProfile(normalized)
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
      localStorage.setItem('userEmail', data.user?.email || '')
      localStorage.setItem('avatarUrl', data.user?.avatar_url || '')

      setIsAuthenticated(true)
      setUserName(data.user?.name || email.split('@')[0])
      setUserEmail(data.user?.email || '')
      setAvatarUrl(data.user?.avatar_url || '')
      setTab('shelf')

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
    setUserEmail('')
    setAvatarUrl('')
    setProfile(emptyProfile)
    setHistory([])
    saveHistory([])
    localStorage.removeItem('token')
    localStorage.removeItem('userName')
    localStorage.removeItem('userEmail')
    localStorage.removeItem('avatarUrl')
    localStorage.removeItem('aidermy:profile')
    localStorage.removeItem('aidermy:history')
    setTab('home')
    setAccountModalOpen(false)
  }

  const handleAccountSaved = (user: { name: string; avatar_url: string | null }) => {
    setUserName(user.name || '')
    setAvatarUrl(user.avatar_url || '')
    localStorage.setItem('userName', user.name || '')
    localStorage.setItem('avatarUrl', user.avatar_url || '')
  }

  const handleSwitchUser = () => {
    handleLogout()
    setIsAuthModalOpen(true)
  }

  // ===== ПРОФИЛЬ =====
  const handleSaveProfile = async (p: SkinProfile) => {
    const mergedProfile = { ...emptyProfile, ...profile, ...p }
    setProfile(mergedProfile)
    saveProfile(mergedProfile)
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
  const handleClearHistory = async () => {
    lastHistoryMutationRef.current = Date.now()
    setHistory([])
    saveHistory([])

    const token = localStorage.getItem('token')
    if (token) {
      try {
        await fetch('/api/auth/history', {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` }
        })
      } catch (error) {
        console.error('Ошибка очистки истории на сервере:', error)
      }
    }
  }

  const handleDeleteHistoryItem = async (id: string) => {
    const originalHistory = [...history]
    const nextHistory = originalHistory.filter((item) => item.id !== id)
    lastHistoryMutationRef.current = Date.now()
    setHistory(nextHistory)
    saveHistory(nextHistory)

    const token = localStorage.getItem('token')
    if (!token) return

    try {
      const res = await fetch('/api/auth/history/items', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ids: [id] }),
      })

      if (!res.ok) {
        console.error('Ошибка удаления записи истории:', await res.text())
        setHistory(originalHistory)
        saveHistory(originalHistory)
        await loadHistoryFromServer(token)
      }
    } catch (error) {
      console.error('Ошибка удаления записи истории:', error)
      setHistory(originalHistory)
      saveHistory(originalHistory)
    }
  }

  const handleDeleteSelectedHistory = async (ids: string[]) => {
    if (!ids.length) return

    const originalHistory = [...history]
    const nextHistory = originalHistory.filter((item) => !ids.includes(item.id))
    lastHistoryMutationRef.current = Date.now()
    setHistory(nextHistory)
    saveHistory(nextHistory)

    const token = localStorage.getItem('token')
    if (!token) return

    try {
      const res = await fetch('/api/auth/history/items', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ids }),
      })

      if (!res.ok) {
        console.error('Ошибка удаления выбранных записей истории:', await res.text())
        setHistory(originalHistory)
        saveHistory(originalHistory)
        await loadHistoryFromServer(token)
      }
    } catch (error) {
      console.error('Ошибка удаления выбранных записей истории:', error)
      setHistory(originalHistory)
      saveHistory(originalHistory)
    }
  }

  // ===== КВИЗ =====
  const handleQuizComplete = (answers: Record<string, string>, skinType: string) => {
    const updatedProfile = {
      ...emptyProfile,
      ...profile,
      quizAnswers: answers,
      skinType: skinType,
      skinTypeDetermined: skinType,
    }
    setProfile(updatedProfile)
    saveProfile(updatedProfile)
    setShowQuiz(false)
    setTab('shelf')
  }

  // ===== ПРОВЕРКА =====
  const handleCheck = async (product: string, skinType: string) => {
    if (loading) return

    const dedupeKey = `${product.trim()}::${skinType}::${profile.skinType || ''}`
    const lastSavedKey = sessionStorage.getItem('aidermy:lastHistorySave')
    if (lastSavedKey === dedupeKey) {
      return
    }

    setIsSheetOpen(true)
    setResult(null)
    setLoading(true)

    try {
      const currentProfile = { ...emptyProfile, ...profile }
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
            name: currentProfile.name || '',
            age: currentProfile.age || '',
            concerns: currentProfile.concerns || [],
            allergies: currentProfile.allergies || [],
            custom_text: currentProfile.customText || '',
            quiz_answers: currentProfile.quizAnswers || {},
            skin_type_determined: currentProfile.skinTypeDetermined || '',
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
      const image_url = data.image_url || foundProduct?.image_url || ''

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
      sessionStorage.setItem('aidermy:lastHistorySave', `${product.trim()}::${skinType}::${profile.skinType || ''}`)
      setLoading(false)

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
              result: {
                ...fullResult,
                safe_ingredients: fullResult.safe_ingredients || [],
                caution_ingredients: fullResult.caution_ingredients || [],
                image_url: fullResult.image_url || '',
              },
              profile_snapshot: {
                name: profile.name || '',
                age: profile.age || '',
                concerns: profile.concerns || [],
                allergies: profile.allergies || [],
                customText: profile.customText || '',
                quizAnswers: profile.quizAnswers || {},
                skinType: profile.skinType || skinType,
                skinTypeDetermined: profile.skinTypeDetermined || skinType,
              }
            })
          })

          if (historyRes.ok) {
            const saved = await historyRes.json().catch(() => ({}))
            console.log('✅ История сохранена на сервере', saved)
            await loadHistoryFromServer(token)
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
      setResult({
        id: `${Date.now()}-error`,
        product,
        skinType: skinType,
        score: 0,
        verdict: 'Не удалось проверить',
        summary: 'Не удалось получить анализ. Проверьте соединение и настройки AI-сервиса.',
        safe_ingredients: [],
        caution_ingredients: [],
        stats: {},
        slug: '',
        image_url: '',
        createdAt: Date.now(),
      })
      setLoading(false)
    }
  }

  const closeSheet = () => {
    setIsSheetOpen(false)
    setResult(null)
    setLoading(false)
  }

  const handleOpenReport = (data: CheckResult) => {
    setResult(data)
    setLoading(false)
    setIsSheetOpen(true)
  }

  // ===== НАВИГАЦИЯ =====
  const handleGoToProfile = () => {
    if (!isAuthenticated) {
      setIsAuthModalOpen(true)
      return
    }
    setTab('profile')
  }

  const handleGoToHistory = () => {
    if (!isAuthenticated) {
      setIsAuthModalOpen(true)
      return
    }
    setTab('history')
  }

  const handleTabChange = (newTab: TabId) => {
    if (newTab === tab) return

    if ((newTab === 'profile' || newTab === 'shelf') && !isAuthenticated) {
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

  useScrollLock(!!pendingTab)

  // Возвращаем скролл контента наверх при смене вкладки (кроме «Истории»)
  useEffect(() => {
    if (tab !== 'history') {
      mainRef.current?.scrollTo({ top: 0 })
    }
  }, [tab])

  // ===== RENDER =====
  return (
    <>
      <SplashScreen />

      <div className="relative h-dvh overflow-hidden bg-background">
        <BrandMarquee />
        <CyberGrid />
        <div className="grid-shimmer" aria-hidden="true" />

        <div className="relative z-20 flex h-dvh flex-col">
          <main ref={mainRef} className="relative flex-1 min-h-0 overflow-y-auto overflow-x-hidden pb-[calc(6rem+env(safe-area-inset-bottom,0px))]">
            <div className="mx-auto w-full max-w-md px-4 md:max-w-3xl lg:max-w-5xl xl:max-w-6xl">
              <AppHeader
                onOpenAccount={() => setAccountModalOpen(true)}
                onAuth={() => setIsAuthModalOpen(true)}
                isAuthenticated={isAuthenticated}
                userName={userName}
                avatarUrl={avatarUrl}
              />

              {tab !== 'home' && (
                <div className="sticky top-0 z-20 -mx-4 mb-3 border-b border-gray-200/50 bg-background/85 px-4 py-2.5 backdrop-blur-sm">
                  <h1 className="text-xl font-light text-foreground">
                    {tab === 'history' ? 'История' : tab === 'profile' ? 'Профиль' : tab === 'catalog' ? 'Каталог' : 'Моя полка'}
                  </h1>
                </div>
              )}

              {showQuiz ? (
                <div className="py-4">
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
                <div key={tab} className="tab-content">
                  {tab === 'home' && (
                    <WelcomeTab
                      onAuth={() => setIsAuthModalOpen(true)}
                    />
                  )}
                  {tab === 'catalog' && (
                    <CatalogTab
                      onOpenProduct={(slug) => setCatalogSlug(slug)}
                    />
                  )}
                  {tab === 'history' && (
                    <HistoryTab
                      history={history}
                      onClear={handleClearHistory}
                      onDeleteItem={handleDeleteHistoryItem}
                      onDeleteSelected={handleDeleteSelectedHistory}
                      onSelect={(item) => {
                        setIsSheetOpen(true)
                        setResult(item)
                        setLoading(false)
                      }}
                    />
                  )}
                  {tab === 'profile' && (
                    <ProfileTab
                      ref={profileTabRef}
                      key={hydrated ? 'profile-ready' : 'profile-loading'}
                      profile={profile}
                      onSave={handleSaveProfile}
                      onStartQuiz={() => setShowQuiz(true)}
                    />
                  )}
                  {tab === 'shelf' && (
                    <ShelfTab onOpenReport={handleOpenReport} />
                  )}
                </div>
              )}
            </div>
          </main>

          <div className="flex-shrink-0">
            <TabBar
              active={tab}
              onChange={handleTabChange}
              onCheck={() => setCheckModalOpen(true)}
              isAuthenticated={isAuthenticated}
            />
          </div>

          <CheckModal
            isOpen={checkModalOpen}
            onClose={() => setCheckModalOpen(false)}
            onCheck={(product, skinType) => handleCheck(product, profile.skinType || skinType)}
          />

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

          {catalogSlug && (
            <ProductModal
              slug={catalogSlug}
              onClose={() => setCatalogSlug(null)}
              onChanged={() => {}}
              onCheck={(productName) => {
                setCatalogSlug(null)
                handleCheck(productName, profile.skinType || 'Нормальная')
              }}
            />
          )}
        </div>
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

      <AccountModal
        isOpen={accountModalOpen}
        onClose={() => setAccountModalOpen(false)}
        userName={userName}
        userEmail={userEmail}
        avatarUrl={avatarUrl}
        onSaved={handleAccountSaved}
        onLogout={handleLogout}
        onSwitchUser={handleSwitchUser}
      />

      {pendingTab && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4 backdrop-blur-sm animate-modal-backdrop" onClick={handleLeaveCancel}>
          <div className="w-80 max-w-full rounded-lg bg-white p-6 shadow-xl border border-primary/20 animate-modal-panel" onClick={(e) => e.stopPropagation()}>
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
        </div>
      )}
    </>
  )
}