'use client'

import { useMemo } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  IconAlertCircle,
  IconCalendarOff,
  IconChevronLeft,
  IconChevronRight,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import type { Locale } from '@/context/locale-store'
import type { MyScheduleDay, MyScheduleShift } from '@/models/scheduling'
import { useMySchedule } from '@/service/use-scheduling'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

function addDays(isoDate: string, amount: number): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  const value = new Date(Date.UTC(year, month - 1, day + amount))
  return value.toISOString().slice(0, 10)
}

function browserWeekStart(): string {
  const now = new Date()
  const mondayOffset = (now.getDay() + 6) % 7
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - mondayOffset)
  return [
    monday.getFullYear(),
    String(monday.getMonth() + 1).padStart(2, '0'),
    String(monday.getDate()).padStart(2, '0'),
  ].join('-')
}

function dayLabel(isoDate: string, locale: Locale): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'numeric',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}

function ShiftChip({ shift, locale }: { shift: MyScheduleShift; locale: Locale }) {
  const isLeave = shift.shift_type === 'leave'
  const name = shift.is_deleted
    ? t('scheduling.my.deletedShift', locale, { id: shift.id })
    : shift.name
  const timeRange = shift.start_time && shift.end_time
    ? `${shift.start_time}–${shift.end_time}`
    : null

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-white"
      style={{ backgroundColor: shift.color }}
    >
      {isLeave ? <IconCalendarOff size={14} /> : null}
      <span>{name}</span>
      {isLeave ? (
        <span className="opacity-90">{t('scheduling.shifts.allDay', locale)}</span>
      ) : timeRange ? (
        <span className="opacity-90">{timeRange}</span>
      ) : null}
    </span>
  )
}

function WeekToolbar({
  weekStart,
  weekEnd,
  isCurrentWeek,
  locale,
  onChange,
}: {
  weekStart: string
  weekEnd: string
  isCurrentWeek: boolean
  locale: Locale
  onChange: (week?: string) => void
}) {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-border bg-background px-6 py-3">
      <button
        type="button"
        onClick={() => onChange(addDays(weekStart, -7))}
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        aria-label={t('scheduling.my.previousWeek', locale)}
      >
        <IconChevronLeft size={16} />
      </button>
      <div className="min-w-[220px] text-center text-sm font-medium tabular-nums">
        {weekStart} ~ {weekEnd}
      </div>
      <button
        type="button"
        onClick={() => onChange(addDays(weekStart, 7))}
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        aria-label={t('scheduling.my.nextWeek', locale)}
      >
        <IconChevronRight size={16} />
      </button>
      <button
        type="button"
        onClick={() => onChange()}
        disabled={isCurrentWeek}
        className="ml-1 h-8 rounded-md border border-border bg-background px-3 text-sm text-foreground transition-colors hover:bg-accent disabled:pointer-events-none disabled:opacity-50"
      >
        {t('scheduling.my.thisWeek', locale)}
      </button>
      <span className="ml-auto text-xs text-muted-foreground">
        {t('scheduling.my.readonlyHint', locale)}
      </span>
    </div>
  )
}

function TodaySummary({ day, locale }: { day: MyScheduleDay; locale: Locale }) {
  return (
    <div className="flex shrink-0 items-center gap-3 border-b border-border bg-accent/40 px-6 py-3">
      <span className="text-sm font-medium">{t('scheduling.my.todayLabel', locale)}</span>
      {day.shifts.length ? (
        <div className="flex flex-wrap gap-2">
          {day.shifts.map((shift) => <ShiftChip key={shift.id} shift={shift} locale={locale} />)}
        </div>
      ) : (
        <span className="text-sm text-muted-foreground">{t('scheduling.my.noShiftToday', locale)}</span>
      )}
    </div>
  )
}

