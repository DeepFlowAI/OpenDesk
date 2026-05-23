'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { IconActivity, IconChartBar, IconMessageCircle } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { useSystemInfo } from '@/service/use-system'
import { t } from '@/utils/i18n'

type SubNavItem = {
  labelKey: string
  href: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  /** Optional gate; when false, the item is hidden. */
  visible?: boolean
}

export default function RecordsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { locale } = useLocaleStore()
  const { data: systemInfo } = useSystemInfo()
  const reportsEnabled = systemInfo?.reports_enabled ?? false

  const SUB_NAV_ITEMS: SubNavItem[] = [
    { labelKey: 'ws.records.nav.sessions', href: '/workspace/records/sessions', icon: IconMessageCircle },
    { labelKey: 'ws.records.nav.sessionReports', href: '/workspace/records/session-reports', icon: IconChartBar, visible: reportsEnabled },
    { labelKey: 'ws.records.nav.onlineMonitor', href: '/workspace/records/online-monitor', icon: IconActivity, visible: reportsEnabled },
  ]

  return (
    <div className="flex h-full min-h-0">
      {/* Secondary sidebar — matches .pen: neutral gray (#F5F5F5) */}
      <nav className="flex w-[180px] shrink-0 flex-col border-r border-border bg-neutral-100 px-3 py-4">
        <div className="flex flex-col gap-0.5">
          {SUB_NAV_ITEMS.filter((item) => item.visible !== false).map((item) => {
            const active = pathname.startsWith(item.href)
            const Icon = item.icon
            return (
              <Link
                key={item.href}
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
            )
          })}
        </div>
      </nav>

      {/* Main list area — white panel next to nav */}
      <div className="min-h-0 flex-1 overflow-hidden bg-background">
        {children}
      </div>
    </div>
  )
}
