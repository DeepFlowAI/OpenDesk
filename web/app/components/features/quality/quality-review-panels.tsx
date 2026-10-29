'use client'

import Link from 'next/link'
import { useState } from 'react'
import { IconEye, IconPlayerPlay, IconUserCheck } from '@tabler/icons-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useEmployees } from '@/service/use-employees'
import {
  useMyPendingQualityReviews,
  useQualityReviews,
  useQualityStatistics,
  useReassignQualityReview,
  useRetryQualityReview,
} from '@/service/use-quality-reviews'
import { hasPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'
import type { QualityReviewListItem } from '@/models/quality-review'
import type { Employee } from '@/models/employee'
import type { Locale } from '@/context/locale-store'

const statusKey = (status: string) => `ws.quality.review.status.${status}`

export function QualityPlanReviewPanels({ planId, reviewerIds }: { planId: number; reviewerIds: number[] }) {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const canReview = hasPermission(user, 'quality.online.review.perform')
  const canView = hasPermission(user, 'quality.online.record.view')
  const canManage = hasPermission(user, 'quality.online.plan.manage')
  const [tab, setTab] = useState<'pending' | 'records'>('pending')
  const [page, setPage] = useState(1)
  const stats = useQualityStatistics(canView ? planId : 0)
  const pending = useMyPendingQualityReviews(canReview ? planId : 0, { page, per_page: 20 })
  const records = useQualityReviews(canView ? planId : 0, { page, per_page: 20 })
  const { data: employees } = useEmployees({ status: 'active', page: 1, per_page: 100 })
  const reviewers = (employees?.items ?? []).filter((employee) => reviewerIds.includes(employee.id))
  const reassign = useReassignQualityReview()
  const retry = useRetryQualityReview()
  const data = tab === 'pending' ? pending.data : records.data

  const assign = async (reviewId: number, reviewerId: number) => {
    try {
      await reassign.mutateAsync({ reviewId, reviewerId })
      toast.success(t('ws.quality.review.reassigned', locale))
    } catch {
      toast.error(t('common.loadFailed', locale))
    }
  }

  const retryReview = async (reviewId: number) => {
    try {
      await retry.mutateAsync({ planId, reviewId })
      toast.success(t('ws.quality.review.retryQueued', locale))
    } catch {
      toast.error(t('common.loadFailed', locale))
    }
  }

  return (
    <section className="space-y-5">
      {canView && (
        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {[
            ['total', stats.data?.total],
            ['aiCompleted', stats.data?.ai_completed],
            ['pendingHuman', stats.data?.pending_human],
            ['humanCompleted', stats.data?.human_completed],
            ['unable', stats.data?.unable],
            ['failed', stats.data?.failed],
          ].map(([key, value]) => (
            <div key={key} className="rounded-lg border bg-card p-4">
              <div className="text-xs text-muted-foreground">{t(`ws.quality.stats.${key}`, locale)}</div>
              <div className="mt-1 text-2xl font-semibold">{value ?? '--'}</div>
            </div>
          ))}
        </div>
      )}
      <div className="overflow-hidden rounded-lg border bg-card">
        <div className="flex items-center gap-1 border-b px-4 pt-3">
          {canReview && <button className={`border-b-2 px-4 py-2 text-sm ${tab === 'pending' ? 'border-primary font-semibold' : 'border-transparent text-muted-foreground'}`} onClick={() => { setTab('pending'); setPage(1) }}>{t('ws.quality.review.pendingMine', locale)}</button>}
          {canView && <button className={`border-b-2 px-4 py-2 text-sm ${tab === 'records' ? 'border-primary font-semibold' : 'border-transparent text-muted-foreground'}`} onClick={() => { setTab('records'); setPage(1) }}>{t('ws.quality.review.records', locale)}</button>}
        </div>
        {!data?.items.length ? (
          <div className="grid min-h-48 place-items-center text-sm text-muted-foreground">{t(tab === 'pending' ? 'ws.quality.review.emptyPending' : 'ws.quality.review.emptyRecords', locale)}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left"><tr><th className="px-5 py-3">{t('ws.quality.review.agent', locale)}</th><th>{t('common.status', locale)}</th><th>{t('ws.quality.review.reason', locale)}</th><th>{t('ws.quality.review.result', locale)}</th><th>{t('common.actions', locale)}</th></tr></thead>
              <tbody>{data.items.map((review) => <ReviewRow key={review.id} review={review} tab={tab} planId={planId} canManage={canManage} employees={reviewers} onAssign={assign} onRetry={retryReview} locale={locale} />)}</tbody>
            </table>
          </div>
        )}
        {data && data.pages > 1 && <div className="flex justify-end gap-2 border-t p-3"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>{t('ws.quality.previous', locale)}</Button><span className="px-2 py-1 text-sm">{page} / {data.pages}</span><Button variant="outline" size="sm" disabled={page >= data.pages} onClick={() => setPage((value) => value + 1)}>{t('ws.quality.next', locale)}</Button></div>}
      </div>
    </section>
  )
}

function ReviewRow({ review, tab, planId, canManage, employees, onAssign, onRetry, locale }: { review: QualityReviewListItem; tab: 'pending' | 'records'; planId: number; canManage: boolean; employees: Employee[]; onAssign: (reviewId: number, reviewerId: number) => Promise<void>; onRetry: (reviewId: number) => Promise<void>; locale: Locale }) {
  const [reviewerId, setReviewerId] = useState(review.assigned_reviewer_id ?? 0)
  return <tr className="border-t"><td className="px-5 py-3 font-medium">{review.agent_name ?? `#${review.target_agent_id}`}</td><td>{t(statusKey(review.status), locale)}</td><td className="max-w-56 truncate">{review.route_reasons.map((reason) => t(`ws.quality.review.route.${reason}`, locale)).join('、') || '--'}</td><td>{review.result_source ? t(`ws.quality.review.source.${review.result_source}`, locale) : '--'}{review.score != null ? ` · ${review.score}` : ''}</td><td><div className="flex items-center gap-2">{tab === 'pending' ? <Link className="inline-flex items-center gap-1 text-primary" href={`/workspace/quality/online/reviews/${review.id}`}><IconUserCheck size={16} />{t('ws.quality.review.start', locale)}</Link> : <Link className="inline-flex items-center gap-1 text-primary" href={`/workspace/quality/online/plans/${planId}/reviews/${review.id}`}><IconEye size={16} />{t('common.view', locale)}</Link>}{review.status === 'execution_failed' && canManage && <button className="inline-flex items-center gap-1 text-primary" onClick={() => void onRetry(review.id)}><IconPlayerPlay size={16} />{t('ws.quality.review.retry', locale)}</button>}{canManage && ['pending_human', 'human_reviewing'].includes(review.status) && <><select className="h-8 max-w-36 rounded-lg border bg-background px-2" value={reviewerId} onChange={(event) => setReviewerId(Number(event.target.value))}><option value={0}>{t('ws.quality.review.unassigned', locale)}</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name}</option>)}</select><Button size="sm" variant="outline" disabled={!reviewerId || reviewerId === review.assigned_reviewer_id} onClick={() => void onAssign(review.id, reviewerId)}>{t('ws.quality.review.assign', locale)}</Button></>}</div></td></tr>
}
