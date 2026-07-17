'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function EngagementIndexPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/workspace/engagement/outbound-tasks')
  }, [router])

  return null
}
