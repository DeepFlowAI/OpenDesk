'use client'

import type { ReactNode } from 'react'
import { IconAlertTriangle, IconInfoCircle, IconX } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import type {
  CallReportCoverage,
  CallReportDataQuality,
} from '@/models/call-report-overall'
import { t } from '@/utils/i18n'

type Props = {
  coverage?: CallReportCoverage
  dataQuality?: CallReportDataQuality
}

export function CallReportNotices({ coverage, dataQuality }: Props) {
  const { locale } = useLocaleStore()
  const qualityItems = dataQuality ? [
    ['pending', dataQuality.pending],
    ['incomplete', dataQuality.incomplete],
    ['failed', dataQuality.failed],
    ['satisfactionPending', dataQuality.satisfaction_pending],
  ].filter((item): item is [string, number] => Number(item[1]) > 0) : []

  return (
    <div className="space-y-2">
      {coverage?.truncated ? (
        <Notice icon="info">
          {t('ws.records.callReports.overall.coverage.truncated', locale, {
            time: formatInstant(coverage.effective_at, locale),
          })}
        </Notice>
      ) : null}
      {coverage?.status === 'partial' ? (
        <Notice icon="info">
          {t('ws.records.callReports.overall.coverage.partial', locale, {
            time: formatInstant(coverage.effective_at, locale),
          })}
        </Notice>
      ) : null}
      {qualityItems.length > 0 ? (
        <Notice icon={dataQuality?.failed ? 'error' : 'warning'}>
          <ul className="space-y-1">
            {qualityItems.map(([key, count]) => (
              <li key={key}>
                {t(`ws.records.callReports.overall.quality.${key}`, locale, {
                  count: count.toLocaleString(locale),
                })}
              </li>
            ))}
          </ul>
        </Notice>
      ) : null}
    </div>
  )
}

export function CallHistoryUnavailable({ effectiveAt }: { effectiveAt: string }) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-muted/20 px-6 text-center">
      <IconInfoCircle size={28} className="text-muted-foreground" />
      <p className="text-sm font-medium text-foreground">
        {t('ws.records.callReports.overall.coverage.unavailable', locale)}
      </p>
      <p className="text-xs text-muted-foreground">
        {t('ws.records.callReports.overall.coverage.availableFrom', locale, {
          time: formatInstant(effectiveAt, locale),
        })}
      </p>
    </div>
  )
}

function Notice({ children, icon }: { children: ReactNode; icon: 'info' | 'warning' | 'error' }) {
  const Icon = icon === 'error' ? IconX : icon === 'warning' ? IconAlertTriangle : IconInfoCircle
  const tone = icon === 'error'
    ? 'border-destructive/30 bg-destructive/10'
    : icon === 'warning'
      ? 'border-warning/30 bg-warning/10'
      : 'border-info/30 bg-info/10'
  return (
    <div className={`flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm text-foreground ${tone}`}>
      <Icon size={18} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  )
}

function formatInstant(value: string, locale: string): string {
  const instant = new Date(value)
  if (Number.isNaN(instant.getTime())) return value
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(instant)
}
