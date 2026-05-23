'use client'

import { useLocaleStore } from '@/context/locale-store'
import type { TrendBucket } from '@/models/session-report'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'

type Props = {
  buckets: TrendBucket[]
}

export function TrendTable({ buckets }: Props) {
  const { locale } = useLocaleStore()
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      {/* Header */}
      <div className="flex h-12 items-center gap-4 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
        <div className="w-[140px]">{t('ws.records.sessionReports.trend.colTime', locale)}</div>
        <div className="flex-1 text-center">
          {t('ws.records.sessionReports.overview.sessionCount', locale)}
        </div>
        <div className="flex-1 text-center">
          {t('ws.records.sessionReports.overview.messageCount', locale)}
        </div>
        <div className="flex-1 text-center">
          {t('ws.records.sessionReports.overview.userMessageCount', locale)}
        </div>
        <div className="flex-1 text-center">
          {t('ws.records.sessionReports.overview.agentMessageCount', locale)}
        </div>
        <div className="w-[140px] text-center">
          {t('ws.records.sessionReports.overview.avgDuration', locale)}
        </div>
      </div>

      {/* Rows */}
      <div className="max-h-[480px] overflow-auto">
        {buckets.map((b) => (
          <div
            key={b.label}
            className="flex h-[52px] items-center gap-4 border-b border-[#F0F0F0] px-6 text-[13px] text-foreground last:border-b-0"
          >
            <div className="w-[140px]">{b.label}</div>
            <div className="flex-1 text-center">{b.metrics.session_count.toLocaleString()}</div>
            <div className="flex-1 text-center">{b.metrics.message_count.toLocaleString()}</div>
            <div className="flex-1 text-center">
              {b.metrics.user_message_count.toLocaleString()}
            </div>
            <div className="flex-1 text-center">
              {b.metrics.agent_message_count.toLocaleString()}
            </div>
            <div className="w-[140px] text-center">
              {formatDuration(b.metrics.avg_duration_seconds)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
