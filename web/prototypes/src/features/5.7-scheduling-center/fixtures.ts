export type Shift = {
  id: string
  name: string
  start: string
  end: string
  color: string
  sort: number
  enabled: boolean
}

export type Agent = {
  id: string
  name: string
  jobNumber?: string
}

export type DayCol = {
  key: string
  weekday: string
  dateLabel: string
  isToday?: boolean
}

/** Fixed week: Mon 2026-08-03 … Sun 2026-08-09; "today" = Wed 08-05. */
export const WEEK_DAYS: DayCol[] = [
  { key: "d1", weekday: "周一", dateLabel: "8/3" },
  { key: "d2", weekday: "周二", dateLabel: "8/4" },
  { key: "d3", weekday: "周三", dateLabel: "8/5", isToday: true },
  { key: "d4", weekday: "周四", dateLabel: "8/6" },
  { key: "d5", weekday: "周五", dateLabel: "8/7" },
  { key: "d6", weekday: "周六", dateLabel: "8/8" },
  { key: "d7", weekday: "周日", dateLabel: "8/9" },
]

export const WEEK_RANGE_LABEL = "2026-08-03 ~ 2026-08-09"

export const SHIFTS: Shift[] = [
  {
    id: "morning",
    name: "早班",
    start: "09:00",
    end: "13:00",
    // Brighter sky blue + white label
    color: "oklch(0.64 0.16 230)",
    sort: 1,
    enabled: true,
  },
  {
    id: "midday",
    name: "中班",
    start: "13:00",
    end: "18:00",
    // Brighter mint teal + white label
    color: "oklch(0.62 0.13 168)",
    sort: 2,
    enabled: true,
  },
  {
    id: "evening",
    name: "晚班",
    start: "18:00",
    end: "22:00",
    // Brighter cool indigo + white label (no brown)
    color: "oklch(0.60 0.14 280)",
    sort: 3,
    enabled: true,
  },
]

export const POOL_GROUPS = [
  { id: "g1", name: "在线客服一组", memberCount: 8 },
  { id: "g2", name: "呼叫坐席组", memberCount: 6 },
]

export const SELECTED_POOL_LABEL = "在线客服一组"
export const POOL_MEMBER_COUNT = 8

export const AGENTS: Agent[] = [
  { id: "a1", name: "张敏", jobNumber: "A001" },
  { id: "a2", name: "李强", jobNumber: "A002" },
  { id: "a3", name: "王芳", jobNumber: "A003" },
  { id: "a4", name: "赵磊", jobNumber: "A004" },
  { id: "a5", name: "陈雪", jobNumber: "A005" },
  { id: "a6", name: "周凯", jobNumber: "A006" },
  { id: "a7", name: "孙悦", jobNumber: "A007" },
  { id: "a8", name: "吴婷", jobNumber: "A008" },
]

/** cell key = `${shiftId}:${dayKey}` → agent ids */
export const BOARD_ASSIGNMENTS: Record<string, string[]> = {
  "morning:d1": ["a1", "a2"],
  "morning:d2": ["a1", "a3"],
  "morning:d3": ["a1", "a2", "a4"],
  "morning:d4": ["a2", "a3"],
  "morning:d5": ["a1", "a5"],
  "morning:d6": [],
  "morning:d7": [],
  "midday:d1": ["a3", "a5"],
  "midday:d2": ["a4", "a5"],
  "midday:d3": ["a3", "a6"],
  "midday:d4": ["a5", "a6"],
  "midday:d5": ["a3", "a4"],
  "midday:d6": ["a6"],
  "midday:d7": [],
  "evening:d1": ["a6", "a7"],
  "evening:d2": ["a7", "a8"],
  // a1 also on evening Wed (multi-shift same day; no OT UI in phase 1)
  "evening:d3": ["a1", "a7"],
  "evening:d4": ["a7", "a8"],
  "evening:d5": ["a8"],
  "evening:d6": ["a7"],
  "evening:d7": [],
}

export const PICKER_AGENTS: { agent: Agent; disabled?: boolean; reason?: string }[] = [
  { agent: AGENTS[0], disabled: true, reason: "已在本格" },
  { agent: AGENTS[1], disabled: true, reason: "已在本格" },
  { agent: AGENTS[2] },
  { agent: AGENTS[3], disabled: true, reason: "已在本格" },
  { agent: AGENTS[4] },
  { agent: AGENTS[5] },
  { agent: AGENTS[6] },
  { agent: AGENTS[7] },
]

