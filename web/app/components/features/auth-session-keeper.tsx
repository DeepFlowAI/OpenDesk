'use client'

import { useTokenRefresh } from '@/hooks/use-token-refresh'

export function AuthSessionKeeper() {
  useTokenRefresh()
  return null
}
