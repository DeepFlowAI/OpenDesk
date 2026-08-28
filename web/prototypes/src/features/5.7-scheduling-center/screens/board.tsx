import {
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconCopy,
  IconDownload,
  IconPhoto,
  IconPlus,
  IconUsersGroup,
  IconX,
} from "@tabler/icons-react"
import { SchedulingShell } from "../components/scheduling-shell"
import {
  AGENTS,
  BOARD_ASSIGNMENTS,
  CALENDAR_CELLS,
  LAYOUT_OPTIONS,
  MONTH_LABEL,
  POOL_MEMBER_COUNT,
  SELECTED_POOL_LABEL,
  SHIFTS,
  WEEK_DAYS,
  WEEK_RANGE_LABEL,
  agentById,
  agentPeriodShiftCounts,
  daySummary,
  shiftCountsForDay,
  shiftsForAgentDay,
  type LayoutView,
} from "../fixtures"

type BoardMode = "filled" | "empty-pool"

function ViewSwitcher({ active }: { active: LayoutView }) {
  return (
    <div className="inline-flex h-9 items-center rounded-md border border-border bg-muted/40 p-0.5">
      {LAYOUT_OPTIONS.map((opt) => (
        <div
          key={opt.id}
          className={`rounded px-3 py-1.5 text-xs font-medium ${
            active === opt.id
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground"
          }`}
        >
          {opt.label}
        </div>
      ))}
    </div>
  )
}

function Toolbar({
  emptyPool,
  layout,
}: {
  emptyPool?: boolean
  layout: LayoutView
}) {
  const isCalendar = layout === "calendar"
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-white px-6 py-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">排班池</span>
        {emptyPool ? (
          <div className="flex h-9 min-w-[180px] items-center justify-between rounded-md border border-dashed border-border bg-muted/20 px-3 text-sm text-muted-foreground">
            <span>选择员工组…</span>
            <IconChevronDown size={14} />
          </div>
        ) : (
          <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-background px-2.5 text-sm">
            <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              <IconUsersGroup size={12} />
              {SELECTED_POOL_LABEL}
              <IconX size={12} className="opacity-60" />
            </span>
            <IconChevronDown size={14} className="text-muted-foreground" />
          </div>
        )}
        {!emptyPool ? (
          <span className="text-xs text-muted-foreground">池内 {POOL_MEMBER_COUNT} 人</span>
        ) : null}
      </div>

      <span className="h-5 w-px bg-border" />

      <ViewSwitcher active={layout} />

      <span className="h-5 w-px bg-border" />

      <div className="flex items-center gap-1">
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-md border border-border text-muted-foreground"
        >
          <IconChevronLeft size={16} />
        </button>
        <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm font-medium">
          {isCalendar ? MONTH_LABEL : WEEK_RANGE_LABEL}
        </div>
        <button
          type="button"
          className="grid h-9 w-9 place-items-center rounded-md border border-border text-muted-foreground"
        >
          <IconChevronRight size={16} />
        </button>
        <button type="button" className="ml-1 h-9 rounded-md border border-border px-3 text-sm">
          {isCalendar ? "本月" : "本周"}
        </button>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          title={isCalendar ? "请切换到周视图后复制" : undefined}
          className={`inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm ${
            emptyPool || isCalendar ? "pointer-events-none opacity-40" : ""
          }`}
        >
          <IconCopy size={14} />
          复制上周
        </button>
        <button
          type="button"
          className={`inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm ${
            emptyPool ? "pointer-events-none opacity-40" : ""
          }`}
        >
          <IconDownload size={14} />
          导出 Excel
        </button>
        <button
          type="button"
          className={`inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm ${
            emptyPool ? "pointer-events-none opacity-40" : ""
          }`}
        >
          <IconPhoto size={14} />
          导出图片
        </button>
      </div>
    </div>
  )
}

function AgentChip({ name }: { name: string }) {
  return (
    <span className="inline-flex max-w-full items-center rounded-md border border-border bg-white px-1.5 py-0.5 text-[11px] leading-4">
      <span className="truncate">{name}</span>
    </span>
  )
}

/** Solid shift color fill + white label for high contrast. */
function ShiftChip({ name, color }: { name: string; color: string }) {
  return (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium leading-4 text-white"
      style={{ background: color }}
    >
      {name}
    </span>
  )
}

/**
 * Agent×day cell: solid-color shift card with fixed width, taller than wide.
 * Does not stretch to fill the cell — multiple shifts stay the same size.
 */
function ShiftStrip({ name, color }: { name: string; color: string }) {
  return (
    <div
      className="flex h-14 w-10 shrink-0 items-center justify-center rounded-md px-1 text-[11px] font-medium leading-4 text-white"
      style={{ background: color }}
      title={name}
    >
      <span className="truncate">{name}</span>
    </div>
  )
}

