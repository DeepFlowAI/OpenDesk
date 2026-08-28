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
  IconSend,
  IconSettings,
  IconSparkles,
  IconTicket,
} from "@tabler/icons-react";

const NAV_ITEMS = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle },
  { label: "呼叫", icon: IconPhone, active: true },
  { label: "触达", icon: IconSend },
  { label: "历史", icon: IconHistory },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
];

export function PersonalOutboundWorkspaceShell({
  children,
  agentState = "就绪",
  callBar,
}: {
  children: ReactNode;
  agentState?: "就绪" | "忙碌";
  callBar?: ReactNode;
}) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="flex w-16 shrink-0 flex-col justify-between border-r border-border bg-muted/70 py-4">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-full items-center justify-center"><IconHeadset size={28} /></div>
          <nav className="flex w-full flex-col items-center gap-1">
            {NAV_ITEMS.map(({ label, icon: ItemIcon, active }) => (
              <div key={label} title={label} className={`grid h-11 w-11 place-items-center rounded-lg ${active ? "bg-background shadow-sm" : "text-muted-foreground"}`}>
                <ItemIcon size={20} stroke={1.7} />
              </div>
            ))}
          </nav>
        </div>
        <div className="flex flex-col items-center gap-2">
          <div className="grid h-10 w-10 place-items-center text-muted-foreground"><IconSettings size={20} /></div>
          <div className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">张</div>
        </div>
      </aside>

      <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-background">
        <div className="border-b border-border p-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">客服状态</div>
          <div className="mt-2 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span className="flex items-center gap-2 font-medium">
              <span className={`h-2.5 w-2.5 rounded-full ${agentState === "忙碌" ? "bg-destructive" : "bg-success"}`} />
              {agentState}
            </span>
            <IconChevronDown size={14} className="text-muted-foreground" />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{agentState === "忙碌" ? "个人自动外呼 · 通话中" : "Web 电话在线 · 可自动接入"}</p>
          <div className="mt-3 flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span>Web 电话</span><IconChevronDown size={14} className="text-muted-foreground" />
          </div>
        </div>
        <div className="p-3">
          <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">我的外呼</div>
          <div className="flex h-10 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground"><IconClipboardList size={17} />我的外呼对象</div>
          <div className="flex h-10 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm"><IconSparkles size={17} />个人自动外呼</div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-surface">
        {callBar}
        {children}
      </main>
    </div>
  );
}
