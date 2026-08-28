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

export type PublishState = "unpublished" | "published" | "dirty"

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
    color: "oklch(0.64 0.16 230)",
    sort: 1,
    enabled: true,
  },
  {
    id: "midday",
    name: "中班",
    start: "13:00",
    end: "18:00",
    color: "oklch(0.62 0.13 168)",
    sort: 2,
    enabled: true,
  },
  {
    id: "evening",
    name: "晚班",
    start: "18:00",
    end: "22:00",
    color: "oklch(0.60 0.14 280)",
    sort: 3,
    enabled: true,
  },
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

/** Demo board after rule generate + one manual dirty edit. */
export const BOARD_ASSIGNMENTS: Record<string, string[]> = {
  "morning:d1": ["a1", "a2", "a3", "a4"],
  "morning:d2": ["a1", "a2", "a3", "a4"],
  "morning:d3": ["a1", "a2", "a3"],
  "morning:d4": ["a2", "a3", "a4", "a5"],
  "morning:d5": ["a1", "a2", "a5"],
  "morning:d6": ["a1", "a2"],
  "morning:d7": ["a1", "a2"],
  "midday:d1": ["a5", "a6", "a7", "a8", "a3"],
  "midday:d2": ["a5", "a6", "a7", "a8"],
  "midday:d3": ["a5", "a6", "a7"],
  "midday:d4": ["a5", "a6", "a7", "a8"],
  "midday:d5": ["a3", "a4", "a6", "a7", "a8"],
  "midday:d6": ["a3", "a6", "a7"],
  "midday:d7": ["a3", "a6"],
  "evening:d1": ["a6", "a7", "a8"],
  "evening:d2": ["a6", "a7", "a8"],
  // dirty: a1 also on evening Wed (soft multi-shift + hard rest risk vs morning)
  "evening:d3": ["a1", "a7", "a8"],
  "evening:d4": ["a7", "a8", "a1"],
  "evening:d5": ["a7", "a8"],
  "evening:d6": ["a7", "a8", "a5", "a4"],
  "evening:d7": ["a7", "a8", "a5", "a4"],
}

/** Coverage targets: weekday Mon–Fri higher; weekend lower. */
export const COVERAGE_TARGETS: Record<string, number[]> = {
  morning: [4, 4, 4, 4, 4, 2, 2],
  midday: [5, 5, 5, 5, 5, 3, 3],
  evening: [3, 3, 3, 3, 3, 4, 4],
}

export const RULE_SETS = [
  {
    id: "rs1",
    name: "在线客服标准周",
    isDefault: true,
    groups: "在线客服一组",
    coverageSummary: "平日早4人/中5人/晚3人 · 周末下调",
    constraintSummary: "连上≤6 · 休息≥8h · 周上班≤6天",
    updatedAt: "2026-08-06 14:20",
  },
  {
    id: "rs2",
    name: "呼叫中心轮转",
    isDefault: false,
    groups: "呼叫坐席组",
    coverageSummary: "三班均6人",
    constraintSummary: "连上≤5 · 休息≥10h",
    updatedAt: "2026-08-01 09:10",
  },
]

export const DEFAULT_RULE_SET_LABEL = "在线客服标准周"

export const ROTATION_TEMPLATE = {
  name: "上三休二（示例）",
  days: ["早班", "早班", "晚班", "休", "休"] as const,
  isDefault: true,
}

export type ConstraintRow = {
  name: string
  level: "硬" | "软"
  on: boolean
  /** null = no numeric param (coverage gap/overflow are toggle-only) */
  param: { prefix: string; value: number; suffix: string; min: number; max: number } | null
}

export const CONSTRAINTS: ConstraintRow[] = [
  {
    name: "连续上班上限",
    level: "硬",
    on: true,
    param: { prefix: "最多", value: 6, suffix: "天", min: 1, max: 31 },
  },
  {
    name: "班间最短休息",
    level: "硬",
    on: true,
    param: { prefix: "≥", value: 8, suffix: "小时", min: 0, max: 48 },
  },
  {
    name: "每周最多上班天数",
    level: "硬",
    on: true,
    param: { prefix: "≤", value: 6, suffix: "天", min: 1, max: 7 },
  },
  {
    name: "每天最多班次数",
    level: "软",
    on: true,
    param: { prefix: "≤", value: 2, suffix: "班", min: 1, max: 6 },
  },
  { name: "目标缺口", level: "软", on: true, param: null },
  { name: "目标溢出", level: "软", on: true, param: null },
  {
    name: "公平性偏差",
    level: "软",
    on: true,
    param: { prefix: "与均值差 ≤", value: 2, suffix: "天", min: 0, max: 14 },
  },
]

export type Violation = {
  id: string
  level: "hard" | "soft"
  agentName: string
  dayLabel: string
  shiftName?: string
  reason: string
  cellKey?: string
}

export const VIOLATIONS: Violation[] = [
  {
    id: "v1",
    level: "hard",
    agentName: "张敏",
    dayLabel: "周三",
    shiftName: "晚班",
    reason: "与早班结束间隔不足 8 小时",
    cellKey: "evening:d3",
  },
  {
    id: "v2",
    level: "soft",
    agentName: "张敏",
    dayLabel: "周三",
    reason: "当天班次数 2，已达软上限（演示角标）",
    cellKey: "evening:d3",
  },
  {
    id: "v3",
    level: "soft",
    agentName: "—",
    dayLabel: "周三 · 早班",
    reason: "目标缺口：目标 4 人，实际 3 人",
    cellKey: "morning:d3",
  },
  {
    id: "v4",
    level: "soft",
    agentName: "—",
    dayLabel: "周一 · 中班",
    reason: "目标溢出：目标 5 人，实际 5 人（演示）",
    cellKey: "midday:d1",
  },
]

export function agentById(id: string): Agent | undefined {
  return AGENTS.find((a) => a.id === id)
}

export type DaySummary = {
  headcount: number
  slots: number
  byShift: { id: string; name: string; color: string; count: number; target: number }[]
  gap: number
  overflow: number
  emptyShifts: number
}

export function daySummary(dayKey: string): DaySummary {
  const dayIndex = WEEK_DAYS.findIndex((d) => d.key === dayKey)
  const people = new Set<string>()
  let slots = 0
  let gap = 0
  let overflow = 0
  const byShift = SHIFTS.filter((s) => s.enabled).map((shift) => {
    const ids = BOARD_ASSIGNMENTS[`${shift.id}:${dayKey}`] ?? []
    const target = COVERAGE_TARGETS[shift.id]?.[dayIndex] ?? 0
    for (const id of ids) {
      people.add(id)
      slots += 1
    }
    if (ids.length < target) gap += target - ids.length
    if (ids.length > target) overflow += ids.length - target
    return {
      id: shift.id,
      name: shift.name.replace("班", ""),
      color: shift.color,
      count: ids.length,
      target,
    }
  })
  const emptyShifts = byShift.filter((s) => s.count === 0).length
  return { headcount: people.size, slots, byShift, gap, overflow, emptyShifts }
}

export function publishStateLabel(state: PublishState): string {
  if (state === "unpublished") return "未发布"
  if (state === "published") return "已发布"
  return "有未发布变更"
}
