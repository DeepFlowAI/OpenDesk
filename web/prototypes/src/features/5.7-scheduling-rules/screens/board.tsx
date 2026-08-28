import {
  IconAlertTriangle,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconCopy,
  IconDownload,
  IconFilter,
  IconPlus,
  IconRefresh,
  IconSparkles,
  IconUpload,
  IconUsersGroup,
  IconX,
} from "@tabler/icons-react"
import { SchedulingShell } from "../components/scheduling-shell"
import {
  BOARD_ASSIGNMENTS,
  POOL_MEMBER_COUNT,
  SELECTED_POOL_LABEL,
  SHIFTS,
  VIOLATIONS,
  WEEK_DAYS,
  WEEK_RANGE_LABEL,
  agentById,
  daySummary,
  publishStateLabel,
  type PublishState,
} from "../fixtures"

function PublishTag({ state }: { state: PublishState }) {
  const label = publishStateLabel(state)
  if (state === "unpublished") {
    return (
      <span className="rounded-md bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
        {label}
      </span>
    )
  }
  if (state === "published") {
    return (
      <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
        {label}
      </span>
    )
  }
  return (
    <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
      {label}
    </span>
  )
}

function Toolbar({
  publishState,
  showValidationDrawer,
}: {
  publishState: PublishState
  showValidationDrawer?: boolean
}) {
  const resetDisabled = publishState !== "dirty"
  const resetTitle =
    publishState === "unpublished"
      ? "本周尚未发布，无法重置"
      : publishState === "published"
        ? "当前已是已发布结果"
        : undefined

  return (
    <div className="shrink-0 border-b border-border bg-white">
      {/* Row 1: pool, rules, generate, publish/reset, filters, batch */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">排班池</span>
          <div className="flex h-8 items-center gap-2 rounded-md border border-border bg-background px-2 text-sm">
            <span className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              <IconUsersGroup size={12} />
              {SELECTED_POOL_LABEL}
              <IconX size={12} className="opacity-60" />
            </span>
            <IconChevronDown size={14} className="text-muted-foreground" />
          </div>
          <span className="text-xs text-muted-foreground">池内 {POOL_MEMBER_COUNT} 人</span>
        </div>

        <span className="h-5 w-px bg-border" />

        <button
          type="button"
          className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2.5 text-xs"
        >
          <IconSparkles size={14} />
          按规则生成
        </button>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2.5 text-xs"
        >
          <IconCopy size={14} />
          复制上周
        </button>

        <button
          type="button"
          className={`inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs ${
            showValidationDrawer
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-border"
          }`}
        >
          <IconFilter size={14} />
          违规筛选
        </button>

        <div className="ml-auto flex items-center gap-2">
          <PublishTag state={publishState} />
          <button
            type="button"
            title={resetTitle}
            className={`inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs ${
              resetDisabled ? "pointer-events-none opacity-40" : ""
            }`}
          >
            <IconRefresh size={14} />
            重置
          </button>
          <button
            type="button"
            className="inline-flex h-8 items-center gap-1 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
          >
            <IconUpload size={14} />
            发布
          </button>
        </div>
      </div>

      {/* Row 2: view · time range · quick jump | export Excel */}
      <div className="flex flex-wrap items-center gap-2 border-t border-border/70 px-4 py-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">视图</span>
          <div className="inline-flex h-8 items-center rounded-md border border-border bg-muted/40 p-0.5">
            <div className="rounded bg-background px-2.5 py-1 text-xs font-medium shadow-sm">
              班次
            </div>
            <div className="px-2.5 py-1 text-xs text-muted-foreground">员工</div>
            <div className="px-2.5 py-1 text-xs text-muted-foreground">日历</div>
          </div>
        </div>

        <span className="h-5 w-px bg-border" />

        <div className="flex items-center gap-1">
          <button
            type="button"
            className="grid h-8 w-8 place-items-center rounded-md border border-border text-muted-foreground"
          >
            <IconChevronLeft size={16} />
          </button>
          <div className="flex h-8 items-center rounded-md border border-border px-2.5 text-xs font-medium">
            {WEEK_RANGE_LABEL}
          </div>
          <button
            type="button"
            className="grid h-8 w-8 place-items-center rounded-md border border-border text-muted-foreground"
          >
            <IconChevronRight size={16} />
          </button>
        </div>

        <button type="button" className="h-8 rounded-md border border-border px-2.5 text-xs">
          本周
        </button>

        <div className="ml-auto">
          <button
            type="button"
            className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2.5 text-xs"
          >
            <IconDownload size={14} />
            导出 Excel
          </button>
        </div>
      </div>
    </div>
  )
}

function AgentChip({ name, dirty }: { name: string; dirty?: boolean }) {
  return (
    <span
      className={`inline-flex max-w-full items-center rounded-md border px-1.5 py-0.5 text-[11px] leading-4 ${
        dirty ? "border-amber-300 bg-amber-50" : "border-border bg-white"
      }`}
    >
      <span className="truncate">{name}</span>
    </span>
  )
}

function cellViolations(cellKey: string) {
  return VIOLATIONS.filter((v) => v.cellKey === cellKey)
}

function DailySummaryRow() {
  return (
    <div
      className="sticky bottom-0 z-20 grid border-t border-border bg-muted/50"
      style={{ gridTemplateColumns: "140px repeat(7, minmax(0, 1fr))" }}
    >
      <div className="sticky left-0 z-10 flex items-center border-r border-border bg-muted/70 px-3 py-2 text-xs font-semibold text-muted-foreground">
        当日统计
      </div>
      {WEEK_DAYS.map((day) => {
        const s = daySummary(day.key)
        return (
          <div
            key={day.key}
            className={`border-r border-border px-1.5 py-1.5 last:border-r-0 ${
              day.isToday ? "bg-primary/5" : ""
            }`}
          >
            <div className="text-[10px] font-semibold tabular-nums">
              {s.headcount}人 / {s.slots}人次
            </div>
            <div className="mt-0.5 flex flex-wrap gap-0.5">
              {s.byShift.map((x) => (
                <span
                  key={x.id}
                  className="rounded px-1 py-px text-[9px] font-medium text-white"
                  style={{ background: x.color }}
                >
                  {x.name}
                  {x.count}/{x.target}人
                </span>
              ))}
            </div>
            <div className="mt-0.5 flex flex-wrap gap-0.5">
              {s.gap > 0 ? (
                <span className="rounded bg-amber-50 px-1 py-px text-[9px] text-amber-800">
                  缺口{s.gap}
                </span>
              ) : null}
              {s.overflow > 0 ? (
                <span className="rounded bg-muted px-1 py-px text-[9px] text-muted-foreground">
                  溢出{s.overflow}
                </span>
              ) : null}
              {s.gap === 0 && s.overflow === 0 ? (
                <span className="rounded bg-emerald-50 px-1 py-px text-[9px] text-emerald-700">
                  达标
                </span>
              ) : null}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ShiftDayGrid() {
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="min-w-[980px]">
        <div
          className="grid border-b border-border bg-muted/40"
          style={{ gridTemplateColumns: "140px repeat(7, minmax(0, 1fr))" }}
        >
          <div className="sticky left-0 z-10 border-r border-border bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
            班次 \ 日期
          </div>
          {WEEK_DAYS.map((day) => (
            <div
              key={day.key}
              className={`border-r border-border px-2 py-2 text-center last:border-r-0 ${
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
              const cellKey = `${shift.id}:${day.key}`
              const ids = BOARD_ASSIGNMENTS[cellKey] ?? []
              const empty = ids.length === 0
              const viols = cellViolations(cellKey)
              const hasHard = viols.some((v) => v.level === "hard")
              const hasSoft = viols.some((v) => v.level === "soft")
              return (
                <div
                  key={day.key}
                  className={`relative min-h-[80px] border-r border-border p-1.5 last:border-r-0 ${
                    day.isToday ? "bg-primary/[0.03]" : "bg-white"
                  } ${hasHard ? "ring-1 ring-inset ring-red-300" : hasSoft ? "ring-1 ring-inset ring-amber-200" : ""}`}
                >
                  {(hasHard || hasSoft) && (
                    <span
                      className={`absolute right-1 top-1 h-2 w-2 rounded-full ${
                        hasHard ? "bg-red-500" : "bg-amber-500"
                      }`}
                      title={viols.map((v) => v.reason).join("；")}
                    />
                  )}
                  {empty ? (
                    <div className="flex h-full min-h-[68px] items-center justify-center rounded-md border border-dashed border-border/80 text-[11px] text-muted-foreground">
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
                        const dirty = cellKey === "evening:d3" && id === "a1"
                        return <AgentChip key={id} name={agent.name} dirty={dirty} />
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

function ValidationDrawer() {
  return (
    <aside className="flex w-[320px] shrink-0 flex-col border-l border-border bg-white">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-sm font-semibold">校验</div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            本周 · {VIOLATIONS.length} 条提醒
          </div>
        </div>
        <IconX size={16} className="text-muted-foreground" />
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-auto p-3">
        {VIOLATIONS.map((v) => (
          <div
            key={v.id}
            className={`rounded-lg border px-3 py-2.5 text-xs ${
              v.level === "hard"
                ? "border-red-200 bg-red-50/60"
                : "border-amber-200 bg-amber-50/50"
            }`}
          >
            <div className="flex items-center gap-1.5 font-medium">
              <IconAlertTriangle
                size={14}
                className={v.level === "hard" ? "text-red-600" : "text-amber-700"}
              />
              <span>{v.level === "hard" ? "硬约束" : "软约束"}</span>
              <span className="text-muted-foreground">· {v.dayLabel}</span>
            </div>
            <div className="mt-1 text-foreground/90">
              {v.agentName !== "—" ? `${v.agentName}：` : ""}
              {v.reason}
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}

function BoardLayout({
  publishState,
  showDrawer,
}: {
  publishState: PublishState
  showDrawer?: boolean
}) {
  return (
    <SchedulingShell tab="board">
      <div className="flex h-full flex-col">
        <Toolbar publishState={publishState} showValidationDrawer={showDrawer} />
        <div className="flex min-h-0 flex-1">
          <ShiftDayGrid />
          {showDrawer ? <ValidationDrawer /> : null}
        </div>
      </div>
    </SchedulingShell>
  )
}

/** Default review screen: dirty after publish + validation drawer open. */
export function BoardDirtyScreen() {
  return <BoardLayout publishState="dirty" showDrawer />
}

/** Published and in sync — reset disabled. */
export function BoardPublishedScreen() {
  return <BoardLayout publishState="published" />
}