export function agentById(id: string): Agent | undefined {
  return AGENTS.find((a) => a.id === id)
}

export type DaySummary = {
  headcount: number
  slots: number
  byShift: { name: string; color: string; count: number }[]
  emptyShifts: number
}

/** Per-day auto summary for the bottom stats row on week grids. */
export function daySummary(dayKey: string): DaySummary {
  const people = new Set<string>()
  let slots = 0
  const byShift = SHIFTS.filter((s) => s.enabled).map((shift) => {
    const ids = BOARD_ASSIGNMENTS[`${shift.id}:${dayKey}`] ?? []
    for (const id of ids) {
      people.add(id)
      slots += 1
    }
    return { name: shift.name.replace("班", ""), color: shift.color, count: ids.length }
  })
  const emptyShifts = byShift.filter((s) => s.count === 0).length
  return { headcount: people.size, slots, byShift, emptyShifts }
}

/** Shifts assigned to an agent on a given week day key. */
export function shiftsForAgentDay(agentId: string, dayKey: string): Shift[] {
  return SHIFTS.filter((shift) =>
    (BOARD_ASSIGNMENTS[`${shift.id}:${dayKey}`] ?? []).includes(agentId),
  )
}

/** Per-agent shift totals across the current board week (enabled shifts only). */
export function agentPeriodShiftCounts(agentId: string): { shift: Shift; count: number }[] {
  return SHIFTS.filter((s) => s.enabled)
    .map((shift) => {
      let count = 0
      for (const day of WEEK_DAYS) {
        if ((BOARD_ASSIGNMENTS[`${shift.id}:${day.key}`] ?? []).includes(agentId)) count += 1
      }
      return { shift, count }
    })
    .filter((x) => x.count > 0)
}

export type DayShiftCount = { shift: Shift; count: number }

export function shiftCountsForDay(dayKey: string): DayShiftCount[] {
  return SHIFTS.filter((s) => s.enabled).map((shift) => ({
    shift,
    count: (BOARD_ASSIGNMENTS[`${shift.id}:${dayKey}`] ?? []).length,
  }))
}

export const MONTH_LABEL = "2026 年 8 月"

/**
 * August 2026 month grid (Mon-start). Days outside Aug are marked outside.
 * weekDayKey maps to BOARD_ASSIGNMENTS keys for Aug 3–9 only.
 */
export type CalendarCell = {
  key: string
  dayNum: number
  outside?: boolean
  isToday?: boolean
  weekDayKey?: string
}

export const CALENDAR_CELLS: CalendarCell[] = [
  // week of Jul 27
  { key: "c0727", dayNum: 27, outside: true },
  { key: "c0728", dayNum: 28, outside: true },
  { key: "c0729", dayNum: 29, outside: true },
  { key: "c0730", dayNum: 30, outside: true },
  { key: "c0731", dayNum: 31, outside: true },
  { key: "c0801", dayNum: 1 },
  { key: "c0802", dayNum: 2 },
  // week of Aug 3 (demo data)
  { key: "c0803", dayNum: 3, weekDayKey: "d1" },
  { key: "c0804", dayNum: 4, weekDayKey: "d2" },
  { key: "c0805", dayNum: 5, weekDayKey: "d3", isToday: true },
  { key: "c0806", dayNum: 6, weekDayKey: "d4" },
  { key: "c0807", dayNum: 7, weekDayKey: "d5" },
  { key: "c0808", dayNum: 8, weekDayKey: "d6" },
  { key: "c0809", dayNum: 9, weekDayKey: "d7" },
  // rest of August (empty)
  ...[10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31].map(
    (n) => ({ key: `c08${n}`, dayNum: n }),
  ),
  // Sep 1–6
  { key: "c0901", dayNum: 1, outside: true },
  { key: "c0902", dayNum: 2, outside: true },
  { key: "c0903", dayNum: 3, outside: true },
  { key: "c0904", dayNum: 4, outside: true },
  { key: "c0905", dayNum: 5, outside: true },
  { key: "c0906", dayNum: 6, outside: true },
]

export type LayoutView = "shift-day" | "agent-day" | "calendar"

export const LAYOUT_OPTIONS: { id: LayoutView; label: string }[] = [
  { id: "shift-day", label: "班次+日期" },
  { id: "agent-day", label: "员工+日期" },
  { id: "calendar", label: "日历" },
]
