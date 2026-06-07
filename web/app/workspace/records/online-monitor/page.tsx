'use client'

import { IconRefresh } from '@tabler/icons-react'
import { EmployeeMonitorTable } from '@/app/components/features/online-monitor/employee-monitor-table'
import { TodayCards } from '@/app/components/features/online-monitor/today-cards'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useOnlineMonitor } from '@/service/use-online-monitor'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'

function formatTime(asOf?: string | null): string {
  if (!asOf) return '—'
  const d = new Date(asOf)
  if (isNaN(d.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export default function OnlineMonitorPage() {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const canView = hasPermission(user, 'chat.online_monitor.view')
  const { data, isFetching, isError, refetch } = useOnlineMonitor(canView)

  if (!canView) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-sm text-muted-foreground">
        {t('ws.records.onlineMonitor.noPermission', locale)}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold text-foreground">
              {t('ws.records.onlineMonitor.title', locale)}
            </h1>
            <span className="text-[13px] text-muted-foreground">
              {data?.today.range_label ?? ''}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              aria-label={t('ws.records.sessionReports.toolbar.refresh', locale)}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-background text-[#404040]',
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
          <div className="rounded-lg border border-[#FDA4A4] bg-[#FEF2F2] px-4 py-2 text-sm text-[#DC2626]">
            {t('ws.records.onlineMonitor.errorLoad', locale)}
          </div>
        )}

        <TodayCards data={data?.today} loading={!data && isFetching} />
        <EmployeeMonitorTable rows={data?.employees ?? []} loading={!data && isFetching} />
      </div>
    </div>
  )
}
