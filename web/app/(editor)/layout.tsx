'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useRefreshCurrentUser } from '@/hooks/use-refresh-current-user'
import { getDefaultAccessiblePath, hasAllPermissions } from '@/utils/permissions'

/** Full-viewport shell for canvas editors — auth guard only, no admin chrome. */
export default function EditorLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { token, user } = useAuthStore()
  const [mounted, setMounted] = useState(false)
  const { isRefreshing: authRefreshing } = useRefreshCurrentUser(mounted)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (mounted && !token) {
      router.replace('/login')
    }
  }, [mounted, token, router])

  useEffect(() => {
    if (
      mounted &&
      token &&
      user &&
      !authRefreshing &&
      !hasAllPermissions(user, ['admin.access', 'call.admin.flow.manage'])
    ) {
      router.replace(getDefaultAccessiblePath(user))
    }
  }, [authRefreshing, mounted, token, user, router])

  if (!mounted || authRefreshing || !token || !user) return null
  if (!hasAllPermissions(user, ['admin.access', 'call.admin.flow.manage'])) return null

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white">
      {children}
    </div>
  )
}
