'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { IconArrowLeft } from '@tabler/icons-react'
import { HTTPError } from 'ky'
import Link from 'next/link'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { CallQueueOverview, QUEUE_GROUP_ORDER } from '@/app/components/features/call-reports/queues/queue-overview'
import { CallQueueTrend } from '@/app/components/features/call-reports/queues/queue-trend'
import { CallHistoryUnavailable, CallReportNotices } from '@/app/components/features/call-reports/overall/report-notices'
import { CallReportTabs } from '@/app/components/features/call-reports/report-tabs'
import { CallReportExportButton } from '@/app/components/features/call-reports/export-button'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { useLocaleStore } from '@/context/locale-store'
import type { TrendType } from '@/models/call-report'
import type { CallQueueType } from '@/models/call-queue-report'
import { callQueueKeys, useCallQueueSummary } from '@/service/use-call-queue-reports'
import { t } from '@/utils/i18n'

const VALID_TRENDS: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export default function CallQueueDetailPage() {
  const params = useParams<{ queueType: string; queueId: string }>()
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const { locale } = useLocaleStore()
  const [trendLoading, setTrendLoading] = useState(false)
  const queueId = Number.parseInt(params.queueId, 10)
  const validType = params.queueType === 'employee_group' || params.queueType === 'employee'
  const queueType = params.queueType as CallQueueType
  const validQueue = validType && Number.isFinite(queueId) && queueId > 0
  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const trendParam = searchParams.get('trend')
  const trend: TrendType = VALID_TRENDS.includes(trendParam as TrendType) ? trendParam as TrendType : 'hour'
  const dateRangeValid = isValidRange(start, end)
  const summaryQuery = useCallQueueSummary({ queueType, queueId, start, end, enabled: validQueue && dateRangeValid })
  const summary = summaryQuery.data
  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])
  const groups = QUEUE_GROUP_ORDER.filter((group) => summary?.metrics.some((metric) => metric.group === group && metric.available))
  const quality = summary?.data_quality ? { ...summary.data_quality, satisfaction_pending: 0 } : undefined
  const errorMessageKey = summaryQuery.error instanceof HTTPError
    && summaryQuery.error.response.status === 404
    ? 'ws.records.callReports.queues.notFound'
    : 'ws.records.callReports.queues.loadFailed'

  const updateParams = useCallback((next: { start?: string; end?: string; trend?: TrendType }) => {
    const nextParams = new URLSearchParams(searchParams.toString())
    if (next.start) nextParams.set('start', next.start)
    if (next.end) nextParams.set('end', next.end)
    if (next.trend) nextParams.set('trend', next.trend)
    router.replace(`/workspace/records/call-reports/queues/${params.queueType}/${params.queueId}?${nextParams.toString()}`)
  }, [params.queueId, params.queueType, router, searchParams])

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <CallReportTabs active="queues" search={carriedSearch} />
        <DateToolbar start={start} end={end} asOf={summary?.as_of ?? null}
          loading={summaryQuery.isFetching || trendLoading || !dateRangeValid}
          onChange={updateParams} onRefresh={() => void queryClient.invalidateQueries({ queryKey: callQueueKeys.all })}
          exportAction={<CallReportExportButton
            params={{ kind: 'queue-detail', start, end, trend, queue_type: queueType, queue_id: queueId }}
            disabled={!validQueue || !dateRangeValid || summaryQuery.isLoading || (summaryQuery.isError && !summary)}
          />} />
        {!validQueue ? <DetailState messageKey="ws.records.callReports.queues.notFound" />
          : summaryQuery.isError && !summary ? <DetailState messageKey={errorMessageKey} onRetry={() => summaryQuery.refetch()} />
          : <>
              <div className="flex flex-wrap items-center gap-3">
                <Link href={`/workspace/records/call-reports/queues${carriedSearch ? `?${carriedSearch}` : ''}`}
                  className="flex size-9 items-center justify-center rounded-lg border border-border text-muted-foreground hover:text-foreground">
                  <IconArrowLeft size={18} />
                </Link>
                <div className="min-w-0">
                  <h1 className="truncate text-lg font-semibold text-foreground">{summary?.queue.name ?? t('ws.records.callReports.queues.detailTitle', locale)}</h1>
                  {summary ? <p className="text-xs text-muted-foreground">{t(`ws.records.callReports.queues.type.${summary.queue.queue_type}`, locale)} · {t(`ws.records.callReports.queues.status.${summary.queue.status}`, locale)}</p> : null}
                </div>
              </div>
              {summary?.coverage.status !== 'unavailable' ? <CallReportNotices coverage={summary?.coverage} dataQuality={quality} /> : null}
              {summary?.coverage.status === 'unavailable' ? <CallHistoryUnavailable effectiveAt={summary.coverage.effective_at} /> : <>
                <CallQueueOverview metrics={summary?.metrics ?? []} distributions={summary?.distributions ?? []} loading={summaryQuery.isLoading} />
                <CallQueueTrend queueType={queueType} queueId={queueId} start={start} end={end} trend={trend}
                  groups={groups.length > 0 ? groups : QUEUE_GROUP_ORDER}
                  enabled={dateRangeValid && Boolean(summary)}
                  summaryLoading={summaryQuery.isLoading} onTrendChange={(value) => updateParams({ trend: value })}
                  onLoadingChange={setTrendLoading} />
              </>}
            </>}
      </div>
    </div>
  )
}

function DetailState({ messageKey, onRetry }: { messageKey: string; onRetry?: () => void }) {
  const { locale } = useLocaleStore()
  return <div className="flex min-h-80 flex-col items-center justify-center gap-3 rounded-lg border border-border text-sm text-muted-foreground">
    <p>{t(messageKey, locale)}</p>
    {onRetry ? <button type="button" onClick={onRetry} className="h-9 rounded-md bg-primary px-4 text-primary-foreground">{t('ws.records.callReports.overall.retry', locale)}</button> : null}
  </div>
}

function todayIsoDate(): string {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function isValidRange(start: string, end: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start > end) return false
  return (new Date(`${end}T00:00:00Z`).getTime() - new Date(`${start}T00:00:00Z`).getTime()) / 86_400_000 < 366
}
