import { useState } from "react"
import { IconCheck, IconChevronDown, IconChevronRight, IconPhone, IconPhoneIncoming, IconPhoneOff } from "@tabler/icons-react"
import { CallWorkspaceShell, type AgentPresence } from "./shell"
import { ConversationColumn, type BotSegment, type HandoffDivider } from "./conversation"
import type { TranscriptLine } from "../fixtures"

export function LiveWorkspace({
  presence,
  bar,
  bot,
  lines,
  divider,
  handoffTime,
  agentTitle,
  agentLines,
  agentNote,
  duration = "00:00",
  facts = "open",
  foldable,
}: {
  presence: AgentPresence
  bar: "ringing" | "on-call" | "wrap-up"
  duration?: string
  bot: BotSegment
  lines: TranscriptLine[]
  divider: HandoffDivider
  handoffTime?: string
  agentTitle?: string
  agentLines?: TranscriptLine[]
  agentNote?: string
  facts?: "open" | "collapsed" | "toggle"
  foldable?: boolean
}) {
  const showFold = foldable ?? facts !== "open"
  return (
    <CallWorkspaceShell presence={presence}>
      {bar === "ringing" ? <RingingBar /> : bar === "wrap-up" ? <WrapUpBar duration={duration} /> : <OnCallBar />}
      <div className="grid min-h-0 flex-1 grid-cols-3 gap-4 p-5">
        <CallInfoColumn
          duration={duration}
          facts={facts}
          foldable={showFold}
          bot={bot}
          lines={lines}
          divider={divider}
          handoffTime={handoffTime}
          agentTitle={agentTitle}
          agentLines={agentLines}
          agentNote={agentNote}
        />
        <CustomerColumn />
        <SummaryColumn />
      </div>
    </CallWorkspaceShell>
  )
}

/** Review-only toggle. Click the header to fold or unfold call facts. */
export function FoldableLiveWorkspace(
  props: Omit<Parameters<typeof LiveWorkspace>[0], "facts">,
) {
  return <LiveWorkspace {...props} facts="toggle" />
}

export function HistoryWorkspace({
  botOnly,
  lines,
  divider,
  handoffTime,
  agentLines,
  agentNote,
}: {
  botOnly?: boolean
  lines: TranscriptLine[]
  divider: HandoffDivider
  handoffTime?: string
  agentLines?: TranscriptLine[]
  agentNote?: string
}) {
  const [factsOpen, setFactsOpen] = useState(false)
  const duration = botOnly ? "01:12" : "04:36"
  return (
    <CallWorkspaceShell presence="idle" selectedHistory>
      <div className="grid min-h-0 flex-1 grid-cols-3 gap-4 p-5">
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-background p-5">
          <div className="mb-3 flex shrink-0 items-center justify-between gap-2 border-b border-border pb-2">
            <button
              type="button"
              className="-mx-1 flex min-w-0 flex-1 items-center justify-between gap-2 rounded-md px-1 text-left hover:bg-muted/60"
              onClick={() => setFactsOpen((open) => !open)}
            >
              <h3 className="flex shrink-0 items-center gap-2 text-sm font-semibold">
                <IconPhone size={16} className="text-muted-foreground" />
                通话信息
              </h3>
              <span className="flex min-w-0 items-center gap-2">
                {!factsOpen && (
                  <span className="truncate text-xs text-muted-foreground">呼入 · 138 0013 8000 · {duration}</span>
                )}
                {factsOpen ? (
                  <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
                ) : (
                  <IconChevronRight size={16} className="shrink-0 text-muted-foreground" />
                )}
              </span>
            </button>
            <span className="shrink-0 text-xs font-medium text-primary">返回当前通话</span>
          </div>
          {factsOpen && (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <h4 className="mb-2 text-xs font-semibold text-foreground/70">通话录音</h4>
              <p className="mb-4 text-sm text-muted-foreground">暂无通话录音</p>
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                <Fact label="通话类型" value="呼入" />
                <Fact label="用户号码" value="138 0013 8000" />
                <Fact label="服务号码" value="400 820 8820" />
                <Fact label="通话时长" value={duration} />
                <Fact label="接听坐席" value={botOnly ? "—" : "张敏"} />
                <Fact label="机器人接待" value="是" />
                <Fact label="通话 ID" value="call_7b55bea8" mono />
              </dl>
            </div>
          )}
          <ConversationColumn
            flushTop={!factsOpen}
            bot="ready"
            lines={lines}
            divider={divider}
            handoffTime={handoffTime}
            agentTitle="对话记录"
            agentLines={agentLines}
            agentNote={agentNote}
          />
        </section>
        <CustomerColumn />
        <SummaryColumn />
      </div>
    </CallWorkspaceShell>
  )
}

function RingingBar() {
  return (
    <header className="flex h-[72px] shrink-0 items-center gap-6 border-b border-border bg-background px-5">
      <span className="flex items-center gap-2 font-semibold text-amber-700">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100">
          <IconPhoneIncoming size={16} />
        </span>
        来电
      </span>
      <BarField label="通话类型" value="呼入" />
      <BarField label="用户号码" value="138 0013 8000" />
      <BarField label="服务号码" value="400 820 8820" />
      <BarField label="响铃时长" value="00:08" />
      <div className="ml-auto flex items-center gap-2">
        <span className="grid h-10 w-10 place-items-center rounded-full bg-red-500 text-white">
          <IconPhoneOff size={16} />
        </span>
        <span className="grid h-10 w-10 place-items-center rounded-full bg-emerald-500 text-white">
          <IconPhone size={16} />
        </span>
      </div>
    </header>
  )
}

