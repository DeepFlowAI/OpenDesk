import type { ReactNode } from "react"
import {
  agentConversation,
  botConversation,
  HANDOFF_TIME,
  unrecordedInterrupt,
} from "./fixtures"
import { FoldableLiveWorkspace, HistoryWorkspace, LiveWorkspace } from "./components/workspace"

interface PrototypeScreen {
  id: string
  title: string
  description: string
  render: () => ReactNode
}

function Frame({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div className="prototype-frame relative">
      {children}
      <div className="pointer-events-none absolute bottom-4 left-4 z-50 rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">
        {id} · 1440×900
      </div>
    </div>
  )
}

export const BotHandoffTranscriptScreens: PrototypeScreen[] = [
  {
    id: "bot-handoff-transcript/ringing",
    title: "转人工 · 响铃弹屏",
    description: "派单响起时左栏展示机器人对话。开场白和一条回复只保留客户已听到的部分并标「已打断」；播报开始前被打断的回复不出现。",
    render: () => (
      <Frame id="bot-handoff-transcript/ringing">
        <LiveWorkspace
          presence="ringing"
          bar="ringing"
          bot="ready"
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/on-call",
    title: "转人工 · 通话中",
    description: "机器人段之下是「已转人工」分隔线，再接人工阶段的实时对话。",
    render: () => (
      <Frame id="bot-handoff-transcript/on-call">
        <LiveWorkspace
          presence="on-call"
          bar="on-call"
          duration="00:42"
          bot="ready"
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
          agentTitle="实时对话"
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/interrupt-unrecorded",
    title: "转人工 · 未记录打断位置",
    description: "被打断但没有已听到内容时，展示完整回复，并在气泡下方标「已打断」。",
    render: () => (
      <Frame id="bot-handoff-transcript/interrupt-unrecorded">
        <LiveWorkspace
          presence="ringing"
          bar="ringing"
          bot="ready"
          lines={unrecordedInterrupt}
          divider="time"
          handoffTime={HANDOFF_TIME}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/loading",
    title: "转人工 · 机器人对话加载中",
    description: "响铃时机器人段内显示加载文案，不阻塞接听和拒接。",
    render: () => (
      <Frame id="bot-handoff-transcript/loading">
        <LiveWorkspace presence="ringing" bar="ringing" bot="loading" lines={[]} divider="none" />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/empty",
    title: "转人工 · 机器人阶段暂无对话",
    description: "没有可展示的消息时，机器人段显示空状态，分隔线仍标出转人工时间。",
    render: () => (
      <Frame id="bot-handoff-transcript/empty">
        <LiveWorkspace
          presence="ringing"
          bar="ringing"
          bot="empty"
          lines={[]}
          divider="time"
          handoffTime={HANDOFF_TIME}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/load-failed",
    title: "转人工 · 加载失败",
    description: "VoiceSpeed 超时或不可用时，机器人段内提示失败并给出重试，接听不受影响。",
    render: () => (
      <Frame id="bot-handoff-transcript/load-failed">
        <LiveWorkspace presence="ringing" bar="ringing" bot="failed" lines={[]} divider="none" />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/transcription-off",
    title: "转人工 · 未开启实时转写",
    description: "实时转写关闭时机器人段照常显示，分隔线之后沿用「暂未开启转写」。",
    render: () => (
      <Frame id="bot-handoff-transcript/transcription-off">
        <LiveWorkspace
          presence="on-call"
          bar="on-call"
          duration="00:42"
          bot="ready"
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
          agentTitle="实时对话"
          agentNote="暂未开启转写"
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/handoff-without-time",
    title: "转人工 · 无转人工时间",
    description: "没有返回转人工时间、但通话已进入人工派单时，分隔线只写「已转人工」。",
    render: () => (
      <Frame id="bot-handoff-transcript/handoff-without-time">
        <LiveWorkspace
          presence="on-call"
          bar="on-call"
          duration="00:42"
          bot="ready"
          lines={botConversation}
          divider="plain"
          agentTitle="实时对话"
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/history",
    title: "转人工 · 历史详情",
    description: "工作台最近通话详情中，机器人段、分隔线和人工阶段对话记录上下衔接。",
    render: () => (
      <Frame id="bot-handoff-transcript/history">
        <HistoryWorkspace
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/history-bot-only",
    title: "转人工 · 仅机器人接待的历史",
    description: "机器人全程接待、未进入人工时不显示分隔线，人工阶段对话记录为空。",
    render: () => (
      <Frame id="bot-handoff-transcript/history-bot-only">
        <HistoryWorkspace
          botOnly
          lines={botConversation.slice(0, 3)}
          divider="none"
          agentNote="暂无对话记录"
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/facts-collapsed",
    title: "通话信息 · 整理中默认折叠",
    description: "有机器人对话时，左栏字段默认收起，标题行右侧留一行摘要。对话区占满剩余高度。",
    render: () => (
      <Frame id="bot-handoff-transcript/facts-collapsed">
        <LiveWorkspace
          presence="wrap-up"
          bar="wrap-up"
          duration="00:44"
          facts="collapsed"
          bot="ready"
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
          agentTitle="对话记录"
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/facts-expanded",
    title: "通话信息 · 整理中展开字段",
    description: "点开标题后恢复现有六行字段。顶栏已有时长，字段本身仍可核对号码和通话 ID。",
    render: () => (
      <Frame id="bot-handoff-transcript/facts-expanded">
        <LiveWorkspace
          presence="wrap-up"
          bar="wrap-up"
          duration="00:44"
          facts="open"
          foldable
          bot="ready"
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
          agentTitle="对话记录"
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/on-call-facts-collapsed",
    title: "通话信息 · 通话中折叠",
    description: "实时对话在下、机器人段在上时，同样默认折叠通话字段，把高度让给气泡。",
    render: () => (
      <Frame id="bot-handoff-transcript/on-call-facts-collapsed">
        <LiveWorkspace
          presence="on-call"
          bar="on-call"
          duration="00:42"
          facts="collapsed"
          bot="ready"
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
          agentTitle="实时对话"
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/live-only-facts-collapsed",
    title: "通话信息 · 仅实时转写折叠",
    description: "没有机器人段、只有实时语音转写时，通话字段同样默认折叠。",
    render: () => (
      <Frame id="bot-handoff-transcript/live-only-facts-collapsed">
        <LiveWorkspace
          presence="on-call"
          bar="on-call"
          duration="00:42"
          facts="collapsed"
          bot="none"
          lines={[]}
          divider="none"
          agentTitle="实时对话"
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
  {
    id: "bot-handoff-transcript/facts-toggle",
    title: "通话信息 · 点击折叠",
    description: "评审用交互稿。点「通话信息」标题行可展开或收起字段，默认收起。",
    render: () => (
      <Frame id="bot-handoff-transcript/facts-toggle">
        <FoldableLiveWorkspace
          presence="wrap-up"
          bar="wrap-up"
          duration="00:44"
          bot="ready"
          lines={botConversation}
          divider="time"
          handoffTime={HANDOFF_TIME}
          agentTitle="对话记录"
          agentLines={agentConversation}
        />
      </Frame>
    ),
  },
]