function DayHeaderRow({ corner }: { corner: string }) {
  return (
    <div
      className="grid border-b border-border bg-muted/40"
      style={{ gridTemplateColumns: "140px repeat(7, minmax(0, 1fr))" }}
    >
      <div className="sticky left-0 z-10 border-r border-border bg-muted/40 px-3 py-2.5 text-xs font-medium text-muted-foreground">
        {corner}
      </div>
      {WEEK_DAYS.map((day) => (
        <div
          key={day.key}
          className={`border-r border-border px-2 py-2.5 text-center last:border-r-0 ${
            day.isToday ? "bg-primary/5" : ""
          }`}
        >
          <div className="text-xs font-semibold">{day.weekday}</div>
          <div
            className={`text-[11px] ${day.isToday ? "font-medium text-primary" : "text-muted-foreground"}`}
          >
            {day.dateLabel}
            {day.isToday ? " · 今天" : ""}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Bottom row: auto per-day summary aligned with date columns. */
function DailySummaryRow() {
  return (
    <div
      className="sticky bottom-0 z-20 grid border-t border-border bg-muted/50"
      style={{ gridTemplateColumns: "140px repeat(7, minmax(0, 1fr))" }}
    >
      <div className="sticky left-0 z-10 flex items-center border-r border-border bg-muted/70 px-3 py-2.5 text-xs font-semibold text-muted-foreground">
        当日统计
      </div>
      {WEEK_DAYS.map((day) => {
        const s = daySummary(day.key)
        return (
          <div
            key={day.key}
            className={`border-r border-border px-2 py-2 last:border-r-0 ${
              day.isToday ? "bg-primary/5" : ""
            }`}
          >
            <div className="text-[11px] font-semibold tabular-nums">
              {s.headcount}人 / {s.slots}人次
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {s.byShift.map((x) => (
                <span
                  key={x.name}
                  className="rounded border px-1 py-px text-[10px] font-medium"
                  style={{ borderColor: x.color, color: x.color }}
                >
                  {x.name}
                  {x.count}
                </span>
              ))}
            </div>
            <div className="mt-1 flex flex-wrap gap-1">
              {s.emptyShifts > 0 ? (
                <span className="rounded bg-red-50 px-1 py-px text-[10px] text-red-700">
                  空{s.emptyShifts}
                </span>
              ) : (
                <span className="rounded bg-emerald-50 px-1 py-px text-[10px] text-emerald-700">
                  满
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ShiftDayGrid({ highlightEmpty }: { highlightEmpty?: boolean }) {
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="min-w-[980px]">
        <DayHeaderRow corner="班次 \\ 日期" />
        {SHIFTS.filter((s) => s.enabled).map((shift) => (
          <div
            key={shift.id}
            className="grid border-b border-border"
            style={{ gridTemplateColumns: "140px repeat(7, minmax(0, 1fr))" }}
          >
            <div className="sticky left-0 z-10 border-r border-border bg-white p-2">
              <div
                className="rounded-md px-2.5 py-2 text-white"
                style={{ background: shift.color }}
              >
                <div className="text-sm font-semibold">{shift.name}</div>
                <div className="text-[11px] text-white/85">
                  {shift.start}–{shift.end}
                </div>
              </div>
            </div>
            {WEEK_DAYS.map((day) => {
              const ids = BOARD_ASSIGNMENTS[`${shift.id}:${day.key}`] ?? []
              const empty = ids.length === 0
              return (
                <div
                  key={day.key}
                  className={`min-h-[88px] border-r border-border p-1.5 last:border-r-0 ${
                    day.isToday ? "bg-primary/[0.03]" : "bg-white"
                  } ${highlightEmpty && empty ? "bg-red-50/80" : ""}`}
                >
                  {empty ? (
                    <div className="flex h-full min-h-[76px] items-center justify-center rounded-md border border-dashed border-border/80 text-[11px] text-muted-foreground">
                      <span className="inline-flex items-center gap-0.5">
                        <IconPlus size={12} />
                        添加
                      </span>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {ids.map((id) => {
                        const agent = agentById(id)
                        if (!agent) return null
                        return <AgentChip key={id} name={agent.name} />
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ))}
        <DailySummaryRow />
      </div>
    </div>
  )
}

function AgentDayGrid() {
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="min-w-[980px]">
        <DayHeaderRow corner="员工 \\ 日期" />
        {AGENTS.map((agent) => {
          const periodStats = agentPeriodShiftCounts(agent.id)
          return (
          <div
            key={agent.id}
            className="grid border-b border-border"
            style={{ gridTemplateColumns: "140px repeat(7, minmax(0, 1fr))" }}
          >
            <div className="sticky left-0 z-10 flex items-center gap-2 border-r border-border bg-white px-3 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{agent.name}</div>
                {agent.jobNumber ? (
                  <div className="font-mono text-[11px] text-muted-foreground">
                    {agent.jobNumber}
                  </div>
                ) : null}
                {periodStats.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {periodStats.map(({ shift, count }) => (
                      <span
                        key={shift.id}
                        className="rounded border px-1 py-px text-[10px] font-medium"
                        style={{ borderColor: shift.color, color: shift.color }}
                        title={`${shift.name} ${count}`}
                      >
                        {shift.name}
                        {count}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
            {WEEK_DAYS.map((day) => {
              const shifts = shiftsForAgentDay(agent.id, day.key)
                .slice()
                .sort((a, b) => {
                  if (a.start !== b.start) return a.start.localeCompare(b.start)
                  return a.sort - b.sort
                })
              const empty = shifts.length === 0
              return (
                <div
                  key={day.key}
                  className={`flex min-h-[72px] flex-col border-r border-border p-1.5 last:border-r-0 ${
                    day.isToday ? "bg-primary/[0.03]" : "bg-white"
                  }`}
                >
                  {empty ? (
                    <div className="flex min-h-[60px] items-center justify-center rounded-md border border-dashed border-border/80 text-[11px] text-muted-foreground">
                      排班
                    </div>
                  ) : (
                    <div className="flex flex-wrap content-start justify-start gap-1">
                      {shifts.map((s) => (
                        <ShiftStrip key={s.id} name={s.name} color={s.color} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          )
        })}
        <DailySummaryRow />
      </div>
    </div>
  )
}

/** Right-side day board when a calendar day is selected (static: Wed 8/5). */
function CalendarDayDetailBoard({ weekDayKey }: { weekDayKey: string }) {
  const day = WEEK_DAYS.find((d) => d.key === weekDayKey)
  const summary = daySummary(weekDayKey)
  if (!day) return null

  return (
    <aside className="flex w-[340px] shrink-0 flex-col border-l border-border bg-white">
      <div className="flex items-start justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">
            {day.weekday} {day.dateLabel}
            {day.isToday ? (
              <span className="ml-1.5 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                今天
              </span>
            ) : null}
          </h2>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {summary.headcount}人 / {summary.slots}人次
            {summary.emptyShifts > 0 ? ` · 空班 ${summary.emptyShifts}` : " · 满班"}
          </p>
        </div>
        <button
          type="button"
          className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-muted"
          aria-label="关闭"
        >
          <IconX size={16} />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-3">
        {SHIFTS.filter((s) => s.enabled).map((shift) => {
          const ids = BOARD_ASSIGNMENTS[`${shift.id}:${weekDayKey}`] ?? []
          return (
            <div key={shift.id} className="overflow-hidden rounded-lg border border-border">
              <div
                className="flex items-center justify-between px-3 py-2 text-white"
                style={{ background: shift.color }}
              >
                <div>
                  <div className="text-sm font-semibold">{shift.name}</div>
                  <div className="text-[11px] text-white/85">
                    {shift.start}–{shift.end}
                  </div>
                </div>
                <span className="text-xs font-medium tabular-nums">{ids.length}人</span>
              </div>
              <div className="space-y-2 bg-white px-3 py-2.5">
                {ids.length === 0 ? (
                  <div className="rounded-md border border-dashed border-border px-2 py-3 text-center text-[11px] text-muted-foreground">
                    暂无人员
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {ids.map((id) => {
                      const agent = agentById(id)
                      if (!agent) return null
                      return (
                        <span
                          key={id}
                          className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/30 px-1.5 py-0.5 text-[11px]"
                        >
                          {agent.name}
                          <IconX size={11} className="text-muted-foreground" />
                        </span>
                      )
                    })}
                  </div>
                )}
                <button
                  type="button"
                  className="inline-flex h-8 w-full items-center justify-center gap-1 rounded-md border border-border text-xs font-medium"
                >
                  <IconPlus size={14} />
                  添加员工
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </aside>
  )
}

function CalendarGrid({ selectedWeekDayKey }: { selectedWeekDayKey?: string }) {
  const weekdays = ["一", "二", "三", "四", "五", "六", "日"]
  const showBoard = Boolean(selectedWeekDayKey)

  return (
    <div className="flex min-h-0 flex-1">
      <div className="min-h-0 min-w-0 flex-1 overflow-auto p-4">
        <div className="mb-2 grid grid-cols-7 gap-px">
          {weekdays.map((w) => (
            <div
              key={w}
              className="px-2 py-1.5 text-center text-xs font-medium text-muted-foreground"
            >
              周{w}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-px overflow-hidden rounded-xl border border-border bg-border">
          {CALENDAR_CELLS.map((cell) => {
            const counts = cell.weekDayKey ? shiftCountsForDay(cell.weekDayKey) : []
            const hasData = counts.some((c) => c.count > 0)
            const selected =
              Boolean(selectedWeekDayKey) && cell.weekDayKey === selectedWeekDayKey
            return (
              <div
                key={cell.key}
                className={`min-h-[100px] bg-white p-2 ${
                  cell.outside ? "bg-muted/30" : ""
                } ${cell.isToday && !selected ? "ring-2 ring-inset ring-primary/30" : ""} ${
                  selected ? "ring-2 ring-inset ring-primary bg-primary/[0.04]" : ""
                }`}
              >
                <div
                  className={`mb-1.5 text-xs font-semibold tabular-nums ${
                    cell.outside
                      ? "text-muted-foreground/50"
                      : selected || cell.isToday
                        ? "text-primary"
                        : "text-foreground"
                  }`}
                >
                  {cell.dayNum}
                  {cell.isToday ? (
                    <span className="ml-1 text-[10px] font-medium">今天</span>
                  ) : null}
                </div>
                {cell.outside ? null : hasData ? (
                  <div className="space-y-1">
                    {counts.map(({ shift, count }) =>
                      count === 0 ? (
                        <div
                          key={shift.id}
                          className="flex items-center justify-between rounded px-1.5 py-0.5 text-[10px] text-muted-foreground/50"
                        >
                          <span>{shift.name}</span>
                          <span>0</span>
                        </div>
                      ) : (
                        <div
                          key={shift.id}
                          className="flex items-center justify-between rounded px-1.5 py-0.5 text-[10px] font-medium text-white"
                          style={{ background: shift.color }}
                        >
                          <span className="truncate">{shift.name}</span>
                          <span className="tabular-nums">{count}</span>
                        </div>
                      ),
                    )}
                  </div>
                ) : (
                  <div className="text-[10px] text-muted-foreground/60">未排</div>
                )}
              </div>
            )
          })}
        </div>
        {!showBoard ? (
          <p className="mt-3 text-center text-[11px] text-muted-foreground">
            点击某一天，在右侧查看当日详情看板
          </p>
        ) : null}
      </div>
      {selectedWeekDayKey ? (
        <CalendarDayDetailBoard weekDayKey={selectedWeekDayKey} />
      ) : null}
    </div>
  )
}

function EmptyPoolGuide() {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center bg-muted/20 px-8">
      <div className="w-[420px] rounded-xl border border-border bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <IconUsersGroup size={24} />
        </div>
        <h2 className="text-base font-semibold">请先选择排班池</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          选择一个或多个员工组后，即可在排班视图中添加客服。支持班次+日期、员工+日期与日历三种视图。
        </p>
        <button
          type="button"
          className="mt-5 h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
        >
          选择员工组
        </button>
      </div>
    </div>
  )
}

function MainView({
  layout,
  highlightEmpty,
  calendarSelectedDay,
}: {
  layout: LayoutView
  highlightEmpty?: boolean
  /** Week day key (d1–d7) for calendar right board; omit = no board. */
  calendarSelectedDay?: string
}) {
  if (layout === "agent-day") return <AgentDayGrid />
  if (layout === "calendar") {
    return <CalendarGrid selectedWeekDayKey={calendarSelectedDay} />
  }
  return <ShiftDayGrid highlightEmpty={highlightEmpty} />
}

/** Shared board chrome; layout switches among three schedule views. */
export function BoardScreen({
  mode = "filled",
  layout = "shift-day",
  highlightEmpty,
  calendarSelectedDay,
}: {
  mode?: BoardMode
  layout?: LayoutView
  highlightEmpty?: boolean
  calendarSelectedDay?: string
}) {
  const emptyPool = mode === "empty-pool"
  return (
    <SchedulingShell tab="board">
      <div className="flex h-full flex-col">
        <Toolbar emptyPool={emptyPool} layout={layout} />
        {emptyPool ? (
          <EmptyPoolGuide />
        ) : (
          <MainView
            layout={layout}
            highlightEmpty={highlightEmpty}
            calendarSelectedDay={calendarSelectedDay}
          />
        )}
      </div>
    </SchedulingShell>
  )
}

export function BoardFilledScreen() {
  return <BoardScreen mode="filled" layout="shift-day" />
}

export function BoardEmptyPoolScreen() {
  return <BoardScreen mode="empty-pool" layout="shift-day" />
}

export function BoardAgentDayScreen() {
  return <BoardScreen mode="filled" layout="agent-day" />
}

/** Calendar with Wednesday (today) selected and right-side day board open. */
export function BoardCalendarScreen() {
  return <BoardScreen mode="filled" layout="calendar" calendarSelectedDay="d3" />
}
