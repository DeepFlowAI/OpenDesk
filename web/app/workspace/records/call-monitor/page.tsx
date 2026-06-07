'use client'

import { IconRefresh } from '@tabler/icons-react'
import { EmployeeCallMonitorTable } from '@/app/components/features/call-monitor/employee-call-monitor-table'
import { CallMonitorTodayCards } from '@/app/components/features/call-monitor/today-cards'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { useCallMonitor } from '@/service/use-call-monitor'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'

function formatTime(asOf?: string | null): string {
  if (!asOf) return '—'
  const d = new Date(asOf)
  if (Number.isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatRangeLabel(asOf: string | undefined, locale: 'zh' | 'en', fallback?: string): string {
  if (!asOf) return fallback ?? ''
  const d = new Date(asOf)
  if (Number.isNaN(d.getTime())) return fallback ?? ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return t('ws.records.callMonitor.rangeToday', locale, {
    start: '00:00',
    end: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  })
}

export default function CallMonitorPage() {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const canView = hasPermission(user, 'call.monitor.view')
  const { data, isFetching, isError, failureCount, refetch } = useCallMonitor(canView)

  if (!canView) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {t('ws.records.callMonitor.noPermission', locale)}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold text-foreground">
              {t('ws.records.callMonitor.title', locale)}
            </h1>
            <span className="text-[13px] text-muted-foreground">
              {formatRangeLabel(data?.as_of, locale, data?.today.range_label)}
            </span>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-4">
            {failureCount >= 2 && data && (
              <span className="text-xs text-warning">
                {t('ws.records.callMonitor.outdated', locale)}
              </span>
            )}
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              aria-label={t('ws.records.sessionReports.toolbar.refresh', locale)}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-background text-foreground',
                isFetching ? 'cursor-not-allowed opacity-50' : 'hover:bg-muted/50'
              )}
            >
              <IconRefresh size={16} className={isFetching ? 'animate-spin' : ''} />
            </button>
            <span className="text-xs text-muted-foreground">
              {t('ws.records.sessionReports.toolbar.lastUpdated', locale, {
                time: formatTime(data?.as_of),
              })}
            </span>
          </div>
        </div>

        {isError && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {t('ws.records.callMonitor.errorLoad', locale)}
          </div>
        )}

        <CallMonitorTodayCards data={data?.today} loading={!data && isFetching} />
        <EmployeeCallMonitorTable rows={data?.employees ?? []} loading={!data && isFetching} />
      </div>
    </div>
  )
}
