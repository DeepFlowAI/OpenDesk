import type { ReactNode } from "react";
import {
  IconAddressBook,
  IconBook2,
  IconChevronDown,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconPhoneIncoming,
  IconSend,
  IconSettings,
  IconTicket,
} from "@tabler/icons-react";
import { CallStrip, type BarTone } from "./call-bar";
import { CALL } from "../fixtures";

const NAV = [
  { icon: IconTicket, active: false, label: "工单" },
  { icon: IconMessageCircle, active: false, label: "在线" },
  { icon: IconHeadset, active: true, label: "呼叫" },
  { icon: IconSend, active: false, label: "触达" },
  { icon: IconHistory, active: false, label: "历史" },
  { icon: IconAddressBook, active: false, label: "通讯录" },
  { icon: IconBook2, active: false, label: "知识库" },
];

function Rail({ activeLabel }: { activeLabel: string }) {
  return (
    <aside className="flex w-16 shrink-0 flex-col justify-between border-r border-border bg-muted/70 py-4">
      <nav className="flex flex-col items-center gap-2">
        {NAV.map((item) => (
          <span
            key={item.label}
            title={item.label}
            className={
              item.label === activeLabel
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
  );
}

function ScreenPop() {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-3 gap-4 p-4">
      {["通话信息", "客户信息", "通话纪要"].map((title) => (
        <section key={title} className="rounded-xl border border-border bg-background p-4">
          <h2 className="text-sm font-semibold">{title}</h2>
          <div className="mt-3 space-y-2 text-sm text-muted-foreground">
            {title === "通话信息" && (
              <>
                <p>呼出 · {CALL.number}</p>
                <p>时长 {CALL.duration}</p>
              </>
            )}
            {title === "客户信息" && (
              <>
                <p>{CALL.customerName}</p>
                <p>未关联更多资料</p>
              </>
            )}
            {title === "通话纪要" && <p>通话进行中，可在此记录要点。</p>}
          </div>
        </section>
      ))}
    </div>
  );
}

export function CallWorkspaceShell({
  callBar,
  tone = "active",
  children,
}: {
  callBar: ReactNode;
  tone?: BarTone;
  children?: ReactNode;
}) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <Rail activeLabel="呼叫" />
      <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-background">
        <div className="border-b border-border p-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            客服状态
          </div>
          <div className="mt-2 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span className="flex items-center gap-2 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-destructive" />
              忙碌
            </span>
            <span className="text-xs text-muted-foreground">通话中</span>
          </div>
          <div className="mt-2.5 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span>Web 电话</span>
            <IconChevronDown size={14} className="text-muted-foreground" />
          </div>
        </div>
        <div className="p-3">
          <div className="text-xs font-semibold text-foreground/70">最近通话（近 24 小时）</div>
          <div className="mt-2 rounded-lg bg-muted px-3 py-3">
            <div className="flex items-center gap-2">
              <IconPhoneIncoming size={15} className="text-muted-foreground" />
              <span className="font-mono text-[13px]">{CALL.number}</span>
            </div>
            <div className="mt-2 text-[11px] text-muted-foreground">通话中 · {CALL.duration}</div>
          </div>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <CallStrip tone={tone}>
          {callBar}
        </CallStrip>
        {children ?? <ScreenPop />}
      </main>
    </div>
  );
}

export function TicketsWorkspaceShell({ callBar }: { callBar: ReactNode }) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <Rail activeLabel="工单" />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="relative flex h-14 shrink-0 items-center justify-end border-b border-border px-6">
          <div className="absolute left-1/2 top-1/2 w-[min(760px,calc(100%-8rem))] -translate-x-1/2 -translate-y-1/2">
            {callBar}
          </div>
          <span className="grid h-8 w-8 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            客
          </span>
        </header>
        <div className="flex-1 bg-surface p-6">
          <div className="rounded-xl border border-border bg-background p-5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <IconTicket size={16} />
              工单工作台
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              通话仍在继续。顶栏沿用现网紧凑条，展开/收起改为 chevron，挂断改为红圆白图标。
            </p>
            <div className="mt-4 space-y-2">
              {["续费咨询 · 处理中", "发票抬头变更 · 待回复", "账号权限 · 已解决"].map((row) => (
                <div key={row} className="flex h-10 items-center rounded-md border border-border px-3 text-sm">
                  {row}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function CompareCanvas({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full flex-col bg-surface text-foreground">
      <div className="border-b border-border bg-background px-8 py-5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          通话控制台 · 视觉对照
        </div>
        <h1 className="mt-1 font-display text-xl font-bold tracking-tight">现状展开态 vs 提案单行图标</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          提案占用发起呼叫区同一条带。每个图标下方放一个词，发短信可见名为短信。
        </p>
      </div>
      <div className="flex-1 space-y-6 overflow-auto px-8 py-6">{children}</div>
    </div>
  );
}
