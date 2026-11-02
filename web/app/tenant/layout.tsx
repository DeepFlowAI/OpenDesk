'use client'

import { useEffect, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { IconBuildingSkyscraper, IconLogout, IconPhone, IconRouter } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  TENANT_CONSOLE_LOGIN_PATH,
  clearConsoleToken,
  readConsoleToken,
} from '@/service/tenant-console-client'
import { tenantConsoleKeys, useConsoleMe } from '@/service/use-tenant-console'

const NAV_ITEMS = [
  { href: '/tenant', match: (p: string) => p === '/tenant' || p.startsWith('/tenant/tenants'), icon: IconBuildingSkyscraper, labelKey: 'tc.nav.tenants' },
  { href: '/tenant/sip-trunks', match: (p: string) => p.startsWith('/tenant/sip-trunks'), icon: IconRouter, labelKey: 'tc.nav.sipTrunks' },
  { href: '/tenant/phone-numbers', match: (p: string) => p.startsWith('/tenant/phone-numbers'), icon: IconPhone, labelKey: 'tc.nav.phoneNumbers' },
]

function ConsoleShell({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const queryClient = useQueryClient()
  const { locale } = useLocaleStore()
  const [hasToken, setHasToken] = useState<boolean | null>(null)
  const { data: me } = useConsoleMe()

  useEffect(() => {
    const present = !!readConsoleToken()
    setHasToken(present)
    if (!present) router.replace(TENANT_CONSOLE_LOGIN_PATH)
  }, [router])

  const handleLogout = () => {
    clearConsoleToken()
    queryClient.removeQueries({ queryKey: tenantConsoleKeys.all })
    router.replace(TENANT_CONSOLE_LOGIN_PATH)
  }

  if (!hasToken) return null

  return (
    <div className="flex h-screen bg-background">
      <aside className="flex w-60 shrink-0 flex-col border-r border-border">
        <div className="px-5 py-5">
          <p className="font-display text-lg font-bold text-foreground">{t('tc.brand', locale)}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{t('tc.brandSub', locale)}</p>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon
            const active = item.match(pathname)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                  active
                    ? 'bg-accent font-medium text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                )}
              >
                <Icon size={16} />
                {t(item.labelKey, locale)}
              </Link>
            )
          })}
        </nav>
        <div className="border-t border-border p-3">
          {me?.username && (
            <p className="truncate px-3 pb-2 text-xs text-muted-foreground">{me.username}</p>
          )}
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <IconLogout size={16} />
            {t('tc.nav.logout', locale)}
          </button>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col overflow-auto">{children}</main>
    </div>
  )
}

export default function TenantConsoleLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  if (pathname.startsWith(TENANT_CONSOLE_LOGIN_PATH)) return <>{children}</>
  return <ConsoleShell>{children}</ConsoleShell>
}
