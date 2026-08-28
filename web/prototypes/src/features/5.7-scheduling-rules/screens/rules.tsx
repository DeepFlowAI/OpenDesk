import { IconCopy, IconPencil, IconPlus, IconStar, IconTrash } from "@tabler/icons-react"
import { SchedulingShell } from "../components/scheduling-shell"
import {
  CONSTRAINTS,
  COVERAGE_TARGETS,
  ROTATION_TEMPLATE,
  RULE_SETS,
  SHIFTS,
  WEEK_DAYS,
} from "../fixtures"

export function RulesListScreen() {
  return (
    <SchedulingShell tab="rules">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between px-8 pt-8 pb-0">
          <h1 className="text-xl font-semibold text-foreground">排班规则</h1>
          <button
            type="button"
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
          >
            <IconPlus size={18} />
            新建规则集
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-auto px-8 pt-6 pb-8">
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="overflow-x-auto">
              <div style={{ minWidth: 980 }}>
                <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
                  <div className="w-[160px] shrink-0 text-sm font-semibold text-foreground/80">名称</div>
                  <div className="w-[80px] shrink-0 text-sm font-semibold text-foreground/80">默认</div>
                  <div className="min-w-[120px] flex-1 text-sm font-semibold text-foreground/80">绑定组</div>
                  <div className="min-w-[160px] flex-1 text-sm font-semibold text-foreground/80">目标摘要</div>
                  <div className="min-w-[160px] flex-1 text-sm font-semibold text-foreground/80">约束摘要</div>
                  <div className="w-[140px] shrink-0 text-sm font-semibold text-foreground/80">更新时间</div>
                  <div className="w-[96px] shrink-0 text-sm font-semibold text-foreground/80">操作</div>
                </div>
                {RULE_SETS.map((rs) => (
                  <div
                    key={rs.id}
                    className="flex h-14 items-center gap-6 border-t border-border px-6"
                  >
                    <div className="w-[160px] shrink-0 truncate text-sm font-medium text-foreground">
                      {rs.name}
                    </div>
                    <div className="flex w-[80px] shrink-0 items-center">
                      {rs.isDefault ? (
                        <span className="inline-flex items-center gap-0.5 rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary">
                          <IconStar size={12} />
                          默认
                        </span>
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </div>
                    <div className="min-w-[120px] flex-1 truncate text-sm text-muted-foreground">
                      {rs.groups}
                    </div>
                    <div className="min-w-[160px] flex-1 truncate text-sm text-muted-foreground">
                      {rs.coverageSummary}
                    </div>
                    <div className="min-w-[160px] flex-1 truncate text-sm text-muted-foreground">
                      {rs.constraintSummary}
                    </div>
                    <div className="w-[140px] shrink-0 truncate text-sm text-muted-foreground">
                      {rs.updatedAt}
                    </div>
                    <div className="flex w-[96px] shrink-0 items-center gap-3">
                      <button
                        type="button"
                        className="text-foreground/80 transition-colors hover:text-foreground"
                        aria-label="编辑"
                      >
                        <IconPencil size={18} />
                      </button>
                      <button
                        type="button"
                        className="text-foreground/80 transition-colors hover:text-foreground"
                        aria-label="复制"
                      >
                        <IconCopy size={18} />
                      </button>
                      <button
                        type="button"
                        className="text-foreground/80 transition-colors hover:text-destructive"
                        aria-label="删除"
                      >
                        <IconTrash size={18} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </SchedulingShell>
  )
}

export function RulesEmptyScreen() {
  return (
    <SchedulingShell tab="rules">
      <div className="flex h-full flex-col items-center justify-center px-8">
        <div className="max-w-md text-center">
          <h2 className="text-lg font-semibold">还没有排班规则</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            配置排班目标、工时约束和轮班模板后，即可按规则自动生成排班。
          </p>
          <button
            type="button"
            className="mt-6 inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          >
            <IconPlus size={16} />
            新建规则集
          </button>
        </div>
      </div>
    </SchedulingShell>
  )
}

export function RulesDetailScreen() {
  const weekdays = WEEK_DAYS.map((d) => d.weekday)
  return (
    <SchedulingShell tab="rules">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-border bg-white px-8 py-4">
          <div className="flex items-center gap-3">
            <button type="button" className="text-sm text-muted-foreground">
              ← 返回列表
            </button>
            <span className="text-border">|</span>
            <h1 className="text-lg font-semibold">在线客服标准周</h1>
            <span className="rounded-md bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
              默认
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
              设为默认
            </button>
            <button
              type="button"
              className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
            >
              保存
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 space-y-6 overflow-auto px-8 py-6">
          <section className="rounded-xl border border-border bg-white p-5">
            <h2 className="text-sm font-semibold">基本信息</h2>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <label className="block text-xs text-muted-foreground">
                名称
                <div className="mt-1 flex h-9 items-center rounded-md border border-border px-3 text-sm text-foreground">
                  在线客服标准周
                </div>
              </label>
              <label className="block text-xs text-muted-foreground">
                默认绑定员工组
                <div className="mt-1 flex h-9 items-center rounded-md border border-border px-3 text-sm">
                  在线客服一组
                </div>
              </label>
              <label className="col-span-2 block text-xs text-muted-foreground">
                说明
                <div className="mt-1 flex h-16 items-start rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
                  平日目标人数较高；周末早/中下调、晚班上调。用于规则生成与校验。
                </div>
              </label>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-white p-5">
            <h2 className="text-sm font-semibold">排班目标（班次 × 星期）</h2>
            <div className="mt-4 overflow-auto">
              <table className="w-full min-w-[640px] border-collapse text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground">
                    <th className="border border-border bg-muted/40 px-2 py-2 text-left font-medium">
                      班次
                    </th>
                    {weekdays.map((w) => (
                      <th
                        key={w}
                        className="border border-border bg-muted/40 px-2 py-2 text-center font-medium"
                      >
                        {w}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {SHIFTS.filter((s) => s.enabled).map((shift) => (
                    <tr key={shift.id}>
                      <td className="border border-border px-2 py-1.5">
                        <span
                          className="inline-flex rounded px-2 py-0.5 text-xs font-medium text-white"
                          style={{ background: shift.color }}
                        >
                          {shift.name}
                        </span>
                      </td>
                      {(COVERAGE_TARGETS[shift.id] ?? []).map((n, i) => (
                        <td key={i} className="border border-border px-2 py-1.5 text-center">
                          <span className="inline-flex h-8 min-w-[3.25rem] items-center justify-center gap-0.5 rounded-md border border-border px-1.5 tabular-nums">
                            <span>{n}</span>
                            <span className="text-[11px] text-muted-foreground">人</span>
                          </span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-white p-5">
            <div className="flex items-end justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold">工时约束</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  开关启用后可自定义参数；硬约束阻止写入，软约束仅提醒。
                </p>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {CONSTRAINTS.map((c) => (
                <div
                  key={c.name}
                  className={`flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2.5 text-sm ${
                    c.on ? "border-border bg-white" : "border-border/60 bg-muted/20 opacity-70"
                  }`}
                >
                  <span
                    className={`relative h-4 w-7 shrink-0 rounded-full ${c.on ? "bg-primary" : "bg-muted"}`}
                  >
                    <span
                      className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow ${
                        c.on ? "right-0.5" : "left-0.5"
                      }`}
                    />
                  </span>
                  <span className="w-36 shrink-0 font-medium">{c.name}</span>

                  {c.param ? (
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <span className="text-xs">{c.param.prefix}</span>
                      <span className="inline-flex h-8 w-14 items-center justify-center rounded-md border border-border bg-background tabular-nums text-foreground">
                        {c.param.value}
                      </span>
                      <span className="text-xs">{c.param.suffix}</span>
                      <span className="ml-1 text-[10px] text-muted-foreground/80">
                        {c.param.min}–{c.param.max}
                      </span>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">无数值参数 · 开启即按实际人数 vs 排班目标提示</span>
                  )}

                  <div className="ml-auto flex items-center gap-1 rounded-md border border-border p-0.5 text-[11px]">
                    <span
                      className={`rounded px-2 py-0.5 ${
                        c.level === "硬" ? "bg-red-50 font-medium text-red-700" : "text-muted-foreground"
                      }`}
                    >
                      硬
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 ${
                        c.level === "软"
                          ? "bg-amber-50 font-medium text-amber-800"
                          : "text-muted-foreground"
                      }`}
                    >
                      软
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-xl border border-border bg-white p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold">轮班模板</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  定义「班次 / 休」天序列；按规则生成时可选用并错位轮转。
                </p>
              </div>
              <button
                type="button"
                className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground"
              >
                <IconPlus size={14} />
                新建轮班模板
              </button>
            </div>
            <div className="mt-4 space-y-2">
              <div className="rounded-lg border border-border px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{ROTATION_TEMPLATE.name}</span>
                      <span className="rounded-md bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
                        生成默认
                      </span>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
                      {ROTATION_TEMPLATE.days.map((d, i) => (
                        <span key={i} className="inline-flex items-center gap-1">
                          {i > 0 ? <span className="text-muted-foreground">→</span> : null}
                          <span
                            className={`rounded px-2 py-0.5 ${
                              d === "休"
                                ? "bg-muted text-muted-foreground"
                                : "bg-primary/10 text-primary"
                            }`}
                          >
                            {d}
                          </span>
                        </span>
                      ))}
                    </div>
                    <div className="mt-1.5 text-[11px] text-muted-foreground">周期 5 天</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      className="h-8 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted"
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      className="h-8 rounded-md px-2 text-xs text-muted-foreground hover:bg-muted"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </SchedulingShell>
  )
}
