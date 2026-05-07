'use client'

import { useState, useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  IconHeadset,
  IconUser,
  IconUsers,
  IconMessageCircle,
  IconGitBranch,
  IconSettings,
  IconClock,
  IconAddressBook,
  IconBuilding,
  IconBuildingCog,
  IconStack2,
  IconLayoutDashboard,
  IconNotes,
  IconListSearch,
} from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { UserDropdown } from '@/app/components/features/user-dropdown'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

type NavItem = {
  labelKey: string
  href: string
  icon: React.ComponentType<{ size?: number; className?: string }>
}

type NavGroup = {
  labelKey: string
  items: NavItem[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: 'nav.group.organization',
    items: [
      { labelKey: 'nav.employees', href: '/employees', icon: IconUser },
      { labelKey: 'nav.employeeGroups', href: '/employee-groups', icon: IconUsers },
    ],
  },
  {
    labelKey: 'nav.group.onlineService',
    items: [
      { labelKey: 'nav.channels', href: '/channels', icon: IconMessageCircle },
      { labelKey: 'nav.sessionRouting', href: '/session-routing', icon: IconGitBranch },
      { labelKey: 'nav.sessionSummary', href: '/session-summary', icon: IconNotes },
    ],
  },
  {
    labelKey: 'nav.group.userOrganization',
    items: [
      { labelKey: 'nav.userFields', href: '/user-fields', icon: IconAddressBook },
      { labelKey: 'nav.organizationFields', href: '/organization-fields', icon: IconBuilding },
      { labelKey: 'nav.userViews', href: '/user-views', icon: IconListSearch },
      { labelKey: 'nav.organizationViews', href: '/organization-views', icon: IconListSearch },
      { labelKey: 'nav.organizationSettings', href: '/organization-settings', icon: IconBuildingCog },
    ],
  },
  {
    labelKey: 'nav.group.ticket',
    items: [
      { labelKey: 'nav.formLayouts', href: '/form-layouts', icon: IconLayoutDashboard },
      { labelKey: 'nav.sharedFields', href: '/shared-fields', icon: IconStack2 },
      { labelKey: 'nav.ticketViews', href: '/ticket-views', icon: IconListSearch },
    ],
  },
  {
    labelKey: 'nav.group.globalSettings',
    items: [
      { labelKey: 'nav.systemSettings', href: '/system-settings', icon: IconSettings },
      { labelKey: 'nav.serviceHours', href: '/service-hours', icon: IconClock },
    ],
  },
]

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user } = useAuthStore()
  const { locale } = useLocaleStore()
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
    <div className="flex h-screen flex-col">
      {/* Top Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex items-center gap-3">
          <IconHeadset size={28} className="text-foreground" />
          <span className="text-lg font-semibold text-foreground">
            {t('admin.header.title', locale)}
          </span>
        </div>
        <UserDropdown />
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="flex w-60 shrink-0 flex-col gap-2 overflow-y-auto border-r border-border bg-muted px-4 py-6">
          {NAV_GROUPS.map((group, gi) => (
            <div key={group.labelKey} className={cn('flex flex-col gap-1', gi > 0 && 'mt-2')}>
              <span className="mb-1 px-2.5 text-sm font-semibold text-muted-foreground">
                {t(group.labelKey, locale)}
              </span>
              {group.items.map((item) => {
                const prefixRoutes = ['/session-routing', '/channels', '/user-fields', '/organization-fields', '/shared-fields', '/form-layouts', '/session-summary', '/user-views', '/ticket-views', '/organization-views']
                const active = prefixRoutes.includes(item.href)
                  ? pathname.startsWith(item.href)
                  : pathname === item.href
                const Icon = item.icon
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      'flex h-9 items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors',
                      active
                        ? 'bg-white font-semibold text-foreground'
                        : 'text-foreground/80 hover:bg-white/60'
                    )}
                  >
                    <Icon size={18} className={active ? 'text-foreground' : 'text-foreground/80'} />
                    {t(item.labelKey, locale)}
                  </Link>
                )
              })}
            </div>
          ))}
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-y-auto bg-white p-8">
          {children}
        </main>
      </div>
    </div>
  )
}
