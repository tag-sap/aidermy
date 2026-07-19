'use client'

import { useState } from 'react'
import { X, Mail, Lock, User, Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AuthModalProps {
    isOpen: boolean
    onClose: () => void
    onLogin: (email: string, password: string) => Promise<void>
    onRegister: (email: string, password: string, name: string) => Promise<void>
}

export function AuthModal({ isOpen, onClose, onLogin, onRegister }: AuthModalProps) {
    const [mode, setMode] = useState<'login' | 'register' | 'success'>('login')
    const [email, setEmail] = useState('')
    const [password, setPassword] = useState('')
    const [name, setName] = useState('')
    const [showPassword, setShowPassword] = useState(false)
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState('')
    const [successMessage, setSuccessMessage] = useState('')

    if (!isOpen) return null

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setError('')
        setIsLoading(true)

        try {
            if (mode === 'login') {
                await onLogin(email, password)
                onClose()
            } else {
                const response = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password, name }),
                })

                const data = await response.json()

                if (!response.ok) {
                    throw new Error(data.detail || 'Ошибка регистрации')
                }

                setSuccessMessage(data.message || 'Письмо с подтверждением отправлено на ваш email!')
                setMode('success')
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Что-то пошло не так')
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <>
            <div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm" onClick={onClose} />

            <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-2xl border border-primary/10">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-normal text-foreground">
                        {mode === 'login' ? 'Вход в аккаунт' : mode === 'register' ? 'Создать аккаунт' : 'Проверьте почту'}
                    </h2>
                    <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
                        <X className="size-5" />
                    </button>
                </div>

                {mode === 'success' ? (
                    <div className="text-center py-4">
                        <div className="text-4xl mb-3">📧</div>
                        <h3 className="text-lg font-normal text-foreground">Проверьте почту!</h3>
                        <p className="text-sm text-muted-foreground mt-2">{successMessage}</p>
                        <button
                            onClick={onClose}
                            className="mt-4 w-full rounded-md bg-primary py-2.5 text-sm font-normal text-white hover:bg-primary/90"
                        >
                            Закрыть
                        </button>
                    </div>
                ) : (
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {mode === 'register' && (
                            <div>
                                <label className="text-sm font-normal text-foreground">Имя</label>
                                <div className="relative mt-1">
                                    <User className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                                    <input
                                        type="text"
                                        value={name}
                                        onChange={(e) => setName(e.target.value)}
                                        placeholder="Алексей"
                                        required
                                        className="w-full rounded-md border border-primary/15 bg-white/50 px-3 py-2.5 pl-9 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                                    />
                                </div>
                            </div>
                        )}

                        <div>
                            <label className="text-sm font-normal text-foreground">Email</label>
                            <div className="relative mt-1">
                                <Mail className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="you@example.com"
                                    required
                                    className="w-full rounded-md border border-primary/15 bg-white/50 px-3 py-2.5 pl-9 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                                />
                            </div>
                        </div>

                        <div>
                            <label className="text-sm font-normal text-foreground">Пароль</label>
                            <div className="relative mt-1">
                                <Lock className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                                <input
                                    type={showPassword ? 'text' : 'password'}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder={mode === 'login' ? '••••••••' : 'Минимум 6 символов'}
                                    required
                                    minLength={6}
                                    className="w-full rounded-md border border-primary/15 bg-white/50 px-3 py-2.5 pl-9 pr-10 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                >
                                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                                </button>
                            </div>
                        </div>

                        {error && (
                            <div className="rounded-md bg-red-50 p-3 text-sm text-red-600">
                                {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={isLoading}
                            className={cn(
                                'w-full rounded-md bg-primary py-2.5 text-sm font-normal text-white transition-colors',
                                isLoading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-primary/90'
                            )}
                        >
                            {isLoading ? 'Загрузка...' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}
                        </button>
                    </form>
                )}

                {mode !== 'success' && (
                    <>
                        {/* === КНОПКА GOOGLE === */}
                        <div className="relative my-4">
                            <div className="absolute inset-0 flex items-center">
                                <div className="w-full border-t border-gray-200"></div>
                            </div>
                            <div className="relative flex justify-center text-xs text-muted-foreground">
                                <span className="bg-white px-2">или</span>
                            </div>
                        </div>

                        <button
                            onClick={() => window.location.href = '/api/auth/google'}
                            className="w-full flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white py-2.5 text-sm font-normal text-gray-700 transition-colors hover:bg-gray-50"
                        >
                            <svg className="w-5 h-5" viewBox="0 0 24 24">
                                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                            </svg>
                            Войти через Google
                        </button>

                        {/* Переключение режима */}
                        <div className="mt-4 text-center text-sm text-muted-foreground">
                            {mode === 'login' ? (
                                <>
                                    Нет аккаунта?{' '}
                                    <button onClick={() => { setMode('register'); setError(''); }} className="text-primary hover:underline font-normal">
                                        Зарегистрироваться
                                    </button>
                                </>
                            ) : (
                                <>
                                    Уже есть аккаунт?{' '}
                                    <button onClick={() => { setMode('login'); setError(''); }} className="text-primary hover:underline font-normal">
                                        Войти
                                    </button>
                                </>
                            )}
                        </div>
                    </>
                )}
            </div>
        </>
    )
}