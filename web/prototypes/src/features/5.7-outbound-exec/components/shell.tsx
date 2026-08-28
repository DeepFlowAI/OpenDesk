import type { ReactNode } from "react";
import {
  IconAddressBook,
  IconBook2,
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
  IconSparkles,
  IconTicket,
} from "@tabler/icons-react";
import { RECENT_CALLS } from "../fixtures";

const NAV_ITEMS = [
  { icon: IconTicket, active: false },
  { icon: IconMessageCircle, active: false },
  { icon: IconHeadset, active: true },
  { icon: IconSend, active: false },
  { icon: IconHistory, active: false },
  { icon: IconAddressBook, active: false },
  { icon: IconBook2, active: false },
];

function RecentCallsArea() {
  return (
    <div className="flex min-h-0 flex-1 flex-col p-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        最近通话（近 24 小时）
      </div>
      <div className="mt-3 flex-1 space-y-1 overflow-hidden">
        {RECENT_CALLS.map((call) => (
          <div key={call.id} className="flex items-center gap-2.5 rounded-md px-2 py-2">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
              {call.direction === "out" ? <IconPhoneOutgoing size={13} /> : <IconPhoneIncoming size={13} />}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm">{call.label}</span>
            <span className="shrink-0 text-[11px] text-muted-foreground">{call.time}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function IdleCallBar() {
  return (
    <div className="flex items-center gap-3 border-b border-border bg-background px-5 py-3.5">
      <div className="flex h-10 w-[220px] items-center rounded-lg border border-border px-3 text-sm text-muted-foreground">
        输入用户号码
      </div>
      <div className="flex h-10 w-[190px] items-center justify-between rounded-lg border border-border px-3 text-sm">
        <span>0755-8655 0123</span>
        <IconChevronDown size={14} className="text-muted-foreground" />
      </div>
      <span className="grid h-10 w-10 place-items-center rounded-full bg-success text-white">
        <IconPhone size={17} />
      </span>
      <span className="ml-auto text-xs text-muted-foreground">已就绪 · 等待来电</span>
    </div>
  );
}

export function OnCallBar() {
  return (
    <div className="flex items-center gap-3 border-b border-border bg-success/10 px-5 py-3.5">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-success text-white">
        <IconPhone size={17} />
      </span>
      <div className="min-w-0">
        <div className="text-sm font-semibold">通话中 · 呼出</div>
        <div className="text-xs text-muted-foreground">张伟 138****8888</div>
      </div>
      <span className="ml-3 font-mono text-sm text-muted-foreground">02:41</span>
      <span className="ml-auto grid h-10 w-10 place-items-center rounded-full bg-destructive text-white">
        <IconPhone size={17} className="rotate-[135deg]" />
      </span>
    </div>
  );
}

export function WrapUpCallBar() {
  return (
    <div className="flex items-center gap-3 border-b border-border bg-muted px-5 py-3.5">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-muted-foreground/20 text-muted-foreground">
        <IconPhone size={17} />
      </span>
      <div className="min-w-0">
        <div className="text-sm font-semibold">通话已结束，请整理本次记录</div>
        <div className="text-xs text-muted-foreground">张伟 138****8888 · 本次通话时长 05:32</div>
      </div>
      <span className="ml-auto inline-flex h-9 items-center rounded-lg border border-border bg-background px-4 text-sm font-medium">
        完成整理
      </span>
    </div>
  );
}

export function OutboundExecShell({
  callBar,
  children,
}: {
  callBar: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="flex w-16 shrink-0 flex-col justify-between border-r border-border bg-muted/70 py-4">
        <nav className="flex flex-col items-center gap-2">
          {NAV_ITEMS.map((item, index) => (
            <span
              key={index}
              className={
                item.active
                  ? "grid h-10 w-10 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm"
                  : "grid h-10 w-10 place-items-center rounded-xl text-muted-foreground"
              }
            >
              <item.icon size={18} />
            </span>
          ))}
        </nav>
        <div className="flex flex-col items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl text-muted-foreground">
            <IconSettings size={18} />
          </span>
          <span className="grid h-9 w-9 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            客
          </span>
        </div>
      </aside>

      <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-background">
        <div className="border-b border-border p-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            客服状态
          </div>
          <div className="mt-2 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span className="flex items-center gap-2 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-success" />
              就绪
            </span>
            <IconChevronDown size={14} className="text-muted-foreground" />
          </div>
          <div className="mt-2.5 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span>Web 电话</span>
            <IconChevronDown size={14} className="text-muted-foreground" />
          </div>
          <div className="mt-3 flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm">
            <IconClipboardList size={16} />
            我的外呼任务
          </div>
          <div className="mt-2 flex h-9 items-center gap-2 rounded-md px-3 text-sm text-muted-foreground">
            <IconSparkles size={16} />
            个人自动外呼
          </div>
        </div>
        <RecentCallsArea />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        {callBar}
        {children}
      </main>
    </div>
  );
}
