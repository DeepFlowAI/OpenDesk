import type {
  CreateServiceHoursPayload,
  HolidayEntry,
  MakeupDayEntry,
  TimeSlot,
  WeeklySchedule,
} from '@/models/service-hours'

export const DEFAULT_SYSTEM_TIMEZONE = 'Asia/Shanghai'

type DateParts = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
}

type LocalDateParts = Omit<DateParts, 'hour' | 'minute'>

const DATE_TIME_LOCAL_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

function isoDayFromUtcDate(date: Date): number {
  const day = date.getUTCDay()
  return day === 0 ? 7 : day
}

function addDays(parts: LocalDateParts, days: number): LocalDateParts {
  const date = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + days))
  return {
    year: date.getUTCFullYear(),
    month: date.getUTCMonth() + 1,
    day: date.getUTCDate(),
  }
}

function parseTime(value: string): { hour: number; minute: number } | null {
  const [hour, minute] = value.split(':').map(Number)
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) return null
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null
  return { hour, minute }
}

function formatTime(hour: number, minute: number): string {
  return `${pad(hour)}:${pad(minute)}`
}

function getZonedParts(date: Date, timeZone: string): DateParts {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
  const parts = formatter.formatToParts(date)
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value ?? 0)

  return {
    year: get('year'),
    month: get('month'),
    day: get('day'),
    hour: get('hour'),
    minute: get('minute'),
  }
}

function getTimeZoneOffsetMs(date: Date, timeZone: string): number {
  const parts = getZonedParts(date, timeZone)
  const zonedAsUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
  )
  return zonedAsUtc - date.getTime()
}

function zonedLocalToUtc(parts: DateParts, timeZone: string): Date {
  const localAsUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
  )
  let utcTime = localAsUtc

  for (let i = 0; i < 3; i += 1) {
    utcTime = localAsUtc - getTimeZoneOffsetMs(new Date(utcTime), timeZone)
  }

  return new Date(utcTime)
}

function parseDateTimeLocal(value: string): DateParts | null {
  const match = value.match(DATE_TIME_LOCAL_RE)
  if (!match) return null

  const [, year, month, day, hour, minute] = match
  return {
    year: Number(year),
    month: Number(month),
    day: Number(day),
    hour: Number(hour),
    minute: Number(minute),
  }
}

