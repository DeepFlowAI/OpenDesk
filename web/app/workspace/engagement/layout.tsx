'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { IconClipboardList, IconTemplate } from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { hasAnyPermission } from '@/utils/permissions'
import { cn } from '@/lib/utils'

const items = [
  {
    href: '/workspace/engagement/outbound-tasks',
    label: '人工外呼任务',
    icon: IconClipboardList,
    permissions: ['engagement.outbound_task.manage', 'engagement.outbound_task.create'],
  },
  {
    href: '/workspace/engagement/outbound-task-templates',
    label: '外呼任务模板',
    icon: IconTemplate,
    permissions: ['engagement.outbound_task.template.manage'],
  },
]

export default function EngagementLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
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
                {item.label}
              </Link>
            )
          })}
        </div>
      </nav>
      <div className="min-h-0 flex-1 overflow-hidden bg-background">{children}</div>
    </div>
  )
}
