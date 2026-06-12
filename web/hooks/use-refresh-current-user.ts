'use client'

import { useEffect } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { useCurrentUser } from '@/service/use-auth'

export function useRefreshCurrentUser(enabled: boolean) {
  const token = useAuthStore((state) => state.token)
  const setUser = useAuthStore((state) => state.setUser)
  const query = useCurrentUser(enabled && Boolean(token))

  useEffect(() => {
    if (query.data) setUser(query.data)
  }, [query.data, setUser])

  return {
    isRefreshing: Boolean(enabled && token && query.isPending),
  }
}
