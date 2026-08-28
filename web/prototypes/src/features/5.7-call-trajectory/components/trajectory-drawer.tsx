import type { ReactNode } from "react"
import {
  IconAlertTriangle,
  IconArrowsExchange,
  IconCheck,
  IconChevronDown,
  IconClock,
  IconCode,
  IconFileDescription,
  IconHeadset,
  IconListDetails,
  IconPhone,
  IconPlayerPause,
  IconRefresh,
  IconRobot,
  IconRoute,
  IconShieldCheck,
  IconUser,
  IconUsers,
  IconX,
} from "@tabler/icons-react"
import { TECHNICAL_TRANSFER_STEPS } from "../fixtures"

type TrajectoryMode = "business" | "technical"

function DrawerHeader() {
  return (
    <>
      <header className="flex h-[62px] shrink-0 items-center justify-between border-b border-border px-6">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold">通话详情</h2>
          <span className="rounded-md bg-muted px-2 py-1 font-mono text-[11px] text-muted-foreground">call_01JQ8F2A9K7P</span>
          <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700">客服接通</span>
        </div>
        <div className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground">
          <IconX size={18} />
        </div>
      </header>

      <nav className="flex h-12 shrink-0 items-end gap-7 border-b border-border px-6 text-sm">
        <div className="flex h-full items-center text-muted-foreground">概览</div>
        <div className="flex h-full items-center border-b-2 border-foreground font-semibold text-foreground">通话轨迹</div>
      </nav>
    </>
  )
}

function Toolbar({ mode }: { mode: TrajectoryMode }) {
  return (
    <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-3">
      <div className="flex items-center gap-2">
        <div className="flex h-8 items-center rounded-md bg-muted p-0.5 text-xs">
          <div className={`flex h-7 items-center gap-1.5 rounded px-2.5 ${mode === "business" ? "bg-background font-medium shadow-sm" : "text-muted-foreground"}`}>
            <IconListDetails size={14} />业务轨迹
          </div>
          <div className={`flex h-7 items-center gap-1.5 rounded px-2.5 ${mode === "technical" ? "bg-background font-medium shadow-sm" : "text-muted-foreground"}`}>
            <IconCode size={14} />技术详情
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>已结束 · 轨迹已校准</span>
        <span className="flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-foreground"><IconRefresh size={13} />刷新</span>
      </div>
    </div>
  )
}

type EventTone = "neutral" | "bot" | "queue" | "success" | "warning" | "danger"

const EVENT_TONE: Record<EventTone, string> = {
  neutral: "bg-neutral-100 text-neutral-700 ring-neutral-200",
  bot: "bg-violet-50 text-violet-700 ring-violet-200",
  queue: "bg-amber-50 text-amber-700 ring-amber-200",
  success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  warning: "bg-orange-50 text-orange-700 ring-orange-200",
  danger: "bg-red-50 text-red-700 ring-red-200",
}

function TimelineEvent({
  time,
  icon,
  title,
  description,
  tone = "neutral",
  last,
  children,
}: {
  time: string
  icon: ReactNode
  title: string
  description: string
  tone?: EventTone
  last?: boolean
  children?: ReactNode
}) {
  return (
    <div className="grid grid-cols-[72px_28px_minmax(0,1fr)] gap-3">
      <time className="pt-1.5 text-right font-mono text-[10px] text-muted-foreground">{time}</time>
      <div className="relative flex justify-center">
        {!last && <div className="absolute bottom-0 top-7 w-px bg-border" />}
        <div className={`relative z-10 grid h-7 w-7 place-items-center rounded-full ring-1 ${EVENT_TONE[tone]}`}>{icon}</div>
      </div>
      <div className="min-w-0 pb-4">
        <div className="pt-1 text-xs font-semibold">{title}</div>
        <div className="mt-1 text-[11px] leading-4 text-muted-foreground">{description}</div>
        {children}
      </div>
    </div>
  )
}

function OperationCard({
  badge,
  title,
  meta,
  children,
}: {
  badge: string
  title: string
  meta: string
  children?: ReactNode
}) {
  return (
    <div className="mt-2 overflow-hidden rounded-lg border border-border bg-background shadow-sm">
      <div className="flex items-center justify-between gap-3 px-3 py-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-700">{badge}</span>
            <span className="truncate text-xs font-medium">{title}</span>
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground">{meta}</div>
        </div>
        <IconChevronDown size={15} className="shrink-0 text-muted-foreground" />
      </div>
      {children}
    </div>
  )
}

