'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useRefreshCurrentUser } from '@/hooks/use-refresh-current-user'
import { getDefaultAccessiblePath, hasAllPermissions } from '@/utils/permissions'
import { getAdminRouteRule } from '@/config/admin-permissions'

const DEFAULT_EDITOR_PERMISSIONS = ['admin.access']

/** Full-viewport shell for canvas editors — auth guard only, no admin chrome. */
export default function EditorLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user } = useAuthStore()
  const [mounted, setMounted] = useState(false)
  const { isRefreshing: authRefreshing } = useRefreshCurrentUser(mounted)

  const requiredPermissions = getAdminRouteRule(pathname)?.permissions ?? DEFAULT_EDITOR_PERMISSIONS

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
      !hasAllPermissions(user, requiredPermissions)
    ) {
      router.replace(getDefaultAccessiblePath(user))
    }
  }, [authRefreshing, mounted, token, user, router, requiredPermissions])

  if (!mounted || authRefreshing || !token || !user) return null
  if (!hasAllPermissions(user, requiredPermissions)) return null

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white">
      {children}
    </div>
  )
}
