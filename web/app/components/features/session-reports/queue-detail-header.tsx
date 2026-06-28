'use client'

import Link from 'next/link'
import { IconArrowLeft } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import type { QueueBrief } from '@/models/session-report'
import { queueStatusLabelKey, queueTypeLabelKey } from './queue-types'

type Props = {
  queue: QueueBrief
  carriedSearch: string
}

export function QueueDetailHeader({ queue, carriedSearch }: Props) {
  const { locale } = useLocaleStore()
  const tail = carriedSearch ? `?${carriedSearch.replace(/^\?/, '')}` : ''

  return (
    <div className="flex flex-col gap-3">
      <Link
        href={`/workspace/records/session-reports/queues${tail}`}
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <IconArrowLeft size={16} />
        {t('ws.records.sessionReports.queues.backToList', locale)}
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {t(queueTypeLabelKey[queue.queue_type], locale)}
        </span>
        <span className="text-lg font-semibold text-foreground">{queue.name}</span>
        <span
          className={cn(
            'inline-flex items-center rounded-md px-2 py-0.5 text-xs',
            queue.status === 'active'
              ? 'bg-[#F0FDF4] text-[#16A34A]'
              : queue.status === 'inactive'
                ? 'bg-[#F5F5F5] text-[#737373]'
                : 'bg-[#FEF2F2] text-[#DC2626]'
          )}
        >
          {t(queueStatusLabelKey[queue.status], locale)}
        </span>
      </div>
    </div>
  )
}
