'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { type ComponentType } from 'react'
import {
  IconActivity,
  IconChartBar,
  IconChartHistogram,
  IconChecklist,
  IconHeadset,
  IconInbox,
  IconMessage,
  IconMessageCircle,
  IconPhone,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useSystemInfo } from '@/service/use-system'
import { t } from '@/utils/i18n'
import {
  WORKSPACE_RECORD_NAV_GROUPS,
  isWorkspacePathMatch,
  type WorkspaceRecordIconKey,
} from '@/config/workspace-permissions'
import { hasAllPermissions, hasAnyPermission, hasPermission } from '@/utils/permissions'

const RECORD_NAV_ICONS: Record<WorkspaceRecordIconKey, ComponentType<{ size?: number; className?: string }>> = {
  onlineMonitor: IconActivity,
  sessions: IconMessageCircle,
  offlineMessages: IconInbox,
  sessionReports: IconChartBar,
  callMonitor: IconHeadset,
  calls: IconPhone,
  callReports: IconChartBar,
  smsRecords: IconMessage,
  dashboards: IconChartHistogram,
  quality: IconChecklist,
}

export function ServiceOperationsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const { data: systemInfo } = useSystemInfo()
  const reportsEnabled = systemInfo?.reports_enabled ?? false

  const visibleNavGroups = WORKSPACE_RECORD_NAV_GROUPS
    .map((group) => ({
      items: group.items.filter((item) => {
        if (item.requiresReports && !reportsEnabled) return false
        return item.requireAll
          ? hasAllPermissions(user, item.permissions)
          : hasAnyPermission(user, item.permissions)
      }),
    }))
    .filter((group) => group.items.length > 0)

  return (
    <div className="flex h-full min-h-0">
      <nav className="flex w-[180px] shrink-0 flex-col border-r border-border bg-neutral-100 px-3 py-4">
        <div className="flex flex-col gap-3">
          {visibleNavGroups.map((group, groupIndex) => (
            <div
              key={groupIndex}
              className={cn(
                'flex flex-col gap-0.5',
                groupIndex > 0 && 'border-t border-border/70 pt-3'
              )}
            >
              {group.items.map((item) => {
                const active = isWorkspacePathMatch(pathname, item.href)
                const Icon = RECORD_NAV_ICONS[item.iconKey]
                const visibleChildren = active
                  ? item.children?.filter((child) => hasPermission(user, child.permission))
                  : undefined

                return (
                  <div key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        'flex items-center gap-2.5 px-3 py-2 text-sm transition-colors',
                        active
                          ? 'rounded-md bg-background font-semibold text-foreground shadow-sm'
                          : 'rounded-lg text-muted-foreground hover:bg-background/60 hover:text-foreground'
                      )}
                    >
                      <Icon size={18} className="shrink-0" />
                      {t(item.labelKey, locale)}
                    </Link>
                    {visibleChildren?.length ? (
                      <div className="mt-1 flex flex-col gap-0.5 pl-6">
                        {visibleChildren.map((child) => {
                          const childActive = isWorkspacePathMatch(pathname, child.href)
                          return (
                            <Link
                              key={child.href}
                              href={child.href}
                              className={cn(
                                'rounded-md px-3 py-1.5 text-sm transition-colors',
                                childActive
                                  ? 'font-medium text-foreground'
                                  : 'text-muted-foreground hover:bg-background/60 hover:text-foreground'
                              )}
                            >
                              {t(child.labelKey, locale)}
                            </Link>
                          )
                        })}
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </nav>

      <div className="min-h-0 flex-1 overflow-hidden bg-background">
        {children}
      </div>
    </div>
  )
}
