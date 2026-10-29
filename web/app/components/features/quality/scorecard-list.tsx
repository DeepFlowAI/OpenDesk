'use client'

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { IconEye, IconPlus, IconSearch } from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useQualityScorecards } from '@/service/use-quality-scorecards'
import { hasPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'
import type { QualityScorecardStatus } from '@/models/quality-scorecard'

export function ScorecardList() {
  const user = useAuthStore((state) => state.user)
  const locale = useLocaleStore((state) => state.locale)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<'' | QualityScorecardStatus>('')
  const params = useMemo(() => ({ q, status, page: 1, per_page: 20 }), [q, status])
  const { data, isLoading, isError } = useQualityScorecards(params)
  const canManage = hasPermission(user, 'quality.online.scorecard.manage')

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-8 py-5">
        <div><h1 className="text-xl font-semibold">{t('ws.quality.scorecards.title', locale)}</h1><p className="mt-1 text-sm text-muted-foreground">{t('ws.quality.scorecards.description', locale)}</p></div>
        {canManage && <Link href="/workspace/quality/online/scorecards/new" className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground"><IconPlus size={16} />{t('ws.quality.scorecards.new', locale)}</Link>}
      </header>
      <div className="flex shrink-0 gap-3 border-b border-border px-8 py-4">
        <label className="flex h-9 w-[280px] items-center gap-2 rounded-lg border border-input px-3"><IconSearch size={16} className="text-muted-foreground" /><input className="min-w-0 flex-1 bg-transparent text-sm outline-none" value={q} onChange={(event) => setQ(event.target.value)} placeholder={t('ws.quality.scorecards.search', locale)} /></label>
        <select className="h-9 rounded-lg border border-input bg-background px-3 text-sm" value={status} onChange={(event) => setStatus(event.target.value as '' | QualityScorecardStatus)}><option value="">{t('ws.quality.allStatuses', locale)}</option><option value="draft">{t('ws.quality.status.draft', locale)}</option><option value="published">{t('ws.quality.status.published', locale)}</option><option value="disabled">{t('ws.quality.status.disabled', locale)}</option></select>
      </div>
      <main className="min-h-0 flex-1 overflow-auto p-8">
        {isLoading ? <div className="text-sm text-muted-foreground">{t('common.loading', locale)}</div> : isError ? <div className="text-sm text-destructive">{t('common.loadFailed', locale)}</div> : !data?.items.length ? (
          <div className="flex min-h-72 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border"><h2 className="font-medium">{t('ws.quality.scorecards.empty', locale)}</h2>{canManage && <Link className="rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground" href="/workspace/quality/online/scorecards/new">{t('ws.quality.scorecards.new', locale)}</Link>}</div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border"><table className="w-full text-sm"><thead className="bg-muted text-left"><tr><th className="px-6 py-3 font-semibold">{t('common.name', locale)}</th><th className="px-6 py-3 font-semibold">{t('ws.quality.version', locale)}</th><th className="px-6 py-3 font-semibold">{t('ws.quality.criteria', locale)}</th><th className="px-6 py-3 font-semibold">{t('common.status', locale)}</th><th className="px-6 py-3 font-semibold">{t('common.updatedAt', locale)}</th><th className="w-20 px-6 py-3 font-semibold">{t('common.actions', locale)}</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id} className="h-14 border-t border-border"><td className="px-6 font-medium">{item.name}</td><td className="px-6">V{item.current_version_number}</td><td className="px-6">{item.scored_count} / {item.observation_count}</td><td className="px-6">{t(`ws.quality.status.${item.status}`, locale)}</td><td className="px-6 text-muted-foreground">{new Date(item.updated_at).toLocaleString(locale)}</td><td className="px-6"><Link title={t('common.view', locale)} href={`/workspace/quality/online/scorecards/${item.id}`}><IconEye size={18} /></Link></td></tr>)}</tbody></table></div>
        )}
      </main>
    </div>
  )
}
