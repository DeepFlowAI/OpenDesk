import type { ReactNode } from "react"
import { IconAlertTriangle, IconCheck, IconX } from "@tabler/icons-react"
import { RULE_SETS, WEEK_RANGE_LABEL } from "../fixtures"
import { BoardDirtyScreen } from "./board"

function DialogOverlay({
  children,
  wide,
}: {
  children: ReactNode
  wide?: boolean
}) {
  return (
    <div className="relative h-full">
      <BoardDirtyScreen />
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 p-8">
        <div
          className={`w-full ${wide ? "max-w-[640px]" : "max-w-[440px]"} rounded-xl border border-border bg-background shadow-2xl`}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

function DialogHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="flex items-start justify-between border-b border-border px-5 py-4">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        {subtitle ? <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p> : null}
      </div>
      <IconX size={18} className="mt-0.5 text-muted-foreground" />
    </div>
  )
}

function DialogFooter({
  primary,
  primaryVariant = "primary",
}: {
  primary: string
  primaryVariant?: "primary" | "destructive"
}) {
  return (
    <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
      <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
        取消
      </button>
      <button
        type="button"
        className={`h-9 rounded-md px-5 text-sm font-medium text-primary-foreground ${
          primaryVariant === "destructive" ? "bg-red-600" : "bg-primary"
        }`}
      >
        {primary}
      </button>
    </div>
  )
}

