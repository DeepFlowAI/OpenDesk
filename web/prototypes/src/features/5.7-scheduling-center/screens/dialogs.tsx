import type { ReactNode } from "react"
import { IconCheck, IconSearch, IconX } from "@tabler/icons-react"
import { PICKER_AGENTS } from "../fixtures"
import { BoardFilledScreen } from "./board"
import { ShiftsScreen } from "./shifts"

function DialogOverlay({
  children,
  backdrop,
  wide,
}: {
  children: ReactNode
  backdrop: ReactNode
  wide?: boolean
}) {
  return (
    <div className="relative h-full">
      {backdrop}
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 p-8">
        <div
          className={`w-full ${wide ? "max-w-[560px]" : "max-w-[440px]"} rounded-xl border border-border bg-background shadow-2xl`}
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

function DialogFooter({ primary }: { primary: string }) {
  return (
    <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
      <button type="button" className="h-9 rounded-md border border-border px-4 text-sm">
        取消
      </button>
      <button
        type="button"
        className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
      >
        {primary}
      </button>
    </div>
  )
}

/** Add agents to a shift×day cell — pool-only picker. */
export function AddAgentsDialogScreen() {
  return (
    <DialogOverlay backdrop={<BoardFilledScreen />} wide>
      <DialogHeader title="添加员工" subtitle="周三 · 早班 · 仅显示当前排班池内人员" />
      <div className="space-y-3 px-5 py-4">
        <div className="flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground">
          <IconSearch size={14} />
          <span>搜索姓名…</span>
        </div>
        <div className="max-h-[320px] overflow-auto rounded-lg border border-border">
          {PICKER_AGENTS.map(({ agent, disabled, reason }) => (
            <div
              key={agent.id}
              className={`flex items-center gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0 ${
                disabled ? "bg-muted/30 text-muted-foreground" : ""
              }`}
            >
              <span
                className={`grid h-4 w-4 place-items-center rounded border ${
                  disabled
                    ? "border-border bg-muted"
                    : agent.id === "a5" || agent.id === "a6"
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-white"
                }`}
              >
                {!disabled && (agent.id === "a5" || agent.id === "a6") ? (
                  <IconCheck size={10} />
                ) : null}
              </span>
              <span className="flex-1 font-medium">{agent.name}</span>
              {agent.jobNumber ? (
                <span className="font-mono text-[11px] text-muted-foreground">
                  {agent.jobNumber}
                </span>
              ) : null}
              {disabled && reason ? (
                <span className="text-[11px] text-muted-foreground">{reason}</span>
              ) : null}
            </div>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">
          已选 2 人。同一天同一班不可重复添加；同一天可加入多个班次。
        </p>
      </div>
      <DialogFooter primary="添加到格子" />
    </DialogOverlay>
  )
}

/** Copy last week confirm with skip / overwrite. */
export function CopyWeekDialogScreen() {
  return (
    <DialogOverlay backdrop={<BoardFilledScreen />}>
      <DialogHeader title="复制上周排班" />
      <div className="space-y-4 px-5 py-4 text-sm">
        <p className="leading-6 text-muted-foreground">
          将上周排班按星期复制到本周。请选择遇到本周已有人员时的处理方式。仅复制当前池内员工。
        </p>
        <div className="space-y-2">
          <label className="flex items-start gap-2.5 rounded-lg border border-primary bg-primary/5 px-3 py-2.5">
            <span className="mt-0.5 grid h-4 w-4 place-items-center rounded-full border border-primary bg-primary">
              <span className="h-1.5 w-1.5 rounded-full bg-primary-foreground" />
            </span>
            <span>
              <span className="font-medium">跳过已有格子</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                本周已有人员的格子保持不变，只填充空格
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2.5 rounded-lg border border-border px-3 py-2.5">
            <span className="mt-0.5 h-4 w-4 rounded-full border border-border" />
            <span>
              <span className="font-medium">覆盖已有格子</span>
              <span className="mt-0.5 block text-xs text-muted-foreground">
                用上周对应人员替换本周格子内容
              </span>
            </span>
          </label>
        </div>
      </div>
      <DialogFooter primary="开始复制" />
    </DialogOverlay>
  )
}

/** Create / edit shift dialog over shifts list. */
export function ShiftFormDialogScreen() {
  return (
    <DialogOverlay backdrop={<ShiftsScreen />}>
      <DialogHeader title="新建班次" />
      <div className="space-y-4 px-5 py-4">
        <Field label="名称" required>
          <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm text-muted-foreground">
            例如：夜班
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="开始时间" required>
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">
              22:00
            </div>
          </Field>
          <Field label="结束时间" required>
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">
              06:00
            </div>
          </Field>
        </div>
        <p className="text-[11px] text-amber-700">结束早于开始时记为跨夜班，归属开始日。</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="颜色" required>
            <div className="flex h-9 items-center gap-2 rounded-md border border-border px-3">
              <span className="h-4 w-4 rounded-full bg-[oklch(0.45_0.12_280)]" />
              <span className="text-sm">色板</span>
            </div>
          </Field>
          <Field label="排序" required>
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">
              4
            </div>
          </Field>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
          <span className="text-sm">启用</span>
          <span className="relative h-5 w-9 rounded-full bg-primary">
            <span className="absolute right-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow" />
          </span>
        </div>
      </div>
      <DialogFooter primary="保存" />
    </DialogOverlay>
  )
}

function Field({
  label,
  required,
  children,
}: {
  label: string
  required?: boolean
  children: ReactNode
}) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium">
        {label}
        {required ? <span className="ml-0.5 text-destructive">*</span> : null}
      </div>
      {children}
    </div>
  )
}
