'use client'

import { useDeferredValue, useState } from 'react'
import Link from 'next/link'
import { IconArrowRight, IconSearch } from '@tabler/icons-react'
import { DashboardIcon } from './dashboard-icon'
import { useWorkspaceCustomDashboards } from '@/service/use-custom-dashboards'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export function WorkspaceDashboardList() {
  const { locale } = useLocaleStore()
  const [keyword, setKeyword] = useState('')
  const deferredKeyword = useDeferredValue(keyword)
  const query = useWorkspaceCustomDashboards(deferredKeyword)
  const items = query.data?.items ?? []

  return (
    <div className="h-full overflow-y-auto bg-background px-7 py-7">
      <h1 className="text-xl font-semibold text-foreground">{t('ws.cd.title', locale)}</h1>
      <div className="mt-6 flex items-center justify-between">
        <label className="flex h-9 w-80 items-center gap-2 rounded-lg border border-border px-3 focus-within:ring-2 focus-within:ring-ring/40">
          <IconSearch size={16} className="text-muted-foreground" />
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={t('ws.cd.search', locale)} className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
        </label>
        <span className="text-sm text-muted-foreground">{t('ws.cd.total', locale, { total: query.data?.total ?? 0 })}</span>
      </div>
      {query.isLoading ? (
        <div className="py-24 text-center text-sm text-muted-foreground">{t('cd.loading', locale)}</div>
      ) : items.length === 0 ? (
        <div className="py-24 text-center text-sm text-muted-foreground">{t('ws.cd.empty', locale)}</div>
      ) : (
        <div className="mt-5 grid grid-cols-3 gap-4">
          {items.map((dashboard) => (
            <Link key={dashboard.id} href={`/workspace/records/dashboards/${dashboard.id}`} className="group flex min-h-44 flex-col rounded-xl border border-border bg-card p-5 shadow-sm transition hover:border-ring/50 hover:shadow-md">
              <div className="flex items-start justify-between"><span className="rounded-xl bg-muted p-3"><DashboardIcon name={dashboard.icon} size={22} /></span><IconArrowRight className="text-muted-foreground transition-transform group-hover:translate-x-1" size={18} /></div>
              <h2 className="mt-4 truncate text-base font-semibold text-foreground">{dashboard.name}</h2>
              <p className="mt-1 line-clamp-2 flex-1 text-sm text-muted-foreground">{dashboard.description || '—'}</p>
              <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground"><span>{t('ws.cd.components', locale, { count: dashboard.component_count })}</span><span>{new Date(dashboard.published_at).toLocaleDateString(locale)}</span></div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
