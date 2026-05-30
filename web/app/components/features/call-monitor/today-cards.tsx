'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { CallMonitorToday } from '@/models/call-monitor'

type Props = {
  data: CallMonitorToday | undefined
  loading?: boolean
}

type MetricKey = Exclude<keyof CallMonitorToday, 'range_label'>

const METRICS: { key: MetricKey; labelKey: string }[] = [
  { key: 'total_calls', labelKey: 'ws.records.callReports.overview.totalCalls' },
  { key: 'inbound_calls', labelKey: 'ws.records.callReports.overview.inboundCalls' },
  {
    key: 'answered_inbound_calls',
    labelKey: 'ws.records.callReports.overview.answeredInboundCalls',
  },
  { key: 'outbound_calls', labelKey: 'ws.records.callReports.overview.outboundCalls' },
  {
    key: 'answered_outbound_calls',
    labelKey: 'ws.records.callReports.overview.answeredOutboundCalls',
  },
]

export function CallMonitorTodayCards({ data, loading }: Props) {
  const { locale } = useLocaleStore()

  return (
    <div>
      <h2 className="mb-3 text-base font-semibold text-foreground">
        {t('ws.records.callMonitor.todayTitle', locale)}
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {METRICS.map((metric) => (
          <Card
            key={metric.key}
            labelKey={metric.labelKey}
            value={data ? data[metric.key].toLocaleString() : '0'}
            loading={loading}
          />
        ))}
      </div>
    </div>
  )
}

function Card({
  labelKey,
  value,
  loading,
}: {
  labelKey: string
  value: string
  loading?: boolean
}) {
  const { locale } = useLocaleStore()

  return (
    <div className="flex h-24 min-w-0 flex-col justify-center gap-2 rounded-[10px] border border-border bg-background px-5 py-4">
      <span className="truncate text-sm text-muted-foreground">{t(labelKey, locale)}</span>
      {loading ? (
        <span className="h-8 w-16 animate-pulse rounded bg-muted" aria-busy="true" />
      ) : (
        <span className="truncate text-[32px] font-semibold leading-none text-foreground">
          {value}
        </span>
      )}
    </div>
  )
}
