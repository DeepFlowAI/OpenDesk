import type { ReactNode } from "react";
import {
  IconBell,
  IconChartBar,
  IconChevronDown,
  IconHeadset,
  IconListCheck,
  IconPhone,
  IconSearch,
  IconSettings,
  IconSpeakerphone,
  IconTicket,
} from "@tabler/icons-react";

const NAV_ITEMS = [
  { label: "工单", icon: IconTicket },
  { label: "呼叫", icon: IconPhone, active: true },
  { label: "在线", icon: IconHeadset },
  { label: "任务", icon: IconListCheck },
  { label: "触达", icon: IconSpeakerphone },
  { label: "报表", icon: IconChartBar },
];

export function AgentShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="flex w-[76px] shrink-0 flex-col items-center border-r border-border bg-muted/60 py-4">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground"><IconHeadset size={20} /></span>
        <nav className="mt-5 space-y-2">
          {NAV_ITEMS.map(({ label, icon: ItemIcon, active }) => (
            <div key={label} className={`flex h-12 w-12 flex-col items-center justify-center gap-0.5 rounded-lg text-[10px] ${active ? "bg-background font-semibold shadow-sm" : "text-muted-foreground"}`}><ItemIcon size={18} /><span>{label}</span></div>
          ))}
        </nav>
        <div className="mt-auto grid h-10 w-10 place-items-center rounded-lg text-muted-foreground"><IconSettings size={19} /></div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
          <div><h1 className="font-display text-sm font-semibold">呼叫中心工作台</h1><p className="text-[10px] text-muted-foreground">Call workspace</p></div>
          <div className="flex items-center gap-4"><IconSearch size={18} className="text-muted-foreground" /><IconBell size={18} className="text-muted-foreground" /><div className="flex items-center gap-2 text-sm"><span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">张</span><span>张琪</span><IconChevronDown size={14} /></div></div>
        </header>
        <div className="flex h-[74px] shrink-0 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-6">
            <div><div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">客服状态</div><div className="mt-1.5 flex items-center gap-2 text-sm font-medium"><span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />就绪<IconChevronDown size={14} /></div></div>
            <div className="h-9 w-px bg-border" />
            <div><div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">当前设备</div><div className="mt-1.5 text-sm font-medium">Web 电话</div></div>
          </div>
          <div className="flex items-center gap-2"><div className="flex h-10 w-[260px] items-center justify-between rounded-lg border border-border px-3 text-sm"><span>138 0013 8000</span><span className="text-xs text-muted-foreground">拨号盘</span></div><button className="grid h-10 w-10 place-items-center rounded-full bg-emerald-600 text-white"><IconPhone size={18} /></button></div>
        </div>
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
