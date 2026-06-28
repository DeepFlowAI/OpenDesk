'use client'

import { useCallback, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { SessionReportExportButton } from '@/app/components/features/session-reports/export-button'
import { QueueDetailHeader } from '@/app/components/features/session-reports/queue-detail-header'
import { QueueOverviewCards } from '@/app/components/features/session-reports/queue-overview-cards'
import { QueueTrend } from '@/app/components/features/session-reports/queue-trend'
import { ReportTabs } from '@/app/components/features/session-reports/report-tabs'
import { useLocaleStore } from '@/context/locale-store'
import { useSessionReportQueueDetail } from '@/service/use-session-reports'
import { t } from '@/utils/i18n'
import type { QueueMetricGroup, QueueType, TrendType } from '@/models/session-report'

function todayIsoDate(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const VALID_TRENDS: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']
const VALID_QUEUE_TYPES: QueueType[] = ['employee_group', 'employee']

export default function QueueDetailPage() {
  const params = useParams<{ queueType: string; queueId: string }>()
  const queueId = parseInt(params.queueId, 10)
  const isValidQueueType = VALID_QUEUE_TYPES.includes(params.queueType as QueueType)
  const queueType = (isValidQueueType ? params.queueType : 'employee_group') as QueueType
  const validQueue = isValidQueueType && Number.isFinite(queueId)
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()
  const [dateRangeValid, setDateRangeValid] = useState(true)
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendGroup, setTrendGroup] = useState<QueueMetricGroup>('queue_access')

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const trendParam = searchParams.get('trend')
  const trend: TrendType = (VALID_TRENDS.includes(trendParam as TrendType) ? trendParam : 'hour') as TrendType

  const updateParams = useCallback(
    (next: { start?: string; end?: string; trend?: TrendType }) => {
      const p = new URLSearchParams(searchParams.toString())
      if (next.start) p.set('start', next.start)
      if (next.end) p.set('end', next.end)
      if (next.trend) p.set('trend', next.trend)
      router.replace(`/workspace/records/session-reports/queues/${queueType}/${queueId}?${p.toString()}`)
    },
    [router, searchParams, queueType, queueId]
  )

  const { data, refetch, isFetching, isLoading, isError } = useSessionReportQueueDetail({
    start,
    end,
    queue_type: queueType,
    queue_id: queueId,
    enabled: validQueue,
  })

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  if (!validQueue || (isError && !data)) {
    return (
      <div className="flex h-full flex-col overflow-auto">
        <div className="flex flex-col gap-5 p-6">
          <ReportTabs active="queues" search={carriedSearch} />
          <div className="text-sm text-muted-foreground">
            {t('ws.records.sessionReports.queues.notFound', locale)}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <ReportTabs active="queues" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={data?.as_of ?? null}
          loading={isFetching}
          exportAction={
            <SessionReportExportButton
              variant="queue"
              params={{
                scope: 'detail',
                start,
                end,
                trend,
                group: trendGroup,
                queue_type: queueType,
                queue_id: queueId,
              }}
              disabled={!dateRangeValid || isFetching || trendLoading || !data}
            />
          }
          onChange={(r) => updateParams(r)}
          onRefresh={() => refetch()}
          onValidityChange={setDateRangeValid}
        />
        {data ? (
          <QueueDetailHeader queue={data.queue} carriedSearch={carriedSearch} />
        ) : (
          <div className="text-sm text-muted-foreground">
            {t('ws.records.sessionReports.common.loading', locale)}
          </div>
        )}
        <QueueOverviewCards metrics={data?.metrics} loading={isLoading} />
        <QueueTrend
          start={start}
          end={end}
          trend={trend}
          group={trendGroup}
          queueType={queueType}
          queueId={queueId}
          onTrendChange={(t) => updateParams({ trend: t })}
          onGroupChange={setTrendGroup}
          onLoadingChange={setTrendLoading}
        />
      </div>
    </div>
  )
}
