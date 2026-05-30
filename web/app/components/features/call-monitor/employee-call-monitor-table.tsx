'use client'

import { EmployeeAvatar } from '@/app/components/features/session-reports/employee-avatar'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import type { CallMonitorEmployeeRow } from '@/models/call-monitor'
import type { AgentStatus } from '@/models/call-center'

type Props = {
  rows: CallMonitorEmployeeRow[]
  loading?: boolean
}

const COLUMNS: {
  key: 'answered_inbound_calls' | 'outbound_calls' | 'answered_outbound_calls'
  labelKey: string
  width: string
}[] = [
  {
    key: 'answered_inbound_calls',
    labelKey: 'ws.records.callReports.overview.answeredInboundCalls',
    width: 'w-[128px]',
  },
  {
    key: 'outbound_calls',
    labelKey: 'ws.records.callReports.overview.outboundCalls',
    width: 'w-[104px]',
  },
  {
    key: 'answered_outbound_calls',
    labelKey: 'ws.records.callReports.overview.answeredOutboundCalls',
    width: 'w-[128px]',
  },
]

const STATUS_STYLE: Record<AgentStatus, { bg: string; dot: string; text: string }> = {
  ready: { bg: 'bg-success/10', dot: 'bg-success', text: 'text-success' },
  busy: { bg: 'bg-destructive/10', dot: 'bg-destructive', text: 'text-destructive' },
  break: { bg: 'bg-warning/10', dot: 'bg-warning', text: 'text-warning' },
  after_call_work: { bg: 'bg-warning/10', dot: 'bg-warning', text: 'text-warning' },
  offline: { bg: 'bg-muted', dot: 'bg-muted-foreground', text: 'text-muted-foreground' },
}

const STATUS_LABEL_KEY: Record<AgentStatus, string> = {
  ready: 'ws.records.callMonitor.status.ready',
  busy: 'ws.records.callMonitor.status.busy',
  break: 'ws.records.callMonitor.status.break',
  after_call_work: 'ws.records.callMonitor.status.afterCallWork',
  offline: 'ws.records.callMonitor.status.offline',
}

export function EmployeeCallMonitorTable({ rows, loading }: Props) {
  const { locale } = useLocaleStore()

  return (
    <div>
      <h2 className="mb-3 text-base font-semibold text-foreground">
        {t('ws.records.callMonitor.employeesTitle', locale)}
      </h2>
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="overflow-x-auto">
          <div className="flex h-12 min-w-[860px] items-center gap-3 bg-muted/60 px-6 text-xs font-semibold text-muted-foreground">
            <div className="w-[220px]">
              {t('ws.records.callReports.employees.colEmployee', locale)}
            </div>
            <div className="w-[128px] text-center">
              {t('ws.records.callMonitor.colCallCenterStatus', locale)}
            </div>
            {COLUMNS.map((column) => (
              <div key={column.key} className={cn(column.width, 'text-center')}>
                {t(column.labelKey, locale)}
              </div>
            ))}
          </div>

          {loading ? (
            <div className="min-w-[860px] px-6 py-16 text-center text-sm text-muted-foreground">
              {t('ws.records.sessionReports.common.loading', locale)}
            </div>
          ) : rows.length === 0 ? (
            <div className="min-w-[860px] px-6 py-16 text-center text-sm text-muted-foreground">
              {t('ws.records.callMonitor.empty', locale)}
            </div>
          ) : (
            rows.map((row, index) => {
              const employee = row.employee
              return (
                <div
                  key={employee.id}
                  className={cn(
                    'flex h-14 min-w-[860px] select-text items-center gap-3 border-b border-border px-6 text-[13px] text-foreground transition-colors last:border-b-0 hover:bg-muted/35',
                    index % 2 === 1 ? 'bg-muted/20' : 'bg-background'
                  )}
                >
                  <div className="flex w-[220px] items-center gap-3">
                    <EmployeeAvatar employee={employee} />
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <span className="truncate font-semibold text-foreground">
                        {employee.display_name ?? employee.name}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        {employee.username ?? employee.email ?? '—'}
                      </span>
                    </div>
                  </div>
                  <div className="w-[128px] text-center">
                    <CallCenterStatusBadge status={row.call_center_status} />
                  </div>
                  {COLUMNS.map((column) => (
                    <div key={column.key} className={cn(column.width, 'text-center')}>
                      {row[column.key].toLocaleString()}
                    </div>
                  ))}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

function CallCenterStatusBadge({ status }: { status: AgentStatus }) {
  const { locale } = useLocaleStore()
  const style = STATUS_STYLE[status] ?? STATUS_STYLE.offline
  const labelKey = STATUS_LABEL_KEY[status] ?? STATUS_LABEL_KEY.offline

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium',
        style.bg,
        style.text
      )}
    >
      <span className={cn('size-1.5 rounded-full', style.dot)} />
      {t(labelKey, locale)}
    </span>
  )
}
