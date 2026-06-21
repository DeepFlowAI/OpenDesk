'use client'

import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw, X } from 'lucide-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

// Version baked into THIS client bundle at build time (see web/Dockerfile).
const CURRENT_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || ''
const POLL_INTERVAL_MS = 3 * 60 * 1000
const DISMISS_KEY = 'opendesk:update-dismissed-version'

async function fetchDeployedVersion(): Promise<string> {
  // Cache-busted + no-store so we always see the freshly deployed file.
  const res = await fetch(`/version.json?_=${Date.now()}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`version.json ${res.status}`)
  const data = (await res.json()) as { version?: string }
  return data.version || ''
}

/**
 * Global "site updated, please refresh" notice. Polls the deployed
 * version.json and compares it to the version baked into the running bundle;
 * when they differ a new deploy has gone out and we prompt the user to reload.
 * Hidden on the visitor-facing embedded chat widget (/chat/[channelId]).
 */
export function UpdateNotice() {
  const pathname = usePathname()
  const { locale } = useLocaleStore()
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null)

  useEffect(() => {
    setDismissedVersion(localStorage.getItem(DISMISS_KEY))
  }, [])

  const isVisitorWidget = pathname?.startsWith('/chat/') ?? false
  // No baseline in dev (version unset) -> never nag.
  const enabled = !isVisitorWidget && CURRENT_VERSION !== ''

  const { data: deployedVersion } = useQuery({
    queryKey: ['app-version'],
    queryFn: fetchDeployedVersion,
    enabled,
    refetchInterval: POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
    staleTime: 0,
    retry: false,
  })

  if (!enabled) return null
  if (!deployedVersion || deployedVersion === CURRENT_VERSION) return null
  if (deployedVersion === dismissedVersion) return null

  return (
    <div className="fixed left-1/2 top-3 z-[1000] -translate-x-1/2">
      <div
        role="status"
        className={cn(
          'flex items-center gap-2 rounded-full border border-border px-3 py-1.5',
          'text-sm text-foreground shadow-lg backdrop-blur',
          'bg-background/95 supports-[backdrop-filter]:bg-background/80'
        )}
      >
        <RefreshCw className="size-4 shrink-0 text-primary" />
        <span className="whitespace-nowrap">{t('update.available', locale)}</span>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-full bg-primary px-2.5 py-0.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
        >
          {t('update.refresh', locale)}
        </button>
        <button
          type="button"
          aria-label={t('update.dismiss', locale)}
          onClick={() => {
            localStorage.setItem(DISMISS_KEY, deployedVersion)
            setDismissedVersion(deployedVersion)
          }}
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  )
}
