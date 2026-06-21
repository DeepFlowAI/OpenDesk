'use client'

import { useState, useEffect, useMemo, type ComponentType } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  IconHeadset,
  IconUser,
  IconUsers,
  IconMessageCircle,
  IconMessageCircleCog,
  IconGitBranch,
  IconSettings,
  IconClock,
  IconKey,
  IconPlugConnected,
  IconAddressBook,
  IconBuilding,
  IconBuildingCog,
  IconStack2,
  IconLayoutDashboard,
  IconNotes,
  IconListSearch,
  IconSortAscending,
  IconPhone,
  IconFilePhone,
  IconShieldCheck,
} from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useRefreshCurrentUser } from '@/hooks/use-refresh-current-user'
import { UserDropdown } from '@/app/components/features/user-dropdown'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  ADMIN_NAV_GROUPS,
  getAdminRouteRule,
  isAdminPathMatch,
  type AdminNavIconKey,
} from '@/config/admin-permissions'
import {
  getDefaultAccessiblePath,
  getDefaultAdminPath,
  hasAllPermissions,
  hasPermission,
} from '@/utils/permissions'

const ADMIN_NAV_ICONS: Record<AdminNavIconKey, ComponentType<{ size?: number; className?: string }>> = {
  employees: IconUser,
  employeeGroups: IconUsers,
  roles: IconShieldCheck,
  queueSettings: IconSortAscending,
  flowStudio: IconGitBranch,
  phoneNumbers: IconPhone,
  callSummary: IconFilePhone,
  conversationSettings: IconMessageCircleCog,
  channels: IconMessageCircle,
  sessionRouting: IconGitBranch,
  sessionSummary: IconNotes,
  userFields: IconAddressBook,
  organizationFields: IconBuilding,
  userViews: IconListSearch,
  organizationViews: IconListSearch,
  organizationSettings: IconBuildingCog,
  formLayouts: IconLayoutDashboard,
  sharedFields: IconStack2,
  ticketViews: IconListSearch,
  ticketWorkflows: IconGitBranch,
  systemSettings: IconSettings,
  serviceHours: IconClock,
  apiKeys: IconKey,
  openAgent: IconPlugConnected,
}

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user } = useAuthStore()
  const { locale } = useLocaleStore()
  const [mounted, setMounted] = useState(false)
  const { isRefreshing: authRefreshing } = useRefreshCurrentUser(mounted)
  const visibleNavGroups = useMemo(
    () => ADMIN_NAV_GROUPS
      .map((group) => ({
        ...group,
        items: group.items.filter((item) => (
          item.superAdminOnly ? Boolean(user?.is_super_admin) : hasPermission(user, item.permission)
        )),
      }))
      .filter((group) => group.items.length > 0),
    [user]
  )

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (mounted && !token) {
      router.replace('/login')
    }
  }, [mounted, token, router])

  useEffect(() => {
    if (mounted && token && user && !authRefreshing && !hasPermission(user, 'admin.access')) {
      router.replace(getDefaultAccessiblePath(user))
    }
  }, [authRefreshing, mounted, token, user, router])

  useEffect(() => {
    if (!mounted || !token || !user || authRefreshing || !hasPermission(user, 'admin.access')) return
    const routeRule = getAdminRouteRule(pathname)
    if (routeRule?.superAdminOnly && !user.is_super_admin) {
      router.replace('/403')
      return
    }
    if (routeRule && !hasAllPermissions(user, routeRule.permissions)) {
      router.replace(getDefaultAdminPath(user))
    }
  }, [authRefreshing, mounted, token, user, pathname, router])

  if (!mounted || authRefreshing || !token || !user) return null
  if (!hasPermission(user, 'admin.access')) return null
  const routeRule = getAdminRouteRule(pathname)
  if (routeRule?.superAdminOnly && !user.is_super_admin) return null
  if (routeRule && !hasAllPermissions(user, routeRule.permissions)) return null
  if (visibleNavGroups.length === 0) return null

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
          {visibleNavGroups.map((group, gi) => (
            <div key={group.labelKey} className={cn('flex flex-col gap-1', gi > 0 && 'mt-2')}>
              <span className="mb-1 px-2.5 text-sm font-semibold text-muted-foreground">
                {t(group.labelKey, locale)}
              </span>
              {group.items.map((item) => {
                const active = isAdminPathMatch(pathname, item.href)
                const Icon = ADMIN_NAV_ICONS[item.iconKey]
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
