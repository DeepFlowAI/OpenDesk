'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function ChannelsPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/channels/web')
  }, [router])

  return null
}