function BusinessTimeline() {
  return (
    <div className="mx-auto max-w-[920px] px-7 py-4">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">完整通话历史</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">2026-08-09 · 共 31 个事件，已聚合为 9 个业务节点</p>
        </div>
        <span className="text-[11px] text-muted-foreground">全部展开</span>
      </div>

      <TimelineEvent time="09:32:04" icon={<IconPhone size={14} />} title="收到客户呼入" description="用户 138 **** 7621 呼入服务号码 400 800 1001" />
      <TimelineEvent time="09:32:05" icon={<IconRoute size={14} />} title="进入 IVR" description="售后服务热线 · 选择“技术问题”分支" />
      <TimelineEvent time="09:32:21" icon={<IconRobot size={14} />} title="机器人开始接待" description="机器人“小深”识别为设备故障，46 秒后请求转人工" tone="bot" />
      <TimelineEvent time="09:33:07" icon={<IconUsers size={14} />} title="进入技术支持组" description="等待 39 秒 · 王小明接受第 2 次坐席呼叫" tone="queue">
        <OperationCard badge="已接通" title="2 次坐席呼叫" meta="刘安超时 15 秒 · 王小明接受 8 秒" />
      </TimelineEvent>
      <TimelineEvent time="09:33:46" icon={<IconHeadset size={14} />} title="王小明开始接待" description="Web 话机 · 技术支持组 · 首次人工接通" tone="success" />
      <TimelineEvent time="09:35:18" icon={<IconArrowsExchange size={14} />} title="直接转接" description="王小明发起，转接至高级技术组客服李小华" tone="success">
        <OperationCard badge="转接成功" title="王小明 → 李小华" meta="目标振铃 10.8 秒 · 总耗时 12.6 秒" />
      </TimelineEvent>
      <TimelineEvent time="09:39:42" icon={<IconPlayerPause size={14} />} title="客户保持" description="李小华发起，23 秒后恢复通话" tone="warning" />
      <TimelineEvent time="09:40:18" icon={<IconCheck size={14} />} title="通话正常结束" description="客户挂断 · 人工通话阶段 · 总时长 08:14" tone="success" last>
        <div className="mt-2 grid grid-cols-4 gap-2 rounded-lg border border-border bg-muted/20 p-3 text-[10px]">
          <div><span className="text-muted-foreground">通话结果</span><div className="mt-1 font-medium">客服接通</div></div>
          <div><span className="text-muted-foreground">结束方</span><div className="mt-1 font-medium">客户</div></div>
          <div><span className="text-muted-foreground">结束阶段</span><div className="mt-1 font-medium">人工通话</div></div>
          <div><span className="text-muted-foreground">人工通话</span><div className="mt-1 font-mono font-medium">06:30</div></div>
        </div>
      </TimelineEvent>
    </div>
  )
}

function TechnicalTimeline() {
  return (
    <div className="mx-auto max-w-[920px] px-7 py-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">技术事件详情</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">原始事件按 occurred_at 与 sequence_no 稳定排序</p>
        </div>
        <span className="rounded-md bg-neutral-950 px-2 py-1 font-mono text-[9px] text-neutral-300">31 EVENTS · v1</span>
      </div>

      <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2 text-[10px] text-amber-800">
        <div className="flex items-center gap-2 font-medium"><IconAlertTriangle size={13} />当前展示底层事件与媒体腿，仅用于排障</div>
      </div>

      <TimelineEvent time="09:33:07.108" icon={<IconUsers size={14} />} title="queue_entered" description="技术支持组 · employee_group #12 · reason=bot_handoff" tone="queue" />
      <TimelineEvent time="09:33:07.421" icon={<IconUser size={14} />} title="agent_offer_started" description="刘安 · Offer ofr_619D · WebRTC · source=opendesk" />
      <TimelineEvent time="09:33:22.440" icon={<IconClock size={14} />} title="agent_offer_timeout" description="刘安未接 · duration=15019ms · reason=agent_no_answer" tone="warning" />
      <TimelineEvent time="09:33:37.612" icon={<IconShieldCheck size={14} />} title="agent_bridge_succeeded" description="customer leg_01AF ↔ agent leg_3D91 · source=flowkit" tone="success" />
      <TimelineEvent time="09:35:18.420" icon={<IconArrowsExchange size={14} />} title="transfer_started" description="operation trf_E182 · actor 王小明 · target 李小华" tone="success">
        <OperationCard badge="7 / 7 成功" title="直接转接 · trf_E182" meta="opendesk + flowkit · 总耗时 12.586 秒">
          <div className="border-t border-border bg-muted/20 px-3 py-2.5">
            {TECHNICAL_TRANSFER_STEPS.map((step, index) => (
              <div key={step.time} className="grid grid-cols-[84px_14px_minmax(0,1fr)] gap-2 py-1.5 text-[9px]">
                <span className="font-mono text-muted-foreground">{step.time}</span>
                <span className={`mt-0.5 grid h-3.5 w-3.5 place-items-center rounded-full ${step.state === "success" ? "bg-emerald-600 text-white" : "bg-emerald-100 text-emerald-700"}`}><IconCheck size={9} /></span>
                <div className="min-w-0"><span className="font-medium">{step.title}</span><span className="ml-2 text-muted-foreground">{step.detail}</span></div>
              </div>
            ))}
          </div>
        </OperationCard>
      </TimelineEvent>
      <TimelineEvent time="09:35:31.006" icon={<IconUser size={14} />} title="reception_started" description="李小华 · 高级技术组 · entry_reason=transfer_in" tone="success" />
      <TimelineEvent time="09:40:18.002" icon={<IconFileDescription size={14} />} title="trajectory_reconciled" description="31 events · 5 phases · 2 reception segments · no gap" last />
    </div>
  )
}

export function TrajectoryDrawer({ mode }: { mode: TrajectoryMode }) {
  return (
    <div className="absolute inset-0 z-20 flex justify-end bg-black/35">
      <section className="flex h-full w-[1120px] flex-col bg-background shadow-2xl">
        <DrawerHeader />
        <Toolbar mode={mode} />
        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          {mode === "business" ? <BusinessTimeline /> : <TechnicalTimeline />}
        </main>
      </section>
    </div>
  )
}
