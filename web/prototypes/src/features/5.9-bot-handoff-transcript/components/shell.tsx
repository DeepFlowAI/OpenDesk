import type { ReactNode } from "react"
import {
  IconAddressBook,
  IconBook2,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconPhone,
  IconPhoneIncoming,
  IconSend,
  IconSettings,
  IconTicket,
} from "@tabler/icons-react"

const NAV = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle },
  { label: "呼叫", icon: IconPhone, active: true },
  { label: "触达", icon: IconSend },
  { label: "历史", icon: IconHistory },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
]

export type AgentPresence = "ringing" | "on-call" | "wrap-up" | "idle"

const PRESENCE: Record<AgentPresence, { label: string; hint: string; dot: string }> = {
  ringing: { label: "就绪", hint: "响铃中 · Web 电话", dot: "bg-emerald-500" },
  "on-call": { label: "忙碌", hint: "通话中 · Web 电话", dot: "bg-red-500" },
  "wrap-up": { label: "整理中", hint: "整理中 · 完成本次记录后恢复就绪", dot: "bg-amber-500" },
  idle: { label: "就绪", hint: "空闲 · Web 电话", dot: "bg-emerald-500" },
}

export function CallWorkspaceShell({
  presence,
  selectedHistory = false,
  children,
}: {
  presence: AgentPresence
  selectedHistory?: boolean
  children: ReactNode
}) {
  const status = PRESENCE[presence]
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="flex w-16 shrink-0 flex-col justify-between border-r border-border bg-muted py-4">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-full items-center justify-center">
            <IconHeadset size={28} />
          </div>
          <nav className="flex w-full flex-col items-center gap-1">
            {NAV.map(({ label, icon: ItemIcon, active }) => (
              <div
                key={label}
                title={label}
                className={`grid h-11 w-11 place-items-center rounded-lg ${active ? "bg-background shadow-sm" : "text-muted-foreground"}`}
              >
                <ItemIcon size={20} />
              </div>
            ))}
          </nav>
        </div>
        <div className="flex flex-col items-center gap-2">
          <IconSettings size={20} className="text-muted-foreground" />
          <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">张</span>
        </div>
      </aside>

      <aside className="flex w-[260px] shrink-0 flex-col border-r border-border bg-background">
        <div className="border-b border-border p-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">客服状态</div>
          <div className="mt-2 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span className="flex items-center gap-2 font-medium">
              <span className={`h-2.5 w-2.5 rounded-full ${status.dot}`} />
              {status.label}
            </span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{status.hint}</p>
          <div className="mt-3 flex h-9 items-center rounded-md border border-border px-3 text-sm">Web 电话</div>
        </div>
        <div className="p-3">
          <h3 className="px-2 text-xs font-semibold text-foreground/70">最近通话（近 24 小时）</h3>
          <RecentCall phone="138 0013 8000" meta="王女士 · 刚刚" active={!selectedHistory && presence !== "idle"} />
          <RecentCall phone="186 8231 1976" meta="1 小时前" active={selectedHistory} />
          <RecentCall phone="139 6742 5208" meta="3 小时前" />
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-muted">{children}</main>
    </div>
  )
}

function RecentCall({ phone, meta, active = false }: { phone: string; meta: string; active?: boolean }) {
  return (
    <div className={`mt-2 rounded-lg px-3 py-3 ${active ? "bg-muted" : ""}`}>
      <div className="flex items-center gap-2">
        <IconPhoneIncoming size={15} className="text-muted-foreground" />
        <span className="font-mono text-[13px]">{phone}</span>
      </div>
      <div className="mt-1 pl-[23px] text-[11px] text-muted-foreground">{meta}</div>
    </div>
  )
}
