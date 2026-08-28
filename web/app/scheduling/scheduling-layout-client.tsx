'use client'

import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useRefreshCurrentUser } from '@/hooks/use-refresh-current-user'
import { useApplyAccountLocale } from '@/hooks/use-apply-account-locale'
import { hasAnyPermission, hasPermission } from '@/utils/permissions'
import { SchedulingShell } from '@/app/components/features/scheduling/scheduling-shell'

export default function SchedulingLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user } = useAuthStore()
  const [mounted, setMounted] = useState(false)
  const { isRefreshing: authRefreshing } = useRefreshCurrentUser(mounted)
  useApplyAccountLocale()

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (mounted && !token) {
      router.replace('/login')
    }
  }, [mounted, token, router])

  useEffect(() => {
    if (!mounted || !token || !user || authRefreshing) return
    const canViewMine = hasPermission(user, 'scheduling.my.view')
    const canManage = hasPermission(user, 'scheduling.center.manage')
    if (!hasAnyPermission(user, ['scheduling.my.view', 'scheduling.center.manage'])) {
      router.replace('/403')
      return
    }
    if (pathname.startsWith('/scheduling/me') && !canViewMine) {
      router.replace('/403')
      return
    }
    if (pathname !== '/scheduling' && !pathname.startsWith('/scheduling/me') && !canManage) {
      router.replace('/403')
    }
  }, [authRefreshing, mounted, pathname, token, user, router])

  if (!mounted || authRefreshing || !token || !user) return null
  const canViewMine = hasPermission(user, 'scheduling.my.view')
  const canManage = hasPermission(user, 'scheduling.center.manage')
  if (!hasAnyPermission(user, ['scheduling.my.view', 'scheduling.center.manage'])) return null
  if (pathname.startsWith('/scheduling/me') && !canViewMine) return null
  if (pathname !== '/scheduling' && !pathname.startsWith('/scheduling/me') && !canManage) return null

  return <SchedulingShell>{children}</SchedulingShell>
}
