'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { PublishStatus } from '@/models/scheduling'

function formatPublishedAt(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const STATE_STYLES = {
  unpublished: 'border-border bg-muted text-muted-foreground',
  published: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  dirty: 'border-amber-200 bg-amber-50 text-amber-700',
} as const

/** Publish state badge for the current week: unpublished / published+time / dirty. */
export function PublishTag({ status }: { status: PublishStatus }) {
  const { locale } = useLocaleStore()
  const label =
    status.state === 'published' && status.published_at
      ? t('scheduling.board.publishTag.published', locale, {
          time: formatPublishedAt(status.published_at),
        })
      : t(`scheduling.board.publishTag.${status.state}`, locale)
  return (
    <span
      className={`inline-flex h-9 items-center rounded-md border px-2.5 text-xs font-medium ${STATE_STYLES[status.state]}`}
    >
      {label}
    </span>
  )
}
