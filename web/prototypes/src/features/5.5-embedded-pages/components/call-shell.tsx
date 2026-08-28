import type { ReactNode } from "react";
import {
  IconAddressBook,
  IconBook2,
  IconCheck,
  IconChevronDown,
  IconClipboardList,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconPhone,
  IconPhoneIncoming,
  IconPhoneOutgoing,
  IconSend,
  IconSettings,
  IconTicket,
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
  { phone: "138 0013 8000", when: "3 分钟前", direction: "in" as const },
  { phone: "186 8231 1976", when: "18 分钟前", direction: "out" as const },
  { phone: "139 6742 5208", when: "1 小时前", direction: "in" as const },
  { phone: "177 3058 6214", when: "昨天", direction: "out" as const },
];

/**
 * Mirrors production call workspace:
 * 64px icon nav → left 280px status/device/recent calls → right call bar + aux area.
 * See `web/app/workspace/call/page.tsx`.
 */
export function CallShell({
  children,
  phase = "on_call",
}: {
  children: ReactNode;
  phase?: "idle" | "on_call" | "wrap_up";
}) {
  const statusHint =
    phase === "on_call"
      ? "通话中 · WebRTC"
      : phase === "wrap_up"
        ? "整理中 · 完成本次记录后恢复就绪"
        : "已就绪 · 等待来电";

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
          <div className="grid h-10 w-10 place-items-center rounded-lg text-muted-foreground"><IconSettings size={20} /></div>
          <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">张</span>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 overflow-hidden">
        <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-background">
          <div className="border-b border-border p-4">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">客服状态</div>
            <div className="mt-2 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
              <span className="flex items-center gap-2 font-medium">
                <span className={`h-2.5 w-2.5 rounded-full ${phase === "wrap_up" ? "bg-amber-500" : phase === "on_call" ? "bg-red-500" : "bg-emerald-500"}`} />
                {phase === "wrap_up" ? "整理中" : phase === "on_call" ? "忙碌" : "就绪"}
              </span>
              <IconChevronDown size={14} className="text-muted-foreground" />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{statusHint}</p>
            <div className="mt-3 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
              <span>Web 电话</span>
              <IconChevronDown size={14} className="text-muted-foreground" />
            </div>
            <div className="mt-3 flex h-9 items-center justify-center gap-2 rounded-md border border-border text-sm text-muted-foreground">
              <IconClipboardList size={16} />
              我的外呼对象
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col px-2 py-2">
            <h3 className="px-2 text-xs font-semibold text-foreground/70">最近通话（近 24 小时）</h3>
            <div className="mt-1 min-h-0 flex-1 space-y-1 overflow-y-auto">
              {RECENT_CALLS.map((call, index) => {
                const active = phase !== "idle" && index === 0;
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
          {children}
        </div>
      </div>
    </div>
  );
}
