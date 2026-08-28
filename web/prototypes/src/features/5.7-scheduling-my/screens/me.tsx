import type { ReactNode } from "react"
import { IconChevronLeft, IconChevronRight } from "@tabler/icons-react"
import { SchedulingShell, type ShellMode } from "../components/scheduling-shell"
import {
  MY_WEEK_DAYS,
  MY_WEEK_EMPTY_DAYS,
  WEEK_RANGE_LABEL,
  type DayRow,
  type ShiftChip,
} from "../fixtures"

function ShiftChipView({ shift }: { shift: ShiftChip }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-white"
      style={{ backgroundColor: shift.color }}
    >
      <span>{shift.name}</span>
      <span className="opacity-90">
        {shift.start}–{shift.end}
      </span>
    </span>
  )
}

function WeekToolbar() {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-border bg-white px-6 py-3">
      <button
        type="button"
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground"
        aria-label="上一周"
      >
        <IconChevronLeft size={16} />
      </button>
      <div className="min-w-[200px] text-center text-sm font-medium tabular-nums">
        {WEEK_RANGE_LABEL}
      </div>
      <button
        type="button"
        className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-muted-foreground"
        aria-label="下一周"
      >
        <IconChevronRight size={16} />
      </button>
      <button
        type="button"
        className="ml-1 h-8 rounded-md border border-border bg-white px-3 text-sm text-foreground"
      >
        本周
      </button>
      <span className="ml-auto text-xs text-muted-foreground">仅展示已发布 · 仅本人</span>
    </div>
  )
}

function TodaySummary({ days }: { days: DayRow[] }) {
  const today = days.find((d) => d.isToday)
  if (!today) return null

  return (
    <div className="flex shrink-0 items-center gap-3 border-b border-border bg-accent/40 px-6 py-3">
      <span className="text-sm font-medium">今天：</span>
      {today.shifts.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {today.shifts.map((shift) => (
            <ShiftChipView key={shift.id} shift={shift} />
          ))}
        </div>
      ) : (
        <span className="text-sm text-muted-foreground">今天未排班</span>
      )}
    </div>
  )
}

function DayList({ days }: { days: DayRow[] }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
      <div className="overflow-hidden rounded-lg border border-border bg-white">
        {days.map((day, index) => (
          <div
            key={day.key}
            className={`flex items-center gap-4 px-4 py-3.5 ${
              index > 0 ? "border-t border-border" : ""
            } ${day.isToday ? "bg-accent/50" : ""}`}
          >
            <div className="w-24 shrink-0">
              <div className="text-sm font-medium">
                {day.weekday}
                {day.isToday ? (
                  <span className="ml-1.5 text-xs font-normal text-primary">今天</span>
                ) : null}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">{day.dateLabel}</div>
            </div>
            <div className="flex min-w-0 flex-1 flex-wrap gap-2">
              {day.shifts.length > 0 ? (
                day.shifts.map((shift) => <ShiftChipView key={shift.id} shift={shift} />)
              ) : (
                <span className="text-sm text-muted-foreground">未排班</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function EmptyPanel({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center px-6 py-8">
      <div className="flex h-[360px] w-full max-w-2xl flex-col items-center justify-center rounded-lg border border-dashed border-border bg-white/60">
        <p className="text-sm text-muted-foreground">{title}</p>
        {hint ? <p className="mt-2 text-xs text-muted-foreground/80">{hint}</p> : null}
      </div>
    </div>
  )
}

function MySchedulePage({
  mode,
  children,
  showTodaySummary,
  days,
}: {
  mode: ShellMode
  children?: ReactNode
  showTodaySummary?: boolean
  days?: DayRow[]
}) {
  return (
    <SchedulingShell tab="me" mode={mode}>
      <div className="flex h-full flex-col overflow-hidden">
        <WeekToolbar />
        {showTodaySummary && days ? <TodaySummary days={days} /> : null}
        {children}
      </div>
    </SchedulingShell>
  )
}

/** Agent-only: one Tab, published week with personal shifts. */
export function MyScheduleFilledScreen() {
  return (
    <MySchedulePage mode="agent-only" showTodaySummary days={MY_WEEK_DAYS}>
      <DayList days={MY_WEEK_DAYS} />
    </MySchedulePage>
  )
}

/** Week has no published snapshot yet. */
export function MyScheduleUnpublishedScreen() {
  return (
    <MySchedulePage mode="agent-only">
      <EmptyPanel
        title="本周排班尚未发布"
        hint="主管发布后，你的班次会出现在这里"
      />
    </MySchedulePage>
  )
}

/** Snapshot exists but current agent has no shifts this week. */
export function MyScheduleNoShiftsScreen() {
  return (
    <MySchedulePage mode="agent-only" showTodaySummary days={MY_WEEK_EMPTY_DAYS}>
      <EmptyPanel title="本周你没有排班" hint="本周班表已发布，但未安排你的班次" />
    </MySchedulePage>
  )
}

/** Manage + my.view: four Tabs, My Schedule active. */
export function MyScheduleWithManageScreen() {
  return (
    <MySchedulePage mode="with-manage" showTodaySummary days={MY_WEEK_DAYS}>
      <DayList days={MY_WEEK_DAYS} />
    </MySchedulePage>
  )
}
