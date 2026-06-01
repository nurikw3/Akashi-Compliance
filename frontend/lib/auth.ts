const AUTH_KEY = 'akashi_auth'

export function setAuth(username: string, password: string): void {
  const token = btoa(`${username}:${password}`)
  setAuthToken(token)
}

export function setAuthToken(token: string): void {
  sessionStorage.setItem(AUTH_KEY, token)
}

/** One-shot login from `#auth=<urlencoded-base64>` (used by scripts/open-compliance.sh). */
export function tryAuthFromHash(): boolean {
  if (typeof window === 'undefined') return false
  const hash = window.location.hash
  if (!hash.startsWith('#auth=')) return false

  const token = decodeURIComponent(hash.slice(6)).trim()
  if (!token) return false

  setAuthToken(token)
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
  return true
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
