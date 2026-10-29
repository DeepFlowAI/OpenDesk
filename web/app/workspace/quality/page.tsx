'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'
import { hasPermission } from '@/utils/permissions'

export default function QualityHomePage() {
  const router = useRouter()
  const user = useAuthStore((state) => state.user)
  useEffect(() => {
    if (!user) return
    if (hasPermission(user, 'quality.online.plan.view')) router.replace('/workspace/quality/online/plans')
    else if (hasPermission(user, 'quality.online.scorecard.view')) router.replace('/workspace/quality/online/scorecards')
    else router.replace('/403')
  }, [router, user])
  return null
}
