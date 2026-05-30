'use client'

import Link from 'next/link'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

type Props = {
  active: 'overall' | 'employees'
  search?: string
}

export function CallReportTabs({ active, search = '' }: Props) {
  const { locale } = useLocaleStore()
  const tail = search ? `?${search.replace(/^\?/, '')}` : ''

  const items: { key: 'overall' | 'employees'; href: string; labelKey: string }[] = [
    {
      key: 'overall',
      href: `/workspace/records/call-reports${tail}`,
      labelKey: 'ws.records.callReports.tabs.overall',
    },
    {
      key: 'employees',
      href: `/workspace/records/call-reports/employees${tail}`,
      labelKey: 'ws.records.callReports.tabs.employees',
    },
  ]

  return (
    <div className="flex border-b border-border">
      {items.map((item) => {
        const isActive = item.key === active
        return (
          <Link
            key={item.key}
            href={item.href}
            className={cn(
              'px-4 pb-3 pt-0 text-sm transition-colors',
              isActive
                ? 'border-b-2 border-foreground font-semibold text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {t(item.labelKey, locale)}
          </Link>
        )
      })}
    </div>
  )
}
