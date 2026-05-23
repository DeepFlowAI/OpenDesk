'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { formatDuration } from '@/utils/format-duration'
import type { TodayOverview } from '@/models/online-monitor'

type Props = {
  data: TodayOverview | undefined
  loading?: boolean
}

export function TodayCards({ data, loading }: Props) {
  const { locale } = useLocaleStore()
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold text-foreground">
        {t('ws.records.onlineMonitor.todayTitle', locale)}
      </h2>
      <div className="flex gap-4">
        <Card
          labelKey="ws.records.onlineMonitor.todaySessions"
          value={data ? data.session_count.toLocaleString() : '0'}
          loading={loading}
        />
        <Card
          labelKey="ws.records.sessionReports.overview.avgDuration"
          value={data ? formatDuration(data.avg_duration_seconds) : '—'}
          loading={loading}
        />
      </div>
    </div>
  )
}

function Card({ labelKey, value, loading }: { labelKey: string; value: string; loading?: boolean }) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex h-24 flex-1 flex-col justify-center gap-2 rounded-[10px] border border-border bg-background px-5 py-4">
      <span className="text-sm text-muted-foreground">{t(labelKey, locale)}</span>
      {loading ? (
        <span className="h-8 w-16 animate-pulse rounded bg-muted" aria-busy="true" />
      ) : (
        <span className="text-[32px] font-semibold leading-none tracking-tight text-foreground">
          {value}
        </span>
      )}
    </div>
  )
}
