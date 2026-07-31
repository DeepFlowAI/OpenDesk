import { useAuthStore } from '@/context/auth-store'

/** Read the shared browser token without touching the in-memory store. */
export function readStoredToken(): string | null {
  try {
    return localStorage.getItem('auth_token')
  } catch {
    return null
  }
}

/**
 * Before clearing auth because a token was rejected, check whether storage
 * already holds a different (newer) token from another tab. If so, adopt it
 * and return true so the caller can skip the logout.
 */
export function adoptNewerTokenIfAny(staleToken: string | null): boolean {
  const stored = readStoredToken()
  if (!stored || !staleToken || stored === staleToken) return false
  useAuthStore.setState({ token: stored })
  return true
}
