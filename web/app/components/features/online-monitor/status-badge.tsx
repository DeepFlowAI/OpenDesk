'use client'

import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { OnlineStatus } from '@/models/online-monitor'

const STATUS_STYLE: Record<OnlineStatus, { bg: string; dot: string; text: string; border?: string }> = {
  online: { bg: 'bg-[#F0FDF4]', dot: 'bg-[#16A34A]', text: 'text-[#16A34A]' },
  busy: { bg: 'bg-[#FFFBEB]', dot: 'bg-[#D97706]', text: 'text-[#D97706]' },
  offline: { bg: 'bg-[#F5F5F5]', dot: 'bg-[#737373]', text: 'text-[#737373]' },
  unknown: {
    bg: 'bg-[#F5F5F5]',
    dot: 'bg-[#737373]',
    text: 'text-[#737373]',
    border: 'border border-dashed border-[#D4D4D4]',
  },
}

const STATUS_LABEL_KEY: Record<OnlineStatus, string> = {
  online: 'ws.records.onlineMonitor.status.online',
  busy: 'ws.records.onlineMonitor.status.busy',
  offline: 'ws.records.onlineMonitor.status.offline',
  unknown: 'ws.records.onlineMonitor.status.unknown',
}

export function StatusBadge({ status }: { status: OnlineStatus }) {
  const { locale } = useLocaleStore()
  const style = STATUS_STYLE[status]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs',
        style.bg,
        style.text,
        style.border
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', style.dot)} aria-hidden />
      {t(STATUS_LABEL_KEY[status], locale)}
    </span>
  )
}
