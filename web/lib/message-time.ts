import type { Locale } from '@/lib/languages'
import { t } from '@/utils/i18n'

export type FormatMessageTimeOptions = {
  /** Keep HH:mm:ss when the existing message timestamp already showed seconds. */
  seconds?: boolean
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function formatClock(date: Date, seconds: boolean): string {
  const hh = pad2(date.getHours())
  const mm = pad2(date.getMinutes())
  if (!seconds) return `${hh}:${mm}`
  return `${hh}:${mm}:${pad2(date.getSeconds())}`
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

/**
 * Format an already-visible chat message time:
 * today = clock, yesterday = localized "yesterday" + clock,
 * same year = MM-DD + clock, other year = YYYY-MM-DD + clock.
 */
export function formatMessageTime(
  input: string | Date,
  locale: Locale,
  options: FormatMessageTimeOptions = {},
): string {
  const date = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const time = formatClock(date, options.seconds === true)
  const dayMs = 24 * 60 * 60 * 1000
  const dayDiff = Math.round(
    (startOfLocalDay(now).getTime() - startOfLocalDay(date).getTime()) / dayMs,
  )

  if (dayDiff === 0) return time
  if (dayDiff === 1) return t('chat.time.yesterday', locale, { time })
  if (date.getFullYear() === now.getFullYear()) {
    return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${time}`
  }
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${time}`
}
