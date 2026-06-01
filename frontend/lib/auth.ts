const AUTH_KEY = 'akashi_auth'

export function setAuth(username: string, password: string): void {
  const token = btoa(`${username}:${password}`)
  sessionStorage.setItem(AUTH_KEY, token)
}

export function clearAuth(): void {
  sessionStorage.removeItem(AUTH_KEY)
}

export function getAuthHeader(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  const token = sessionStorage.getItem(AUTH_KEY)
  if (!token) return {}
  return { Authorization: `Basic ${token}` }
}

export function isAuthenticated(): boolean {
  if (typeof window === 'undefined') return false
  return !!sessionStorage.getItem(AUTH_KEY)
}