function DayList({ days, today, locale }: { days: MyScheduleDay[]; today: string; locale: Locale }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
      <div className="overflow-hidden rounded-lg border border-border bg-background">
        {days.map((day, index) => {
          const date = new Date(`${day.date}T00:00:00Z`)
          const isToday = day.date === today
          return (
            <div
              key={day.date}
              className={cn(
                'flex items-center gap-4 px-4 py-3.5',
                index > 0 && 'border-t border-border',
                isToday && 'bg-accent/50',
              )}
            >
              <div className="w-24 shrink-0">
                <div className="text-sm font-medium">
                  {t(`scheduling.board.weekday.${date.getUTCDay()}`, locale)}
                  {isToday ? (
                    <span className="ml-1.5 text-xs font-normal text-primary">
                      {t('scheduling.my.today', locale)}
                    </span>
                  ) : null}
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">{dayLabel(day.date, locale)}</div>
              </div>
              <div className="flex min-w-0 flex-1 flex-wrap gap-2">
                {day.shifts.length
                  ? day.shifts.map((shift) => <ShiftChip key={shift.id} shift={shift} locale={locale} />)
                  : <span className="text-sm text-muted-foreground">{t('scheduling.my.off', locale)}</span>}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StatePanel({ title, description, error, onRetry, retryLabel }: {
  title: string
  description?: string
  error?: boolean
  onRetry?: () => void
  retryLabel?: string
}) {
  const Icon = error ? IconAlertCircle : IconCalendarOff
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center px-6 py-8">
      <div className="flex h-[360px] w-full max-w-2xl flex-col items-center justify-center rounded-lg border border-dashed border-border bg-background/60 px-6 text-center">
        <span className="mb-4 rounded-lg bg-muted p-3 text-muted-foreground"><Icon size={24} /></span>
        <p className="text-sm font-medium">{title}</p>
        {description ? <p className="mt-2 text-xs text-muted-foreground">{description}</p> : null}
        {onRetry && retryLabel ? (
          <button type="button" onClick={onRetry} className="mt-4 h-8 rounded-md border border-border px-3 text-sm hover:bg-accent">
            {retryLabel}
          </button>
        ) : null}
      </div>
    </div>
  )
}

function LoadingDays() {
  return (
    <div className="min-h-0 flex-1 px-6 py-4">
      <div className="overflow-hidden rounded-lg border border-border bg-background">
        {Array.from({ length: 7 }, (_, index) => (
          <div key={index} className={cn('flex h-[68px] items-center gap-4 px-4', index > 0 && 'border-t border-border')}>
            <div className="h-8 w-20 animate-pulse rounded bg-muted" />
            <div className="h-7 w-44 animate-pulse rounded-md bg-muted" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function MyScheduleView() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()
  const requestedWeek = searchParams.get('week') || undefined
  const query = useMySchedule(requestedWeek)
  const fallbackStart = useMemo(() => requestedWeek ?? browserWeekStart(), [requestedWeek])
  const weekStart = query.data?.week_start ?? fallbackStart
  const weekEnd = query.data?.week_end ?? addDays(weekStart, 6)
  const isCurrentWeek = query.data
    ? query.data.today >= query.data.week_start && query.data.today <= query.data.week_end
    : !requestedWeek
  const todayDay = query.data?.days.find((day) => day.date === query.data?.today)
  const hasShifts = query.data?.days.some((day) => day.shifts.length) ?? false

  const changeWeek = (week?: string) => {
    router.push(week ? `/scheduling/me?week=${week}` : '/scheduling/me')
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <WeekToolbar weekStart={weekStart} weekEnd={weekEnd} isCurrentWeek={isCurrentWeek} locale={locale} onChange={changeWeek} />
      {query.isLoading ? <LoadingDays /> : null}
      {query.isError ? (
        <StatePanel
          title={t('scheduling.my.loadFailed', locale)}
          error
          onRetry={() => void query.refetch()}
          retryLabel={t('scheduling.my.retry', locale)}
        />
      ) : null}
      {query.data && !query.data.is_published ? (
        <StatePanel title={t('scheduling.my.unpublished', locale)} description={t('scheduling.my.unpublishedHint', locale)} />
      ) : null}
      {query.data?.is_published && todayDay ? <TodaySummary day={todayDay} locale={locale} /> : null}
      {query.data?.is_published && !hasShifts ? (
        <StatePanel title={t('scheduling.my.noShifts', locale)} description={t('scheduling.my.noShiftsHint', locale)} />
      ) : null}
      {query.data?.is_published && hasShifts ? <DayList days={query.data.days} today={query.data.today} locale={locale} /> : null}
    </div>
  )
}
