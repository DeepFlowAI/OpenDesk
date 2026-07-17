'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { usePathname, useRouter } from 'next/navigation'

import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useRefreshCurrentUser } from '@/hooks/use-refresh-current-user'
import { hasPermission } from '@/utils/permissions'

export default function H5TicketsLayout({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user } = useAuthStore()
  const { locale } = useLocaleStore()
  const [mounted, setMounted] = useState(false)
  const { isRefreshing } = useRefreshCurrentUser(mounted)

  useEffect(() => setMounted(true), [])

  useEffect(() => {
    if (!mounted || token) return
    const target = `${pathname}${window.location.search}`
    router.replace(`/login?redirect=${encodeURIComponent(target)}`)
  }, [mounted, pathname, router, token])

  if (!mounted || isRefreshing || !token || !user) {
    return <H5PageLoading label={locale === 'zh' ? '加载中…' : 'Loading…'} />
  }

  if (!hasPermission(user, 'ticket.workspace.view')) {
    return (
      <div className="mx-auto flex h-[100dvh] max-w-[480px] flex-col items-center justify-center gap-3 bg-background px-6 text-center">
        <p className="font-display text-lg font-semibold">403</p>
        <p className="text-sm text-muted-foreground">
          {locale === 'zh' ? '无权访问 H5 工单工作台' : 'You do not have access to the H5 ticket workspace'}
        </p>
      </div>
    )
  }

  return (
    <div className="min-h-[100dvh] bg-surface">
      <div className="mx-auto h-[100dvh] max-w-[480px] overflow-hidden bg-background shadow-sm">
        {children}
      </div>
    </div>
  )
}

function H5PageLoading({ label }: { label: string }) {
  return (
    <div className="mx-auto flex h-[100dvh] max-w-[480px] items-center justify-center bg-background">
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  )
}
