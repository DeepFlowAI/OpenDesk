import type { ReactNode } from "react";
import {
  IconAddressBook,
  IconBook2,
  IconCheck,
  IconChevronDown,
  IconGridDots,
  IconHeadset,
  IconHistory,
  IconMessage,
  IconMessageCircle,
  IconMicrophone,
  IconPhone,
  IconPhoneCall,
  IconPhoneIncoming,
  IconPhoneOff,
  IconPhoneOutgoing,
  IconPlayerPause,
  IconSend,
  IconSettings,
  IconTicket,
  IconArrowsExchange,
} from "@tabler/icons-react";

const PRIMARY_NAV = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle },
  { label: "呼叫", icon: IconPhone, active: true },
  { label: "触达", icon: IconSend },
  { label: "历史", icon: IconHistory },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
];

const RECENT_CALLS = [
  { phone: "13800138000", when: "3 分钟前", direction: "in" as const },
  { phone: "18682311976", when: "18 分钟前", direction: "out" as const },
  { phone: "13967425208", when: "1 小时前", direction: "in" as const },
];

export function CallShell({
  children,
  phase = "idle",
  dialNumber = "13800138000",
  showSendButton = true,
}: {
  children?: ReactNode;
  phase?: "idle" | "on_call";
  dialNumber?: string;
  showSendButton?: boolean;
}) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="relative z-30 flex w-16 shrink-0 flex-col justify-between border-r border-[#E5E5E5] bg-[#F5F5F5] py-4">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-full items-center justify-center">
            <IconHeadset size={28} className="text-[#1a1a1a]" />
          </div>
          <nav className="flex w-full flex-col items-center gap-1">
            {PRIMARY_NAV.map(({ label, icon: ItemIcon, active }) => (
              <div
                key={label}
                className={`flex h-11 w-11 items-center justify-center rounded-lg ${active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"}`}
              >
                <ItemIcon size={20} stroke={1.7} />
              </div>
            ))}
          </nav>
        </div>
        <div className="flex flex-col items-center gap-2">
          <div className="grid h-10 w-10 place-items-center rounded-lg text-muted-foreground">
            <IconSettings size={20} />
          </div>
          <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">张</span>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 overflow-hidden">
        <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-background">
          <div className="border-b border-border p-4">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">客服状态</div>
            <div className="mt-2 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
              <span className="flex items-center gap-2 font-medium">
                <span className={`h-2.5 w-2.5 rounded-full ${phase === "on_call" ? "bg-red-500" : "bg-emerald-500"}`} />
                {phase === "on_call" ? "忙碌" : "就绪"}
              </span>
              <IconChevronDown size={14} className="text-muted-foreground" />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {phase === "on_call" ? "通话中 · WebRTC" : "已就绪 · 等待来电"}
            </p>
          </div>
          <div className="flex min-h-0 flex-1 flex-col px-2 py-2">
            <h3 className="px-2 text-xs font-semibold text-foreground/70">最近通话（近 24 小时）</h3>
            <div className="mt-1 min-h-0 flex-1 space-y-1 overflow-y-auto">
              {RECENT_CALLS.map((call, index) => {
                const active = phase === "on_call" && index === 0;
                const DirIcon = call.direction === "in" ? IconPhoneIncoming : IconPhoneOutgoing;
                return (
                  <div
                    key={call.phone + call.when}
                    className={`flex items-center justify-between rounded-lg px-3 py-2.5 ${active ? "bg-muted" : ""}`}
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <DirIcon size={15} className="text-muted-foreground" />
                      <span className="font-mono text-[13px]">{call.phone}</span>
                      {active && <IconCheck size={13} className="text-emerald-600" />}
                    </div>
                    <span className="text-[11px] text-muted-foreground">{call.when}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-muted/30">
          {phase === "idle" ? (
            <div className="flex shrink-0 items-center justify-between border-b border-border bg-background px-5 py-[18px]">
              <div className="text-sm text-muted-foreground">拨号</div>
              <div className="flex items-center gap-2">
                <div className="flex h-10 w-[220px] items-center justify-between rounded-lg border border-border px-3 text-sm shadow-sm">
                  <span className="font-mono font-medium">{dialNumber}</span>
                  <IconGridDots size={16} className="text-muted-foreground" />
                </div>
                {showSendButton && (
                  <button
                    className="grid h-10 w-10 place-items-center rounded-lg border border-border bg-background text-foreground"
                    title="发短信"
                    aria-label="发短信"
                  >
                    <IconMessage size={18} />
                  </button>
                )}
                <button className="grid h-10 w-10 place-items-center rounded-full bg-emerald-600 text-white">
                  <IconPhone size={18} />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex shrink-0 items-center gap-6 border-b-2 border-green-200 bg-green-50 px-5 py-[18px]">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-green-100">
                  <IconPhoneCall size={16} className="text-green-700" />
                </span>
                <span className="font-bold text-green-800">通话中</span>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">用户号码</div>
                <div className="mt-0.5 text-sm font-semibold">13800138000</div>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">服务号码</div>
                <div className="mt-0.5 text-sm">0755-86550123</div>
              </div>
              <div>
                <div className="text-[11px] text-muted-foreground">通话时长</div>
                <div className="mt-0.5 text-sm font-semibold text-green-700">01:42</div>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <button className="grid h-8 w-8 place-items-center rounded-md text-foreground/80" title="静音">
                  <IconMicrophone size={16} />
                </button>
                <button className="grid h-8 w-8 place-items-center rounded-md text-foreground/80" title="保持">
                  <IconPlayerPause size={16} />
                </button>
                <button className="inline-flex h-8 items-center gap-1 rounded-md border border-border bg-background/60 px-2 text-xs">
                  <IconArrowsExchange size={14} />
                  转接
                </button>
                {showSendButton && (
                  <button
                    className="grid h-8 w-8 place-items-center rounded-md border border-border bg-background/60 text-foreground/80"
                    title="发短信"
                    aria-label="发短信"
                  >
                    <IconMessage size={16} />
                  </button>
                )}
                <button className="grid h-9 w-9 place-items-center rounded-full bg-red-500 text-white" title="挂断">
                  <IconPhoneOff size={16} />
                </button>
              </div>
            </div>
          )}
          <div className="relative min-h-0 flex-1 overflow-hidden">{children}</div>
        </div>
      </div>
    </div>
  );
}
