'use client'

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Loader2, Lock } from 'lucide-react'
import { checkHealth } from '@/lib/api'
import { clearAuth, isAuthenticated, setAuth } from '@/lib/auth'

export function AuthGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [authed, setAuthed] = useState(false)
  const [username, setUsername] = useState('nurikw3')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const verifySession = useCallback(async () => {
    if (!isAuthenticated()) {
      setAuthed(false)
      setReady(true)
      return
    }
    try {
      const ok = await checkHealth()
      setAuthed(ok)
      if (!ok) clearAuth()
    } catch {
      clearAuth()
      setAuthed(false)
    } finally {
      setReady(true)
    }
  }, [])

  useEffect(() => {
    void verifySession()
  }, [verifySession])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError(null)
    setAuth(username.trim(), password)
    try {
      const ok = await checkHealth()
      if (!ok) {
        clearAuth()
        setError('Неверный логин или пароль')
        setAuthed(false)
        return
      }
      setAuthed(true)
      setPassword('')
    } catch {
      clearAuth()
      setError('Неверный логин или пароль')
      setAuthed(false)
    } finally {
      setLoading(false)
    }
  }

  if (!ready) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-neutral-400" />
      </div>
    )
  }

  if (!authed) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center px-4">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-sm bg-white border border-neutral-200 rounded-2xl p-8 shadow-sm"
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-neutral-900 text-white flex items-center justify-center">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-neutral-900">Compliance Workspace</h1>
              <p className="text-sm text-neutral-500">Вход в систему</p>
            </div>
          </div>

          <label className="block text-sm font-medium text-neutral-700 mb-1.5">Логин</label>
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full mb-4 px-3 py-2 border border-neutral-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
            required
          />

          <label className="block text-sm font-medium text-neutral-700 mb-1.5">Пароль</label>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full mb-4 px-3 py-2 border border-neutral-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
            required
          />

          {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-neutral-900 hover:bg-neutral-800 disabled:opacity-50 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {loading ? 'Проверка…' : 'Войти'}
          </button>
        </form>
      </div>
    )
  }

  return <>{children}</>
}
