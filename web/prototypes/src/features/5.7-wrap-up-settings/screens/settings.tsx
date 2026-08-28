import { IconCheck, IconSettings } from "@tabler/icons-react"
import { AdminShell } from "@/prototypes/src/features/5.5-embedded-pages/components/admin-shell"
import { EngagementShell } from "@/prototypes/src/features/5.4-auto-outbound/components/engagement-shell"
import {
  TASK_WRAPUP_HINT,
  TRANSCRIPTION_DESC,
  WRAP_UP_HINT_INVALID,
  WRAP_UP_HINT_ZERO,
  WRAP_UP_SECTION_DESC,
} from "../fixtures"

function StaticSwitch({ on }: { on: boolean }) {
  return (
    <div className={`relative h-5 w-9 shrink-0 rounded-full ${on ? "bg-primary" : "bg-muted"}`}>
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm ${on ? "right-0.5" : "left-0.5"}`}
      />
    </div>
  )
}

function PriorSection({ title, desc }: { title: string; desc: string }) {
  return (
    <section className="opacity-50">
      <h2 className="text-sm font-medium text-foreground">{title}</h2>
      <p className="mt-1 max-w-[640px] text-sm leading-relaxed text-muted-foreground">{desc}</p>
      <div className="mt-3 h-16 max-w-[640px] rounded-lg border border-dashed border-border bg-muted/30" />
    </section>
  )
}

function DurationField({
  value,
  invalid,
  saveDisabled,
}: {
  value: string
  invalid?: boolean
  saveDisabled?: boolean
}) {
  return (
    <section className="flex max-w-[640px] flex-col gap-3">
      <h2 className="text-sm font-medium text-foreground">整理中</h2>
      <p className="text-sm leading-relaxed text-muted-foreground">{WRAP_UP_SECTION_DESC}</p>
      <label className="grid max-w-[240px] gap-1.5">
        <span className="text-sm font-medium text-foreground">
          <span className="mr-0.5 text-destructive">*</span>
          整理中时长（秒）
        </span>
        <div
          className={`flex h-10 items-center rounded-md border bg-background px-3 text-sm ${
            invalid ? "border-destructive" : "border-border"
          }`}
        >
          <span className="flex-1 tabular-nums">{value}</span>
          <span className="text-sm text-muted-foreground">秒</span>
        </div>
      </label>
      <p className={`text-sm leading-relaxed ${invalid ? "text-destructive" : "text-muted-foreground"}`}>
        {invalid
          ? WRAP_UP_HINT_INVALID
          : value === "0"
            ? WRAP_UP_HINT_ZERO
            : `挂断后进入整理中 ${value} 秒。客服可提前完成；到时自动回到就绪。`}
      </p>
      <button
        type="button"
        className={`flex h-10 w-fit items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-white ${
          saveDisabled ? "opacity-60" : ""
        }`}
      >
        保存
      </button>
    </section>
  )
}

export function CallCenterSettingsScreen({
  duration,
  invalid,
  dirty,
}: {
  duration: string
  invalid?: boolean
  dirty?: boolean
}) {
  const saveDisabled = invalid || !dirty
  return (
    <AdminShell active="call-settings">
      <div className="flex h-full flex-col overflow-hidden">
        <main className="min-h-0 flex-1 space-y-8 overflow-y-auto px-6 py-5 pb-10">
          <h1 className="text-xl font-semibold text-foreground">呼叫中心设置</h1>

          <section className="flex max-w-[640px] flex-col gap-3">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-sm font-medium text-foreground">是否开启坐席工作台实时语音转写</h2>
              <StaticSwitch on />
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">{TRANSCRIPTION_DESC}</p>
          </section>

          <DurationField value={duration} invalid={invalid} saveDisabled={saveDisabled} />

          <PriorSection
            title="通话提示音"
            desc="保持、咨询、三方、转接时播放给客户的提示音（沿用现网）"
          />
          <PriorSection
            title="弹屏嵌入页面"
            desc="在弹屏区追加第三方页面 Tab（沿用现网，走独立入口）"
          />

          <div className="opacity-50">
            <button
              type="button"
              className="flex h-10 items-center justify-center rounded-lg bg-primary px-5 text-sm font-medium text-white opacity-60"
            >
              保存
            </button>
            <p className="mt-2 text-xs text-muted-foreground">页底保存只提交转写与提示音</p>
          </div>

          <section className="flex max-w-[720px] flex-col gap-4 border-t border-border pt-8 opacity-60">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-foreground">外呼预筛意图</h2>
                <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                  维护相似表达、易混淆反例和相似度阈值（沿用现网，走独立入口）
                </p>
              </div>
              <button
                type="button"
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-border px-4 text-sm font-medium"
              >
                <IconSettings size={17} />
                配置
              </button>
            </div>
          </section>
        </main>
      </div>
    </AdminShell>
  )
}

export function AutoOutboundTaskFormScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border">
          <div className="px-6 py-4">
            <h1 className="text-xl font-semibold">新建自动外呼任务</h1>
          </div>
          <div className="flex items-center gap-2 px-6 pb-4">
            <span className="grid h-6 w-6 place-items-center rounded-full bg-emerald-100 text-emerald-700">
              <IconCheck size={13} />
            </span>
            <span className="text-sm text-muted-foreground">基础信息</span>
            <span className="mx-2 h-px w-10 bg-border" />
            <span className="grid h-6 w-6 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
              2
            </span>
            <span className="text-sm font-semibold">执行方式</span>
            <span className="mx-2 h-px w-10 bg-border" />
            <span className="grid h-6 w-6 place-items-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground">
              3
            </span>
            <span className="text-sm text-muted-foreground">外呼计划与呼叫策略</span>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto bg-surface p-6">
          <div className="mx-auto max-w-3xl">
            <section className="rounded-lg border border-border bg-background p-5">
              <h2 className="text-base font-semibold">自动转人工配置</h2>
              <div className="mt-4 grid grid-cols-2 gap-4">
                <label className="grid gap-1.5">
                  <span className="text-xs font-medium text-muted-foreground">
                    <span className="mr-0.5 text-destructive">*</span>
                    接待队列
                  </span>
                  <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">
                    续费接待队列
                  </div>
                </label>
                <label className="grid gap-1.5">
                  <span className="text-xs font-medium text-muted-foreground">
                    <span className="mr-0.5 text-destructive">*</span>
                    话后处理时长
                  </span>
                  <div className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
                    <span className="tabular-nums">60</span>
                    <span className="text-xs text-muted-foreground">秒</span>
                  </div>
                  <p className="text-[11px] leading-5 text-muted-foreground">{TASK_WRAPUP_HINT}</p>
                </label>
              </div>
              <p className="mt-4 text-[11px] leading-5 text-muted-foreground">
                取值 15–300，默认 60。覆盖租户「整理中」时长，只作用于本任务的坐席接待通话。
              </p>
            </section>
          </div>
        </main>
      </div>
    </EngagementShell>
  )
}
