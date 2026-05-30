'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/context/auth-store'

/** Full-viewport shell for canvas editors — auth guard only, no admin chrome. */
export default function EditorLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { token, user } = useAuthStore()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (mounted && !token) {
      router.replace('/login')
    }
  }, [mounted, token, router])

  useEffect(() => {
    if (mounted && token && user?.roles && !user.roles.includes('admin')) {
      router.replace('/workspace/chat')
    }
  }, [mounted, token, user?.roles, router])

  if (!mounted || !token) return null
  if (user?.roles && !user.roles.includes('admin')) return null

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-white">
      {children}
    </div>
  )
}
