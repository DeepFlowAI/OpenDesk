'use client'

import { useState, useCallback, useEffect } from 'react'
import { DateTimeInput, TimeInput } from '@/components/ui/time-input'
import { IconTrash, IconCalendar } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSystemSettings } from '@/service/use-system-settings'
import {
  DEFAULT_SYSTEM_TIMEZONE,
  serviceHoursFormToUtcPayload,
  serviceHoursUtcToFormPayload,
} from '@/utils/service-hours-timezone'
import type {
  ServiceHours,
  CreateServiceHoursPayload,
  WeeklySchedule,
  TimeSlot,
  HolidayEntry,
  MakeupDayEntry,
} from '@/models/service-hours'

const DAY_KEYS: { day: number; key: string }[] = [
  { day: 1, key: 'sh.weekly.mon' },
  { day: 2, key: 'sh.weekly.tue' },
  { day: 3, key: 'sh.weekly.wed' },
  { day: 4, key: 'sh.weekly.thu' },
  { day: 5, key: 'sh.weekly.fri' },
  { day: 6, key: 'sh.weekly.sat' },
  { day: 7, key: 'sh.weekly.sun' },
]

function getSlotsForDay(schedules: WeeklySchedule[], day: number): TimeSlot[] {
  return schedules.find((s) => s.day_of_week === day)?.slots ?? []
}

function setSlots(schedules: WeeklySchedule[], day: number, slots: TimeSlot[]): WeeklySchedule[] {
  const existing = schedules.filter((s) => s.day_of_week !== day)
  if (slots.length === 0) return existing
  return [...existing, { day_of_week: day, slots }].sort((a, b) => a.day_of_week - b.day_of_week)
}

type Props = {
  initialData?: ServiceHours
  onSubmit: (data: CreateServiceHoursPayload) => void
}

