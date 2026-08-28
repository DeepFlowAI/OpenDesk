'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { IconCalendarStats } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { UserDropdown } from '@/app/components/features/user-dropdown'
import { useAuthStore } from '@/context/auth-store'
import { hasPermission } from '@/utils/permissions'
import { cn } from '@/lib/utils'

export function SchedulingShell({ children }: { children: ReactNode }) {
  const { locale } = useLocaleStore()
  const { user } = useAuthStore()
  const pathname = usePathname()
  const canViewMine = hasPermission(user, 'scheduling.my.view')
  const canManage = hasPermission(user, 'scheduling.center.manage')
  const tabs = [
    ...(canViewMine ? [{ key: 'scheduling.tab.my', href: '/scheduling/me' }] : []),
    ...(canManage
      ? [
          { key: 'scheduling.tab.board', href: '/scheduling/board' },
          { key: 'scheduling.tab.shifts', href: '/scheduling/shifts' },
          { key: 'scheduling.tab.rules', href: '/scheduling/rules' },
        ]
      : []),
  ]

  return (
    <div className="flex h-screen flex-col bg-muted/30">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-6">
        <div className="flex h-full items-center gap-3">
          <IconCalendarStats size={22} className="text-foreground" />
          <span className="text-base font-semibold">{t('scheduling.shell.title', locale)}</span>
          <nav className="ml-6 flex h-full items-center gap-1">
            {tabs.map((tab) => {
              const active = pathname.startsWith(tab.href)
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className={cn(
                    '-mb-px flex h-full items-center border-b-2 px-3 text-sm transition-colors',
                    active
                      ? 'border-primary font-semibold text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t(tab.key, locale)}
                </Link>
              )
            })}
          </nav>
        </div>
        <UserDropdown />
      </header>
      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
    </div>
  )
}
