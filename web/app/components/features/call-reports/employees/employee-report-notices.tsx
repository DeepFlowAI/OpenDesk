'use client'

import { IconAlertTriangle, IconInfoCircle, IconX } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import type { CallAgentDataQuality } from '@/models/call-agent-report'
import type { CallReportCoverage } from '@/models/call-report-overall'
import { t } from '@/utils/i18n'

export function CallEmployeeReportNotices({ coverage, dataQuality }: {
  coverage?: CallReportCoverage
  dataQuality?: CallAgentDataQuality
}) {
  const { locale } = useLocaleStore()
  const qualityItems = dataQuality ? Object.entries(dataQuality).filter(([, count]) => count > 0) : []
  return <div className="space-y-2">
    {coverage?.status === 'partial' || coverage?.truncated ? <Notice tone="info">
      {t('ws.records.callReports.employees.coverage.partial', locale, { time: formatInstant(coverage.effective_at, locale) })}
    </Notice> : null}
    {qualityItems.length ? <Notice tone={dataQuality?.failed ? 'error' : 'warning'}><ul className="space-y-1">
      {qualityItems.map(([key, count]) => <li key={key}>{t(`ws.records.callReports.employees.quality.${key}`, locale, { count: count.toLocaleString(locale) })}</li>)}
    </ul></Notice> : null}
  </div>
}

export function CallEmployeeHistoryUnavailable({ effectiveAt }: { effectiveAt: string }) {
  const { locale } = useLocaleStore()
  return <div className="flex min-h-[280px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-muted/20 px-6 text-center">
    <IconInfoCircle size={28} className="text-muted-foreground" />
    <p className="text-sm font-medium text-foreground">{t('ws.records.callReports.employees.coverage.unavailable', locale)}</p>
    <p className="text-xs text-muted-foreground">{t('ws.records.callReports.employees.coverage.availableFrom', locale, { time: formatInstant(effectiveAt, locale) })}</p>
  </div>
}

function Notice({ children, tone }: { children: ReactNode; tone: 'info' | 'warning' | 'error' }) {
  const Icon = tone === 'error' ? IconX : tone === 'warning' ? IconAlertTriangle : IconInfoCircle
  const classes = tone === 'error' ? 'border-destructive/30 bg-destructive/10' : tone === 'warning' ? 'border-warning/30 bg-warning/10' : 'border-info/30 bg-info/10'
  return <div className={`flex items-start gap-2.5 rounded-lg border px-4 py-3 text-sm text-foreground ${classes}`}><Icon size={18} className="mt-0.5 shrink-0" /><div>{children}</div></div>
}

function formatInstant(value: string, locale: string): string {
  const instant = new Date(value)
  return Number.isNaN(instant.getTime()) ? value : new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(instant)
}