export default function ServiceHoursForm({ initialData, onSubmit }: Props) {
  const { locale } = useLocaleStore()
  const { data: systemSettings } = useSystemSettings()
  const serviceHoursTimezone = systemSettings?.default_timezone ?? DEFAULT_SYSTEM_TIMEZONE

  const [name, setName] = useState(initialData?.name ?? '')
  const [description, setDescription] = useState(initialData?.description ?? '')
  const [weeklySchedules, setWeeklySchedules] = useState<WeeklySchedule[]>(
    initialData?.weekly_schedules ?? []
  )
  const [holidays, setHolidays] = useState<HolidayEntry[]>(initialData?.holidays ?? [])
  const [makeupDays, setMakeupDays] = useState<MakeupDayEntry[]>(initialData?.makeup_days ?? [])
  const [nameError, setNameError] = useState('')
  const [initializedKey, setInitializedKey] = useState('')

  useEffect(() => {
    if (!initialData) return

    const nextKey = `${initialData.id}:${serviceHoursTimezone}`
    if (initializedKey === nextKey) return

    const localPayload = serviceHoursUtcToFormPayload({
      name: initialData.name,
      description: initialData.description,
      weekly_schedules: initialData.weekly_schedules,
      holidays: initialData.holidays,
      makeup_days: initialData.makeup_days,
    }, serviceHoursTimezone)

    setName(localPayload.name)
    setDescription(localPayload.description ?? '')
    setWeeklySchedules(localPayload.weekly_schedules)
    setHolidays(localPayload.holidays)
    setMakeupDays(localPayload.makeup_days)
    setInitializedKey(nextKey)
  }, [initialData, initializedKey, serviceHoursTimezone])

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      const trimmed = name.trim()
      if (!trimmed) {
        setNameError(t('sh.form.name.required', locale))
        return
      }
      setNameError('')
      onSubmit(serviceHoursFormToUtcPayload({
        name: trimmed,
        description: description || null,
        weekly_schedules: weeklySchedules,
        holidays,
        makeup_days: makeupDays,
      }, serviceHoursTimezone))
    },
    [name, description, weeklySchedules, holidays, makeupDays, serviceHoursTimezone, locale, onSubmit]
  )

  /* --- Weekly schedule helpers --- */
  const addSlot = (day: number) => {
    const slots = getSlotsForDay(weeklySchedules, day)
    setWeeklySchedules(setSlots(weeklySchedules, day, [...slots, { start: '09:00', end: '18:00' }]))
  }
  const updateSlot = (day: number, idx: number, field: 'start' | 'end', val: string) => {
    const slots = [...getSlotsForDay(weeklySchedules, day)]
    slots[idx] = { ...slots[idx], [field]: val }
    setWeeklySchedules(setSlots(weeklySchedules, day, slots))
  }
  const removeSlot = (day: number, idx: number) => {
    const slots = getSlotsForDay(weeklySchedules, day).filter((_, i) => i !== idx)
    setWeeklySchedules(setSlots(weeklySchedules, day, slots))
  }

  /* --- Holiday helpers --- */
  const addHoliday = () => {
    setHolidays([...holidays, { name: '', start: '', end: '' }])
  }
  const updateHoliday = (idx: number, field: keyof HolidayEntry, val: string) => {
    const next = [...holidays]
    next[idx] = { ...next[idx], [field]: val }
    setHolidays(next)
  }
  const removeHoliday = (idx: number) => {
    setHolidays(holidays.filter((_, i) => i !== idx))
  }

  /* --- Makeup day helpers --- */
  const addMakeup = () => {
    setMakeupDays([...makeupDays, { name: '', start: '', end: '' }])
  }
  const updateMakeup = (idx: number, field: keyof MakeupDayEntry, val: string) => {
    const next = [...makeupDays]
    next[idx] = { ...next[idx], [field]: val }
    setMakeupDays(next)
  }
  const removeMakeup = (idx: number) => {
    setMakeupDays(makeupDays.filter((_, i) => i !== idx))
  }

  return (
    <form id="sh-form" onSubmit={handleSubmit} className="flex flex-col gap-5 rounded-lg bg-white p-8">
      {/* Name */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-1">
          <label className="text-sm font-medium text-foreground/80">{t('sh.form.name', locale)}</label>
          <span className="text-sm font-medium text-destructive">*</span>
        </div>
        <input
          type="text"
          value={name}
          onChange={(e) => { setName(e.target.value); setNameError('') }}
          placeholder={t('sh.form.name.placeholder', locale)}
          maxLength={64}
          className={`h-10 rounded-lg border px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring ${
            nameError ? 'border-destructive' : 'border-border'
          }`}
        />
        {nameError && <span className="text-xs text-destructive">{nameError}</span>}
      </div>

      {/* Description */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">{t('sh.form.desc', locale)}</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t('sh.form.desc.placeholder', locale)}
          maxLength={256}
          rows={3}
          className="rounded-lg border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      {/* Weekly schedules */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">{t('sh.weekly.title', locale)}</label>
        <p className="text-[13px] text-muted-foreground">{t('sh.weekly.hint', locale)}</p>
        <div className="mt-1 flex flex-col gap-3">
          {DAY_KEYS.map(({ day, key }) => {
            const slots = getSlotsForDay(weeklySchedules, day)
            return (
              <div key={day} className="flex flex-wrap items-center gap-3">
                <span className="w-10 text-sm text-foreground/80">{t(key, locale)}</span>
                {slots.map((slot, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <div className="flex h-9 items-center gap-2 rounded-lg border border-border px-2.5">
                      <TimeInput
                        value={slot.start}
                        onChange={(e) => updateSlot(day, idx, 'start', e.target.value)}
                        className="border-none bg-transparent text-sm text-foreground outline-none"
                      />
                      <span className="text-sm text-muted-foreground">–</span>
                      <TimeInput
                        value={slot.end}
                        onChange={(e) => updateSlot(day, idx, 'end', e.target.value)}
                        className="border-none bg-transparent text-sm text-foreground outline-none"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => removeSlot(day, idx)}
                      className="text-muted-foreground transition-colors hover:text-destructive"
                    >
                      <IconTrash size={16} />
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => addSlot(day)}
                  className="text-[13px] text-primary transition-colors hover:text-primary/80"
                >
                  {t('sh.weekly.addSlot', locale)}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {/* Holidays */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">{t('sh.holidays.title', locale)}</label>
        <p className="text-[13px] text-muted-foreground">{t('sh.holidays.hint', locale)}</p>
        <div className="mt-1 flex flex-col gap-2">
          {holidays.map((h, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={h.name}
                onChange={(e) => updateHoliday(idx, 'name', e.target.value)}
                placeholder={t('sh.holidays.name', locale)}
                maxLength={32}
                className="h-9 w-[120px] rounded-md border border-border px-2.5 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <div className="flex h-9 items-center gap-2 rounded-md border border-border px-3">
                <DateTimeInput
                  value={h.start}
                  onChange={(e) => updateHoliday(idx, 'start', e.target.value)}
                  className="border-none bg-transparent text-[13px] text-foreground outline-none"
                />
                <span className="text-[13px] text-muted-foreground">→</span>
                <DateTimeInput
                  value={h.end}
                  onChange={(e) => updateHoliday(idx, 'end', e.target.value)}
                  className="border-none bg-transparent text-[13px] text-foreground outline-none"
                />
                <IconCalendar size={16} className="text-muted-foreground" />
              </div>
              <button
                type="button"
                onClick={() => removeHoliday(idx)}
                className="text-muted-foreground transition-colors hover:text-destructive"
              >
                <IconTrash size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addHoliday}
            className="self-start text-[13px] text-primary transition-colors hover:text-primary/80"
          >
            {t('sh.holidays.add', locale)}
          </button>
        </div>
      </div>

      {/* Makeup days */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">{t('sh.makeup.title', locale)}</label>
        <p className="text-[13px] text-muted-foreground">{t('sh.makeup.hint', locale)}</p>
        <div className="mt-1 flex flex-col gap-2">
          {makeupDays.map((m, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={m.name}
                onChange={(e) => updateMakeup(idx, 'name', e.target.value)}
                placeholder={t('sh.holidays.name', locale)}
                maxLength={32}
                className="h-9 w-[120px] rounded-md border border-border px-2.5 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <div className="flex h-9 items-center gap-2 rounded-md border border-border px-3">
                <DateTimeInput
                  value={m.start}
                  onChange={(e) => updateMakeup(idx, 'start', e.target.value)}
                  className="border-none bg-transparent text-[13px] text-foreground outline-none"
                />
                <span className="text-[13px] text-muted-foreground">→</span>
                <DateTimeInput
                  value={m.end}
                  onChange={(e) => updateMakeup(idx, 'end', e.target.value)}
                  className="border-none bg-transparent text-[13px] text-foreground outline-none"
                />
                <IconCalendar size={16} className="text-muted-foreground" />
              </div>
              <button
                type="button"
                onClick={() => removeMakeup(idx)}
                className="text-muted-foreground transition-colors hover:text-destructive"
              >
                <IconTrash size={16} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addMakeup}
            className="self-start text-[13px] text-primary transition-colors hover:text-primary/80"
          >
            {t('sh.makeup.add', locale)}
          </button>
        </div>
      </div>
    </form>
  )
}