function formatDateTimeLocal(parts: DateParts): string {
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}`
}

function getReferenceLocalDate(dayOfWeek: number, timeZone: string): LocalDateParts {
  const nowParts = getZonedParts(new Date(), timeZone)
  const todayAsUtcDate = new Date(Date.UTC(nowParts.year, nowParts.month - 1, nowParts.day))
  const todayIsoDay = isoDayFromUtcDate(todayAsUtcDate)
  return addDays(nowParts, dayOfWeek - todayIsoDay)
}

function getReferenceUtcDate(dayOfWeek: number): LocalDateParts {
  const now = new Date()
  const todayUtc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
  return addDays(
    {
      year: todayUtc.getUTCFullYear(),
      month: todayUtc.getUTCMonth() + 1,
      day: todayUtc.getUTCDate(),
    },
    dayOfWeek - isoDayFromUtcDate(todayUtc),
  )
}

function addSlot(target: Map<number, TimeSlot[]>, dayOfWeek: number, slot: TimeSlot) {
  target.set(dayOfWeek, [...(target.get(dayOfWeek) ?? []), slot])
}

function normalizeSchedules(slotsByDay: Map<number, TimeSlot[]>): WeeklySchedule[] {
  return Array.from(slotsByDay.entries())
    .sort(([a], [b]) => a - b)
    .map(([dayOfWeek, slots]) => ({
      day_of_week: dayOfWeek,
      slots: slots.sort((a, b) => a.start.localeCompare(b.start)),
    }))
}

function addUtcSegments(target: Map<number, TimeSlot[]>, start: Date, end: Date) {
  let cursor = start

  while (cursor.getTime() <= end.getTime()) {
    const dayEnd = new Date(Date.UTC(
      cursor.getUTCFullYear(),
      cursor.getUTCMonth(),
      cursor.getUTCDate(),
      23,
      59,
    ))
    const segmentEnd = end.getTime() < dayEnd.getTime() ? end : dayEnd

    addSlot(target, isoDayFromUtcDate(cursor), {
      start: formatTime(cursor.getUTCHours(), cursor.getUTCMinutes()),
      end: formatTime(segmentEnd.getUTCHours(), segmentEnd.getUTCMinutes()),
    })

    if (segmentEnd.getTime() >= end.getTime()) break
    cursor = new Date(Date.UTC(
      cursor.getUTCFullYear(),
      cursor.getUTCMonth(),
      cursor.getUTCDate() + 1,
      0,
      0,
    ))
  }
}

export function zonedWeeklySchedulesToUtc(
  schedules: WeeklySchedule[],
  timeZone: string,
): WeeklySchedule[] {
  const slotsByDay = new Map<number, TimeSlot[]>()

  for (const schedule of schedules) {
    const referenceDate = getReferenceLocalDate(schedule.day_of_week, timeZone)

    for (const slot of schedule.slots) {
      const startTime = parseTime(slot.start)
      const endTime = parseTime(slot.end)
      if (!startTime || !endTime) continue

      const endDate = endTime.hour < startTime.hour
        || (endTime.hour === startTime.hour && endTime.minute < startTime.minute)
        ? addDays(referenceDate, 1)
        : referenceDate

      const startUtc = zonedLocalToUtc({ ...referenceDate, ...startTime }, timeZone)
      const endUtc = zonedLocalToUtc({ ...endDate, ...endTime }, timeZone)
      addUtcSegments(slotsByDay, startUtc, endUtc)
    }
  }

  return normalizeSchedules(slotsByDay)
}

export function utcWeeklySchedulesToZoned(
  schedules: WeeklySchedule[],
  timeZone: string,
): WeeklySchedule[] {
  const slotsByDay = new Map<number, TimeSlot[]>()

  for (const schedule of schedules) {
    const referenceDate = getReferenceUtcDate(schedule.day_of_week)

    for (const slot of schedule.slots) {
      const startTime = parseTime(slot.start)
      const endTime = parseTime(slot.end)
      if (!startTime || !endTime) continue

      const endDate = endTime.hour < startTime.hour
        || (endTime.hour === startTime.hour && endTime.minute < startTime.minute)
        ? addDays(referenceDate, 1)
        : referenceDate

      const startLocal = getZonedParts(new Date(Date.UTC(
        referenceDate.year,
        referenceDate.month - 1,
        referenceDate.day,
        startTime.hour,
        startTime.minute,
      )), timeZone)
      const endLocal = getZonedParts(new Date(Date.UTC(
        endDate.year,
        endDate.month - 1,
        endDate.day,
        endTime.hour,
        endTime.minute,
      )), timeZone)
      const localDay = isoDayFromUtcDate(new Date(Date.UTC(
        startLocal.year,
        startLocal.month - 1,
        startLocal.day,
      )))

      addSlot(slotsByDay, localDay, {
        start: formatTime(startLocal.hour, startLocal.minute),
        end: formatTime(endLocal.hour, endLocal.minute),
      })
    }
  }

  return normalizeSchedules(slotsByDay)
}

function zonedDateTimeToUtcString(value: string, timeZone: string): string {
  const parts = parseDateTimeLocal(value)
  if (!parts) return value
  return zonedLocalToUtc(parts, timeZone).toISOString()
}

function utcDateTimeToZonedLocal(value: string, timeZone: string): string {
  if (!value.trim()) return value
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return formatDateTimeLocal(getZonedParts(date, timeZone))
}

function zonedDateTimeEntriesToUtc<T extends HolidayEntry | MakeupDayEntry>(
  entries: T[],
  timeZone: string,
): T[] {
  return entries.map((entry) => ({
    ...entry,
    start: zonedDateTimeToUtcString(entry.start, timeZone),
    end: zonedDateTimeToUtcString(entry.end, timeZone),
  }))
}

function utcDateTimeEntriesToZoned<T extends HolidayEntry | MakeupDayEntry>(
  entries: T[],
  timeZone: string,
): T[] {
  return entries.map((entry) => ({
    ...entry,
    start: utcDateTimeToZonedLocal(entry.start, timeZone),
    end: utcDateTimeToZonedLocal(entry.end, timeZone),
  }))
}

export function serviceHoursFormToUtcPayload(
  payload: CreateServiceHoursPayload,
  timeZone: string,
): CreateServiceHoursPayload {
  return {
    ...payload,
    weekly_schedules: zonedWeeklySchedulesToUtc(payload.weekly_schedules, timeZone),
    holidays: zonedDateTimeEntriesToUtc(payload.holidays, timeZone),
    makeup_days: zonedDateTimeEntriesToUtc(payload.makeup_days, timeZone),
  }
}

export function serviceHoursUtcToFormPayload(
  payload: CreateServiceHoursPayload,
  timeZone: string,
): CreateServiceHoursPayload {
  return {
    ...payload,
    weekly_schedules: utcWeeklySchedulesToZoned(payload.weekly_schedules, timeZone),
    holidays: utcDateTimeEntriesToZoned(payload.holidays, timeZone),
    makeup_days: utcDateTimeEntriesToZoned(payload.makeup_days, timeZone),
  }
}
