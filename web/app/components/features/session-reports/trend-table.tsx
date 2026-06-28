'use client'

import { useLocaleStore } from '@/context/locale-store'
import type { MetricKey, TrendBucket } from '@/models/session-report'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'
import { metricLabelKey } from './types'

type Props = {
  buckets: TrendBucket[]
  showBusinessMetrics?: boolean
}

type Column = {
  key: MetricKey
  className: string
}

const BASIC_COLUMNS: Column[] = [
  { key: 'session_count', className: 'w-[110px]' },
  { key: 'message_count', className: 'w-[110px]' },
  { key: 'user_message_count', className: 'w-[120px]' },
  { key: 'agent_message_count', className: 'w-[120px]' },
  { key: 'avg_duration_seconds', className: 'w-[140px]' },
]

const BUSINESS_COLUMNS: Column[] = [
  { key: 'bot_session_count', className: 'w-[120px]' },
  { key: 'bot_handoff_count', className: 'w-[130px]' },
  { key: 'queued_session_count', className: 'w-[120px]' },
  { key: 'avg_queue_duration_seconds', className: 'w-[140px]' },
  { key: 'offline_message_count', className: 'w-[110px]' },
]

export function TrendTable({ buckets, showBusinessMetrics = false }: Props) {
  const { locale } = useLocaleStore()
  const canViewOfflineMessages = buckets[0]?.metrics.can_view_offline_messages ?? true
  const columns = [
    ...BASIC_COLUMNS,
    ...(showBusinessMetrics
      ? BUSINESS_COLUMNS.filter((col) => (
        col.key !== 'offline_message_count' || canViewOfflineMessages
      ))
      : []),
  ]
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <div className="min-w-max">
        {/* Header */}
        <div className="flex h-12 items-center gap-4 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
          <div className="w-[140px] shrink-0">{t('ws.records.sessionReports.trend.colTime', locale)}</div>
          {columns.map((col) => (
            <div key={col.key} className={`${col.className} shrink-0 text-center`}>
              {t(metricLabelKey[col.key], locale)}
            </div>
          ))}
        </div>

        {/* Rows */}
        <div className="max-h-[480px] overflow-auto">
          {buckets.map((b) => (
            <div
              key={b.label}
              className="flex h-[52px] items-center gap-4 border-b border-[#F0F0F0] px-6 text-[13px] text-foreground last:border-b-0"
            >
              <div className="w-[140px] shrink-0">{b.label}</div>
              {columns.map((col) => (
                <div key={col.key} className={`${col.className} shrink-0 text-center`}>
                  {renderMetricValue(b, col.key)}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function renderMetricValue(bucket: TrendBucket, key: MetricKey): string {
  if (key === 'avg_duration_seconds') {
    return formatDuration(bucket.metrics.avg_duration_seconds)
  }
  if (key === 'avg_queue_duration_seconds') {
    return formatDuration(bucket.metrics.avg_queue_duration_seconds)
  }
  const value = bucket.metrics[key]
  return typeof value === 'number' ? value.toLocaleString() : '0'
}
