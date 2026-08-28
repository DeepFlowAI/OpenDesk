import { IconPlus, IconTrash, IconX } from "@tabler/icons-react"
import { SHIFTS } from "../fixtures"
import { RulesDetailScreen } from "./rules"

const DRAFT_DAYS: { id: string; kind: "shift" | "off"; label: string; color?: string }[] = [
  { id: "1", kind: "shift", label: "早班", color: SHIFTS[0].color },
  { id: "2", kind: "shift", label: "早班", color: SHIFTS[0].color },
  { id: "3", kind: "shift", label: "晚班", color: SHIFTS[2].color },
  { id: "4", kind: "off", label: "休" },
  { id: "5", kind: "off", label: "休" },
]

/** Create / edit rotation template dialog over rules detail. */
export function RotationTemplateFormScreen() {
  return (
    <div className="relative h-full">
      <RulesDetailScreen />
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 p-8">
        <div className="w-full max-w-[560px] rounded-xl border border-border bg-background shadow-2xl">
          <div className="flex items-start justify-between border-b border-border px-5 py-4">
            <div>
              <h2 className="text-base font-semibold">新建轮班模板</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                按天配置班次或休，生成时按此序列错位轮转分配给池内员工。
              </p>
            </div>
            <IconX size={18} className="mt-0.5 text-muted-foreground" />
          </div>

          <div className="space-y-4 px-5 py-4">
            <label className="block text-xs text-muted-foreground">
              模板名称
              <div className="mt-1 flex h-9 items-center rounded-md border border-border px-3 text-sm text-foreground">
                上三休二
              </div>
            </label>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  天序列（周期 {DRAFT_DAYS.length} 天，范围 2～28）
                </span>
                <button
                  type="button"
                  className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px]"
                >
                  <IconPlus size={12} />
                  添加一天
                </button>
              </div>

              <div className="space-y-2 rounded-lg border border-border p-3">
                {DRAFT_DAYS.map((day, index) => (
                  <div
                    key={day.id}
                    className="flex items-center gap-2 rounded-md border border-border bg-muted/20 px-2.5 py-2"
                  >
                    <span className="w-10 shrink-0 text-xs font-medium text-muted-foreground">
                      第 {index + 1} 天
                    </span>
                    <div className="inline-flex h-8 items-center rounded-md border border-border bg-background p-0.5 text-[11px]">
                      <span
                        className={`rounded px-2 py-1 ${
                          day.kind === "shift"
                            ? "bg-primary/10 font-medium text-primary"
                            : "text-muted-foreground"
                        }`}
                      >
                        班次
                      </span>
                      <span
                        className={`rounded px-2 py-1 ${
                          day.kind === "off"
                            ? "bg-muted font-medium text-foreground"
                            : "text-muted-foreground"
                        }`}
                      >
                        休
                      </span>
                    </div>
                    {day.kind === "shift" ? (
                      <div className="flex h-8 min-w-[120px] flex-1 items-center gap-2 rounded-md border border-border bg-background px-2 text-xs">
                        <span
                          className="inline-flex rounded px-1.5 py-0.5 font-medium text-white"
                          style={{ background: day.color }}
                        >
                          {day.label}
                        </span>
                        <span className="ml-auto text-muted-foreground">▾</span>
                      </div>
                    ) : (
                      <div className="flex h-8 flex-1 items-center rounded-md border border-dashed border-border px-2 text-xs text-muted-foreground">
                        休息日（不排班）
                      </div>
                    )}
                    <button
                      type="button"
                      className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-muted"
                      title="删除该天"
                    >
                      <IconTrash size={14} />
                    </button>
                  </div>
                ))}
              </div>

              <p className="mt-2 text-[11px] text-muted-foreground">
                预览：
                {DRAFT_DAYS.map((d, i) => (
                  <span key={d.id}>
                    {i > 0 ? " → " : " "}
                    <span
                      className={
                        d.kind === "off" ? "text-muted-foreground" : "font-medium text-foreground"
                      }
                    >
                      {d.label}
                    </span>
                  </span>
                ))}
              </p>
            </div>

            <label className="flex items-center gap-2 text-sm">
              <span className="relative h-4 w-7 rounded-full bg-primary">
                <span className="absolute right-0.5 top-0.5 h-3 w-3 rounded-full bg-white shadow" />
              </span>
              <span>设为生成时的默认模板</span>
            </label>
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
            <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
              取消
            </button>
            <button
              type="button"
              className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
            >
              保存模板
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
