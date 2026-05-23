'use client'

import Link from 'next/link'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import type { EmployeeBrief } from '@/models/session-report'
import { EmployeeAvatar } from './employee-avatar'

type Props = {
  employee: EmployeeBrief
  carriedSearch: string
}

export function EmployeeDetailHeader({ employee, carriedSearch }: Props) {
  const { locale } = useLocaleStore()
  const tail = carriedSearch ? `?${carriedSearch.replace(/^\?/, '')}` : ''

  return (
    <div className="flex flex-col gap-3">
      <Link
        href={`/workspace/records/session-reports/employees${tail}`}
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <IconArrowLeft size={16} />
        {t('ws.records.sessionReports.employees.backToList', locale)}
      </Link>
      <div className="flex items-center gap-3">
        <EmployeeAvatar employee={employee} size={40} />
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold text-foreground">
            {employee.display_name ?? employee.name}
          </span>
          <span
            className={cn(
              'inline-flex items-center rounded-md px-2 py-0.5 text-xs',
              employee.is_active ? 'bg-[#F0FDF4] text-[#16A34A]' : 'bg-[#F5F5F5] text-[#737373]'
            )}
          >
            {employee.is_active
              ? t('ws.records.sessionReports.employees.statusActive', locale)
              : t('ws.records.sessionReports.employees.statusInactive', locale)}
          </span>
        </div>
      </div>
    </div>
  )
}
