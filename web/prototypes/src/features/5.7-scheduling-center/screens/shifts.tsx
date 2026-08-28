import { IconPencil, IconPlus, IconTrash } from "@tabler/icons-react"
import { Switch } from "@/components/ui/switch"
import { SchedulingShell } from "../components/scheduling-shell"
import { SHIFTS } from "../fixtures"

/** Shift template admin list with preset morning / midday / evening. */
export function ShiftsScreen() {
  return (
    <SchedulingShell tab="shifts">
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between px-8 pt-8 pb-0">
          <h1 className="text-xl font-semibold text-foreground">班次管理</h1>
          <button
            type="button"
            className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
          >
            <IconPlus size={18} />
            新建班次
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-auto px-8 pt-6 pb-8">
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex h-14 items-center gap-6 rounded-t-lg bg-muted px-6">
              <div className="flex w-[100px] shrink-0 items-center">
                <span className="text-sm font-semibold text-foreground/80">班次</span>
              </div>
              <div className="flex min-w-0 flex-1 items-center">
                <span className="text-sm font-semibold text-foreground/80">名称</span>
              </div>
              <div className="flex w-[160px] shrink-0 items-center">
                <span className="text-sm font-semibold text-foreground/80">时段</span>
              </div>
              <div className="flex w-[80px] shrink-0 items-center">
                <span className="text-sm font-semibold text-foreground/80">排序</span>
              </div>
              <div className="flex w-[100px] shrink-0 items-center">
                <span className="text-sm font-semibold text-foreground/80">状态</span>
              </div>
              <div className="flex w-[70px] shrink-0 items-center">
                <span className="text-sm font-semibold text-foreground/80">操作</span>
              </div>
            </div>
            {SHIFTS.map((shift) => (
              <div
                key={shift.id}
                className="flex h-14 items-center gap-6 border-t border-border px-6"
              >
                <div className="flex w-[100px] shrink-0 items-center">
                  <span
                    className="inline-flex h-7 items-center justify-center rounded-md px-2.5 text-xs font-medium text-white"
                    style={{ background: shift.color }}
                  >
                    {shift.name}
                  </span>
                </div>
                <div className="flex min-w-0 flex-1 items-center">
                  <span className="truncate text-sm text-foreground">{shift.name}</span>
                </div>
                <div className="flex w-[160px] shrink-0 items-center">
                  <span className="tabular-nums text-sm text-muted-foreground">
                    {shift.start}–{shift.end}
                  </span>
                </div>
                <div className="flex w-[80px] shrink-0 items-center">
                  <span className="text-sm text-muted-foreground">{shift.sort}</span>
                </div>
                <div className="flex w-[100px] shrink-0 items-center">
                  <Switch checked={shift.enabled} aria-label="状态" />
                </div>
                <div className="flex w-[70px] shrink-0 items-center gap-3">
                  <button
                    type="button"
                    className="text-foreground/80 transition-colors hover:text-foreground"
                    aria-label="编辑"
                  >
                    <IconPencil size={18} />
                  </button>
                  <button
                    type="button"
                    className="cursor-not-allowed text-foreground/80 opacity-40"
                    title="该班次仍有排班记录，请先清空或改为停用"
                    aria-label="删除"
                  >
                    <IconTrash size={18} />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            删除按钮在仍有排班记录时禁用（演示态全部禁用）。跨夜班时段如 22:00–06:00 归属开始日。
          </p>
        </div>
      </div>
    </SchedulingShell>
  )
}
