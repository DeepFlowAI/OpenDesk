'use client'

import { useLocaleStore } from '@/context/locale-store'
import type { CallTrendBucket } from '@/models/call-report'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'

type Props = {
  buckets: CallTrendBucket[]
}

export function CallTrendTable({ buckets }: Props) {
  const { locale } = useLocaleStore()
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex h-12 min-w-[980px] items-center gap-4 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
        <div className="w-[120px]">{t('ws.records.callReports.trend.colTime', locale)}</div>
        <div className="w-[100px] text-center">{t('ws.records.callReports.overview.totalCalls', locale)}</div>
        <div className="w-[100px] text-center">{t('ws.records.callReports.overview.inboundCalls', locale)}</div>
        <div className="w-[130px] text-center">{t('ws.records.callReports.overview.answeredInboundCalls', locale)}</div>
        <div className="w-[100px] text-center">{t('ws.records.callReports.overview.outboundCalls', locale)}</div>
        <div className="w-[130px] text-center">{t('ws.records.callReports.overview.answeredOutboundCalls', locale)}</div>
        <div className="w-[140px] text-center">{t('ws.records.callReports.overview.avgInboundTalkTime', locale)}</div>
        <div className="w-[140px] text-center">{t('ws.records.callReports.overview.avgOutboundTalkTime', locale)}</div>
      </div>

      <div className="max-h-[480px] overflow-auto">
        {buckets.map((bucket) => (
          <div
            key={bucket.label}
            className="flex h-[52px] min-w-[980px] items-center gap-4 border-b border-[#F0F0F0] px-6 text-[13px] text-foreground last:border-b-0"
          >
            <div className="w-[120px]">{bucket.label}</div>
            <div className="w-[100px] text-center">{bucket.metrics.total_calls.toLocaleString()}</div>
            <div className="w-[100px] text-center">{bucket.metrics.inbound_calls.toLocaleString()}</div>
            <div className="w-[130px] text-center">{bucket.metrics.answered_inbound_calls.toLocaleString()}</div>
            <div className="w-[100px] text-center">{bucket.metrics.outbound_calls.toLocaleString()}</div>
            <div className="w-[130px] text-center">{bucket.metrics.answered_outbound_calls.toLocaleString()}</div>
            <div className="w-[140px] text-center">{formatDuration(bucket.metrics.avg_inbound_talk_seconds)}</div>
            <div className="w-[140px] text-center">{formatDuration(bucket.metrics.avg_outbound_talk_seconds)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
