'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { useSystemInfo } from '@/service/use-system'
import { getDefaultWorkspaceRecordPath } from '@/config/workspace-permissions'
import { hasAnyPermission } from '@/utils/permissions'

export default function RecordsPage() {
  const router = useRouter()
  const user = useAuthStore((state) => state.user)
  const { data: systemInfo } = useSystemInfo()
  const reportsEnabled = systemInfo?.reports_enabled ?? false

  useEffect(() => {
    if (!user) return
    router.replace(
      getDefaultWorkspaceRecordPath(
        (permissions) => hasAnyPermission(user, permissions),
        reportsEnabled,
      ),
    )
  }, [reportsEnabled, router, user])

  return null
}
