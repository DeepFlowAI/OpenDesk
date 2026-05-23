'use client'

import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { formatDuration } from '@/utils/format-duration'
import { EmployeeAvatar } from '@/app/components/features/session-reports/employee-avatar'
import type { EmployeeMonitorRow } from '@/models/online-monitor'
import { CurrentLoad } from './current-load'
import { StatusBadge } from './status-badge'

type Props = {
  rows: EmployeeMonitorRow[]
  loading?: boolean
}

export function EmployeeMonitorTable({ rows, loading }: Props) {
  const { locale } = useLocaleStore()
  return (
    <div>
      <h2 className="mb-3 text-base font-semibold text-foreground">
        {t('ws.records.onlineMonitor.employeesTitle', locale)}
      </h2>
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="flex h-12 items-center gap-3 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
          <div className="w-[220px]">
            {t('ws.records.sessionReports.employees.colEmployee', locale)}
          </div>
          <div className="w-[90px] text-center">
            {t('ws.records.sessionReports.employees.colStatus', locale)}
          </div>
          <div className="w-[110px] text-center">
            {t('ws.records.onlineMonitor.colCurrentLoad', locale)}
          </div>
          <div className="w-[90px] text-center">
            {t('ws.records.onlineMonitor.colTodaySessions', locale)}
          </div>
          <div className="w-[120px] text-center">
            {t('ws.records.sessionReports.overview.avgDuration', locale)}
          </div>
        </div>

        {loading ? (
          <div className="px-6 py-16 text-center text-sm text-muted-foreground">
            {t('ws.records.sessionReports.common.loading', locale)}
          </div>
        ) : rows.length === 0 ? (
          <div className="px-6 py-16 text-center text-sm text-muted-foreground">
            {t('ws.records.onlineMonitor.empty', locale)}
          </div>
        ) : (
          rows.map((row, idx) => {
            const e = row.employee
            return (
              <div
                key={e.id}
                className={cn(
                  'flex h-14 items-center gap-3 border-b border-[#F0F0F0] px-6 text-[13px] last:border-b-0',
                  idx % 2 === 1 ? 'bg-[#FAFAFA]' : 'bg-background'
                )}
              >
                <div className="flex w-[220px] items-center gap-3">
                  <EmployeeAvatar employee={e} />
                  <div className="flex flex-col gap-0.5">
                    <span className="font-semibold text-foreground">
                      {e.display_name ?? e.name}
                    </span>
                    {e.email && (
                      <span className="text-xs text-muted-foreground">{e.email}</span>
                    )}
                  </div>
                </div>
                <div className="w-[90px] text-center">
                  <StatusBadge status={row.status} />
                </div>
                <div className="w-[110px] text-center">
                  <CurrentLoad current={row.current_count} max={row.max_concurrent} />
                </div>
                <div className="w-[90px] text-center">{row.session_count.toLocaleString()}</div>
                <div className="w-[120px] text-center">
                  {formatDuration(row.avg_duration_seconds)}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
