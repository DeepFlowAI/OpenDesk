'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'


export default function CallCenterIntegrationsPage() {
  const router = useRouter()
  useEffect(() => router.replace('/call-center/integrations/embedded-call'), [router])
  return null
}
