'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { IconClipboardList, IconMessage2, IconPhoneOutgoing, IconTemplate } from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { hasAnyPermission } from '@/utils/permissions'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

const items = [
  {
    href: '/workspace/engagement/outbound-tasks',
    labelKey: 'ws.engagement.nav.manual',
    icon: IconClipboardList,
    permissions: ['engagement.outbound_task.manage', 'engagement.outbound_task.create'],
  },
  {
    href: '/workspace/engagement/auto-outbound-tasks',
    labelKey: 'ws.engagement.nav.auto',
    icon: IconPhoneOutgoing,
    permissions: ['engagement.auto_outbound_task.manage', 'engagement.auto_outbound_task.create'],
  },
  {
    href: '/workspace/engagement/outbound-task-templates',
    labelKey: 'ws.engagement.nav.templates',
    icon: IconTemplate,
    permissions: ['engagement.outbound_task.template.manage'],
  },
  {
    href: '/workspace/engagement/sms-tasks',
    labelKey: 'ws.engagement.nav.sms',
    icon: IconMessage2,
    permissions: ['engagement.sms_task.manage', 'engagement.sms_task.create'],
  },
]

export default function EngagementLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const visibleItems = items.filter((item) => hasAnyPermission(user, item.permissions))

  return (
    <div className="flex h-full min-h-0">
      <nav className="flex w-[180px] shrink-0 flex-col border-r border-border bg-neutral-100 px-3 py-4">
        <div className="flex flex-col gap-0.5">
          {visibleItems.map((item) => {
            const active = pathname.startsWith(item.href)
            const Icon = item.icon
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-background font-semibold text-foreground shadow-sm'
                    : 'text-muted-foreground hover:bg-background/60 hover:text-foreground',
                )}
              >
                <Icon size={18} className="shrink-0" />
                {t(item.labelKey, locale)}
              </Link>
            )
          })}
        </div>
      </nav>
      <div className="min-h-0 flex-1 overflow-hidden bg-background">{children}</div>
    </div>
  )
}