/** Generate dialog: pick rule set, then preview & confirm. */
export function GeneratePreviewScreen() {
  return (
    <DialogOverlay wide>
      <DialogHeader title="按规则生成" subtitle={`${WEEK_RANGE_LABEL} · 当前排班池`} />
      <div className="space-y-4 px-5 py-4">
        <div>
          <div className="mb-2 text-xs font-medium text-muted-foreground">规则集</div>
          <div className="space-y-2">
            {RULE_SETS.map((rs) => (
              <div
                key={rs.id}
                className={`flex cursor-default items-start gap-3 rounded-lg border px-3 py-2.5 ${
                  rs.isDefault
                    ? "border-primary bg-primary/5"
                    : "border-border bg-background"
                }`}
              >
                <span
                  className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border ${
                    rs.isDefault ? "border-primary bg-primary text-primary-foreground" : "border-border"
                  }`}
                >
                  {rs.isDefault ? <IconCheck size={10} stroke={3} /> : null}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <span className="truncate">{rs.name}</span>
                    {rs.isDefault ? (
                      <span className="rounded bg-primary/10 px-1.5 py-px text-[10px] text-primary">
                        默认
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
                    {rs.coverageSummary} · {rs.constraintSummary}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">模式</div>
            <div className="flex h-9 items-center gap-4 rounded-md border border-border px-3 text-xs">
              <label className="inline-flex items-center gap-1.5 font-medium">
                <span className="grid h-3.5 w-3.5 place-items-center rounded-full border border-primary bg-primary">
                  <span className="h-1.5 w-1.5 rounded-full bg-white" />
                </span>
                仅填空格
              </label>
              <label className="inline-flex items-center gap-1.5 text-muted-foreground">
                <span className="h-3.5 w-3.5 rounded-full border border-border" />
                清空后重排
              </label>
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">范围</div>
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-xs font-medium">
              {WEEK_RANGE_LABEL}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "将新增", value: "42 条" },
            { label: "将跳过", value: "6 格" },
            { label: "目标达成", value: "18 / 21 格" },
            { label: "软提醒", value: "3 条" },
          ].map((x) => (
            <div key={x.label} className="rounded-lg border border-border bg-muted/30 px-3 py-2.5">
              <div className="text-[11px] text-muted-foreground">{x.label}</div>
              <div className="mt-1 text-sm font-semibold tabular-nums">{x.value}</div>
            </div>
          ))}
        </div>
        <div className="rounded-lg border border-border">
          <div className="border-b border-border bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
            变更摘要（节选）
          </div>
          <div className="max-h-[160px] space-y-0 overflow-auto text-sm">
            {[
              "周一 · 早班 ← 张敏、李强、王芳、赵磊",
              "周一 · 中班 ← 陈雪、周凯、孙悦、吴婷、王芳",
              "周三 · 早班 ← 张敏、李强、王芳（缺口 1）",
              "周六 · 晚班 ← 孙悦、吴婷、陈雪、赵磊",
              "… 其余 17 格略",
            ].map((line) => (
              <div
                key={line}
                className="border-b border-border px-3 py-2 text-xs last:border-b-0"
              >
                {line}
              </div>
            ))}
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">
          确认后写入当前编辑态。若本周已发布，状态将变为「有未发布变更」。
        </p>
      </div>
      <DialogFooter primary="确认写入" />
    </DialogOverlay>
  )
}

/** Publish confirm — persist week snapshot. */
export function PublishConfirmScreen() {
  return (
    <DialogOverlay>
      <DialogHeader title="发布本周排班" subtitle={WEEK_RANGE_LABEL} />
      <div className="space-y-3 px-5 py-4 text-sm">
        <p className="leading-6 text-muted-foreground">
          发布后将确认并保存本周当前排班。之后可用「重置」恢复到本版结果。
        </p>
        <div className="rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2.5 text-xs text-amber-900">
          <div className="flex items-start gap-1.5">
            <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>当前存在 1 条硬约束冲突（张敏 · 周三晚班休息间隔）。仍可发布，建议先处理。</span>
          </div>
        </div>
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
          <li>将覆盖本周上一份已发布快照（若有）</li>
          <li>不会通知坐席；外发请继续使用导出</li>
        </ul>
      </div>
      <DialogFooter primary="确认发布" />
    </DialogOverlay>
  )
}

/** Reset confirm — restore editing state from published snapshot. */
export function ResetConfirmScreen() {
  return (
    <DialogOverlay>
      <DialogHeader title="重置为已发布排班" subtitle={WEEK_RANGE_LABEL} />
      <div className="space-y-3 px-5 py-4 text-sm">
        <p className="leading-6 text-muted-foreground">
          将丢弃本周发布后的全部修改，恢复为上次发布的排班结果。此操作不可撤销。
        </p>
        <div className="rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-xs text-muted-foreground">
          上次发布：2026-08-06 16:40 · 将撤销例如「张敏 · 周三晚班」等未发布改动
        </div>
      </div>
      <DialogFooter primary="确定重置" primaryVariant="destructive" />
    </DialogOverlay>
  )
}

/** Soft constraint continue confirm. */
export function SoftWarnScreen() {
  return (
    <DialogOverlay>
      <DialogHeader title="存在排班提醒" subtitle="软约束 · 仍可继续" />
      <div className="space-y-2 px-5 py-4">
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2.5 text-xs">
          张敏 · 周三：当天班次数将变为 2（软上限）
        </div>
        <p className="text-xs text-muted-foreground">确认后写入，并在格子上保留提醒角标。</p>
      </div>
      <DialogFooter primary="仍要继续" />
    </DialogOverlay>
  )
}

/** Hard constraint block. */
export function HardBlockScreen() {
  return (
    <DialogOverlay>
      <DialogHeader title="无法添加" subtitle="硬约束冲突" />
      <div className="space-y-3 px-5 py-4">
        <div className="rounded-lg border border-red-200 bg-red-50/70 px-3 py-2.5 text-sm">
          <div className="flex items-start gap-1.5">
            <IconAlertTriangle size={16} className="mt-0.5 shrink-0 text-red-600" />
            <div>
              <div className="font-medium">张敏：与前一班休息间隔不足 8 小时</div>
              <div className="mt-1 text-xs text-muted-foreground">
                周三早班 13:00 结束 → 晚班 18:00 开始，间隔 5 小时
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="flex items-center justify-end border-t border-border px-5 py-4">
        <button
          type="button"
          className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
        >
          知道了
        </button>
      </div>
    </DialogOverlay>
  )
}
