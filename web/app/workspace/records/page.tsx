'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function RecordsPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/workspace/records/sessions')
  }, [router])

  return null
}
