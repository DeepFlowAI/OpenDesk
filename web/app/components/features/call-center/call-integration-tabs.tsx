'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import {
  CALL_EMBED_MANAGE_PERMISSION,
  CALL_EVENT_SUBSCRIPTION_MANAGE_PERMISSION,
  isAdminPathMatch,
} from '@/config/admin-permissions'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { hasPermission } from '@/utils/permissions'

type PermissionUser = Parameters<typeof hasPermission>[0]

export const CALL_INTEGRATION_TABS = [
  {
    href: '/call-center/integrations/embedded-call',
    permission: CALL_EMBED_MANAGE_PERMISSION,
    label: { zh: '嵌入式通话', en: 'Embedded calling' },
  },
  {
    href: '/call-center/integrations/event-subscriptions',
    permission: CALL_EVENT_SUBSCRIPTION_MANAGE_PERMISSION,
    label: { zh: '事件订阅', en: 'Event subscriptions' },
  },
] as const

export function getFirstCallIntegrationPath(user: PermissionUser): string {
  return CALL_INTEGRATION_TABS.find((tab) => hasPermission(user, tab.permission))?.href ?? '/403'
}

export function CallIntegrationTabs({
  onNavigate,
  className,
}: {
  /** Return false to cancel navigation (e.g. when the form has unsaved changes). */
  onNavigate?: (href: string) => boolean
  className?: string
}) {
  const pathname = usePathname()
  const user = useAuthStore((state) => state.user)
  const { locale } = useLocaleStore()
  const tabs = CALL_INTEGRATION_TABS.filter((tab) => hasPermission(user, tab.permission))

  return (
    <nav
      aria-label={locale === 'zh' ? '通话集成' : 'Call integrations'}
      className={cn('flex h-10 items-end gap-6 border-b border-border text-sm', className)}
    >
      {tabs.map((tab) => {
        const active = isAdminPathMatch(pathname, tab.href)
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            onClick={(event) => {
              if (onNavigate && !active && !onNavigate(tab.href)) event.preventDefault()
            }}
            className={cn(
              'flex h-10 items-center border-b-2 px-1 transition-colors',
              active
                ? 'border-foreground font-semibold text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {locale === 'zh' ? tab.label.zh : tab.label.en}
          </Link>
        )
      })}
    </nav>
  )
}
