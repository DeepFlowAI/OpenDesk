'use client'

import Link from 'next/link'
import { IconArrowLeft } from '@tabler/icons-react'
import { EmployeeAvatar } from '@/app/components/features/session-reports/employee-avatar'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import type { CallEmployeeBrief } from '@/models/call-report'

type Props = {
  employee: CallEmployeeBrief
  carriedSearch: string
}

export function CallEmployeeDetailHeader({ employee, carriedSearch }: Props) {
  const { locale } = useLocaleStore()
  const tail = carriedSearch ? `?${carriedSearch.replace(/^\?/, '')}` : ''

  return (
    <div className="flex flex-col gap-3">
      <Link
        href={`/workspace/records/call-reports/employees${tail}`}
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <IconArrowLeft size={16} />
        {t('ws.records.callReports.employees.backToList', locale)}
      </Link>
      <div className="flex items-center gap-3">
        <EmployeeAvatar employee={employee} size={40} />
        <div className="flex min-w-0 items-center gap-3">
          <span className="truncate text-lg font-semibold text-foreground">
            {employee.display_name ?? employee.name}
          </span>
          <span
            className={cn(
              'inline-flex shrink-0 items-center rounded-md px-2 py-0.5 text-xs',
              employee.is_active
                ? 'bg-success/10 text-success'
                : 'bg-muted text-muted-foreground'
            )}
          >
            {employee.is_active
              ? t('ws.records.callReports.employees.statusActive', locale)
              : t('ws.records.callReports.employees.statusInactive', locale)}
          </span>
        </div>
      </div>
    </div>
  )
}
