'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

import { getFirstCallIntegrationPath } from '@/app/components/features/call-center/call-integration-tabs'
import { useAuthStore } from '@/context/auth-store'


export default function CallCenterIntegrationsPage() {
  const router = useRouter()
  const user = useAuthStore((state) => state.user)
  useEffect(() => {
    if (user) router.replace(getFirstCallIntegrationPath(user))
  }, [router, user])
  return null
}
