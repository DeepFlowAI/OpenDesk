export type ShiftChip = {
  id: string
  name: string
  start: string
  end: string
  color: string
}

export type DayRow = {
  key: string
  weekday: string
  dateLabel: string
  fullDate: string
  isToday?: boolean
  shifts: ShiftChip[]
}

export const AGENT_NAME = "张敏"

/** Fixed week: Mon 2026-08-03 … Sun 2026-08-09; today = Wed 08-05. */
export const WEEK_RANGE_LABEL = "2026-08-03 ~ 2026-08-09"

const MORNING: ShiftChip = {
  id: "morning",
  name: "早班",
  start: "09:00",
  end: "13:00",
  color: "oklch(0.64 0.16 230)",
}

const MIDDAY: ShiftChip = {
  id: "midday",
  name: "中班",
  start: "13:00",
  end: "18:00",
  color: "oklch(0.62 0.13 168)",
}

const EVENING: ShiftChip = {
  id: "evening",
  name: "晚班",
  start: "18:00",
  end: "22:00",
  color: "oklch(0.60 0.14 280)",
}

/** Published week with personal shifts (self only). */
export const MY_WEEK_DAYS: DayRow[] = [
  {
    key: "d1",
    weekday: "周一",
    dateLabel: "8/3",
    fullDate: "2026-08-03",
    shifts: [MORNING],
  },
  {
    key: "d2",
    weekday: "周二",
    dateLabel: "8/4",
    fullDate: "2026-08-04",
    shifts: [MORNING],
  },
  {
    key: "d3",
    weekday: "周三",
    dateLabel: "8/5",
    fullDate: "2026-08-05",
    isToday: true,
    shifts: [MORNING, EVENING],
  },
  {
    key: "d4",
    weekday: "周四",
    dateLabel: "8/6",
    fullDate: "2026-08-06",
    shifts: [MIDDAY],
  },
  {
    key: "d5",
    weekday: "周五",
    dateLabel: "8/7",
    fullDate: "2026-08-07",
    shifts: [MIDDAY],
  },
  {
    key: "d6",
    weekday: "周六",
    dateLabel: "8/8",
    fullDate: "2026-08-08",
    shifts: [],
  },
  {
    key: "d7",
    weekday: "周日",
    dateLabel: "8/9",
    fullDate: "2026-08-09",
    shifts: [],
  },
]

/** Published week but current agent has no assignments. */
export const MY_WEEK_EMPTY_DAYS: DayRow[] = MY_WEEK_DAYS.map((day) => ({
  ...day,
  shifts: [],
}))