function OnCallBar() {
  return (
    <header className="flex h-[72px] shrink-0 items-center gap-6 border-b border-border bg-background px-5">
      <span className="flex items-center gap-2 font-semibold">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-emerald-100 text-emerald-700">
          <IconPhone size={16} />
        </span>
        通话中
      </span>
      <BarField label="用户号码" value="138 0013 8000" />
      <BarField label="通话时长" value="00:42" />
      <span className="ml-auto grid h-10 w-10 place-items-center rounded-full bg-red-500 text-white">
        <IconPhoneOff size={16} />
      </span>
    </header>
  )
}

function WrapUpBar({ duration }: { duration: string }) {
  return (
    <header className="flex h-[72px] shrink-0 items-center gap-6 border-b border-border bg-background px-5">
      <span className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100 text-amber-700">
          <IconCheck size={16} />
        </span>
        <span>
          <span className="block font-semibold">通话已结束，请整理本次记录</span>
          <span className="text-xs text-muted-foreground">本次通话时长：{duration}</span>
        </span>
      </span>
      <span className="ml-auto font-mono text-sm tabular-nums text-muted-foreground">整理剩余 00:16</span>
      <span className="grid h-10 w-10 place-items-center rounded-full bg-emerald-500 text-white">
        <IconCheck size={16} />
      </span>
    </header>
  )
}

function CallInfoColumn({
  duration,
  facts,
  foldable,
  bot,
  lines,
  divider,
  handoffTime,
  agentTitle,
  agentLines,
  agentNote,
}: {
  duration: string
  facts: "open" | "collapsed" | "toggle"
  foldable: boolean
  bot: BotSegment
  lines: TranscriptLine[]
  divider: HandoffDivider
  handoffTime?: string
  agentTitle?: string
  agentLines?: TranscriptLine[]
  agentNote?: string
}) {
  const [open, setOpen] = useState(facts === "open")
  const factsOpen = facts === "toggle" ? open : facts === "open"
  const header = (
    <CallInfoHeader open={factsOpen} duration={duration} foldable={foldable} />
  )
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-background p-5">
      {facts === "toggle" ? (
        <button
          type="button"
          className="-mx-1 w-[calc(100%+8px)] rounded-md px-1 text-left hover:bg-muted/60"
          onClick={() => setOpen((value) => !value)}
        >
          {header}
        </button>
      ) : (
        header
      )}
      {factsOpen && <CallFacts duration={duration} />}
      <ConversationColumn
        bot={bot}
        lines={lines}
        divider={divider}
        handoffTime={handoffTime}
        agentTitle={agentTitle}
        agentLines={agentLines}
        agentNote={agentNote}
        flushTop={!factsOpen}
      />
    </section>
  )
}

function CallInfoHeader({
  open,
  duration,
  foldable,
}: {
  open: boolean
  duration: string
  foldable: boolean
}) {
  return (
    <div className="mb-3 flex shrink-0 items-center justify-between gap-2 border-b border-border pb-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <IconPhone size={16} className="text-muted-foreground" />
        通话信息
      </h3>
      {foldable && (
        <span className="flex min-w-0 items-center gap-2">
          {!open && (
            <span className="truncate text-xs text-muted-foreground">呼入 · 138 0013 8000 · {duration}</span>
          )}
          {open ? (
            <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
          ) : (
            <IconChevronRight size={16} className="shrink-0 text-muted-foreground" />
          )}
        </span>
      )}
    </div>
  )
}

function BarField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  )
}

function CallFacts({ duration }: { duration: string }) {
  return (
    <dl className="grid shrink-0 grid-cols-2 gap-y-2 text-sm">
      <Fact label="通话类型" value="呼入" />
      <Fact label="用户号码" value="138 0013 8000" />
      <Fact label="服务号码" value="400 820 8820" />
      <Fact label="通话时长" value={duration} />
      <Fact label="来电时间" value="19:21:02" />
      <Fact label="通话 ID" value="call_7b55bea8" mono />
    </dl>
  )
}

function Fact({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono text-xs" : ""}>{value}</dd>
    </>
  )
}

function CustomerColumn() {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-background p-5">
      <h3 className="mb-4 border-b border-border pb-2 text-sm font-semibold">客户信息</h3>
      <dl className="grid grid-cols-[88px_1fr] gap-y-3 text-sm">
        <dt className="text-muted-foreground">姓名</dt>
        <dd>王女士</dd>
        <dt className="text-muted-foreground">号码</dt>
        <dd className="font-mono text-xs">138 0013 8000</dd>
        <dt className="text-muted-foreground">标签</dt>
        <dd>VIP 客户</dd>
      </dl>
    </section>
  )
}

function SummaryColumn() {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-background">
      <div className="flex border-b border-border px-4">
        <span className="border-b-2 border-primary px-3 py-3 text-sm font-medium">通话纪要</span>
        <span className="px-3 py-3 text-sm text-muted-foreground">新建工单</span>
      </div>
      <div className="space-y-4 p-4">
        <div>
          <p className="text-xs text-muted-foreground">通话主题</p>
          <div className="mt-2 h-9 rounded-md border border-border" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">处理结果</p>
          <div className="mt-2 h-20 rounded-md border border-border" />
        </div>
      </div>
    </section>
  )
}
