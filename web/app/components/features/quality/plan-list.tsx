'use client'

import Link from 'next/link'
import { useState } from 'react'
import { IconEye, IconPlus, IconSearch } from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useQualityPlans } from '@/service/use-quality-plans'
import { hasPermission } from '@/utils/permissions'
import type { QualityPlanStatus } from '@/models/quality-plan'
import { t } from '@/utils/i18n'

export function QualityPlanList() {
  const user = useAuthStore((state) => state.user); const [q, setQ] = useState(''); const [status, setStatus] = useState<'' | QualityPlanStatus>('')
  const { locale } = useLocaleStore()
  const { data, isLoading } = useQualityPlans({ q, status, page: 1, per_page: 20 }); const canManage = hasPermission(user, 'quality.online.plan.manage')
  return <div className="flex h-full flex-col overflow-hidden"><header className="flex items-center justify-between border-b border-border px-8 py-5"><div><h1 className="text-xl font-semibold">{t('ws.quality.plans.title', locale)}</h1><p className="mt-1 text-sm text-muted-foreground">{t('ws.quality.plans.description', locale)}</p></div>{canManage && <Link href="/workspace/quality/online/plans/new" className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm text-primary-foreground"><IconPlus size={16} />{t('ws.quality.plans.new', locale)}</Link>}</header>
    <div className="flex gap-3 border-b border-border px-8 py-4"><label className="flex h-9 w-72 items-center gap-2 rounded-lg border border-input px-3"><IconSearch size={16} /><input className="min-w-0 flex-1 bg-transparent text-sm outline-none" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('ws.quality.plans.search', locale)} /></label><select className="h-9 rounded-lg border border-input bg-background px-3" value={status} onChange={(e) => setStatus(e.target.value as '' | QualityPlanStatus)}><option value="">{t('ws.quality.allStatuses', locale)}</option>{['draft','running','paused','completed','partial_failed','failed'].map((value) => <option key={value} value={value}>{t(`ws.quality.status.${value}`, locale)}</option>)}</select></div>
    <main className="min-h-0 flex-1 overflow-auto p-8">{isLoading ? <p>{t('common.loading', locale)}</p> : !data?.items.length ? <div className="grid min-h-72 place-items-center rounded-lg border border-dashed">{t('ws.quality.plans.empty', locale)}</div> : <div className="overflow-hidden rounded-lg border"><table className="w-full text-sm"><thead className="bg-muted text-left"><tr><th className="px-6 py-3">{t('common.name', locale)}</th><th>{t('ws.quality.plans.runMode', locale)}</th><th>{t('ws.quality.plans.strategy', locale)}</th><th>{t('common.status', locale)}</th><th>{t('ws.quality.plans.candidates', locale)}</th><th className="w-20">{t('common.actions', locale)}</th></tr></thead><tbody>{data.items.map((plan) => <tr key={plan.id} className="h-14 border-t"><td className="px-6 font-medium">{plan.name}</td><td>{t(`ws.quality.plans.run.${plan.run_mode}`, locale)}</td><td>{t(`ws.quality.plans.strategy.${plan.execution_strategy}`, locale)}</td><td>{t(`ws.quality.status.${plan.status}`, locale)}</td><td>{plan.estimate_result.estimated_review_count ?? '--'}</td><td><Link title={t('common.view', locale)} href={`/workspace/quality/online/plans/${plan.id}`}><IconEye size={18} /></Link></td></tr>)}</tbody></table></div>}</main></div>
}
