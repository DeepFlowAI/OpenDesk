'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { hasPermission } from '@/utils/permissions'

export default function SchedulingIndexPage() {
  const router = useRouter()
  const { user } = useAuthStore()

  useEffect(() => {
    if (!user) return
    if (hasPermission(user, 'scheduling.center.manage')) {
      router.replace('/scheduling/board')
    } else if (hasPermission(user, 'scheduling.my.view')) {
      router.replace('/scheduling/me')
    } else {
      router.replace('/403')
    }
  }, [router, user])

  return null
}
