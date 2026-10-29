import type { ReactNode } from "react"
import { AGENT_NAME, type TranscriptLine } from "../fixtures"

const ROLE_LABEL = { user: "用户", bot: "机器人", agent: "坐席" } as const

export type BotSegment = "ready" | "loading" | "empty" | "failed" | "none"
export type HandoffDivider = "time" | "plain" | "none"

export function ConversationColumn({
  bot,
  lines,
  divider,
  handoffTime,
  agentTitle,
  agentLines,
  agentNote,
  flushTop = false,
}: {
  bot: BotSegment
  lines: TranscriptLine[]
  divider: HandoffDivider
  handoffTime?: string
  agentTitle?: string
  agentLines?: TranscriptLine[]
  agentNote?: string
  flushTop?: boolean
}) {
  return (
    <div
      className={
        flushTop
          ? "flex min-h-0 flex-1 flex-col pt-3"
          : "mt-4 flex min-h-0 flex-1 flex-col border-t border-border pt-4"
      }
    >
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
        {bot !== "none" && <BotSegmentView state={bot} lines={lines} />}
        {bot !== "none" && divider !== "none" && <HandoffLine mode={divider} time={handoffTime} />}
        {agentTitle && (
          <h4 className="shrink-0 text-xs font-semibold text-foreground/70">{agentTitle}</h4>
        )}
        {agentLines && agentLines.length > 0 && <Bubbles lines={agentLines} />}
        {agentNote && (
          <p className="flex min-h-16 items-center justify-center text-center text-xs text-muted-foreground">
            {agentNote}
          </p>
        )}
      </div>
    </div>
  )
}

function BotSegmentView({ state, lines }: { state: BotSegment; lines: TranscriptLine[] }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex shrink-0 items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold text-foreground/70">机器人对话</h4>
        {(state === "ready" || state === "empty") && (
          <span className="text-xs text-muted-foreground">由 {AGENT_NAME} 接待</span>
        )}
      </div>
      {state === "ready" && <Bubbles lines={lines} />}
      {state === "loading" && <SegmentNote>机器人对话加载中…</SegmentNote>}
      {state === "empty" && <SegmentNote>机器人阶段暂无对话</SegmentNote>}
      {state === "failed" && (
        <SegmentNote>
          机器人对话加载失败
          <span className="ml-2 text-xs text-primary">重试</span>
        </SegmentNote>
      )}
    </section>
  )
}

function SegmentNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex min-h-16 items-center justify-center text-center text-xs text-muted-foreground">
      {children}
    </p>
  )
}

function HandoffLine({ mode, time }: { mode: Exclude<HandoffDivider, "none">; time?: string }) {
  const label = mode === "time" && time ? `${time} 已转人工` : "已转人工"
  return (
    <div className="my-2 flex shrink-0 items-center gap-3">
      <div className="h-px flex-1 bg-border" />
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}

function Bubbles({ lines }: { lines: TranscriptLine[] }) {
  return (
    <div className="flex flex-col gap-2">
      {lines.map((line, index) => {
        const alignedEnd = line.role !== "user"
        return (
          <div key={index} className={`flex flex-col ${alignedEnd ? "items-end" : "items-start"}`}>
            <span className="mb-0.5 px-1 text-[10px] text-muted-foreground">{ROLE_LABEL[line.role]}</span>
            <div
              className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm ${bubbleClass(line.role)}`}
            >
              {line.text}
            </div>
            {line.interrupted && (
              <span className="mt-0.5 px-1 text-[10px] text-muted-foreground">已打断</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function bubbleClass(role: TranscriptLine["role"]) {
  if (role === "agent") return "rounded-br-sm bg-primary text-primary-foreground"
  if (role === "bot") return "rounded-br-sm border border-border bg-secondary text-foreground"
  return "rounded-bl-sm bg-muted text-foreground"
}
