export type TimeSlot = {
  start: string
  end: string
}

export type WeeklySchedule = {
  day_of_week: number
  slots: TimeSlot[]
}

export type HolidayEntry = {
  name: string
  start: string
  end: string
}

export type MakeupDayEntry = {
  name: string
  start: string
  end: string
}

export type ServiceHours = {
  id: number
  name: string
  description: string | null
  weekly_schedules: WeeklySchedule[]
  holidays: HolidayEntry[]
  makeup_days: MakeupDayEntry[]
  created_at: string
  updated_at: string
}

export type CreateServiceHoursPayload = {
  name: string
  description?: string | null
  weekly_schedules: WeeklySchedule[]
  holidays: HolidayEntry[]
  makeup_days: MakeupDayEntry[]
}

export type UpdateServiceHoursPayload = CreateServiceHoursPayload
