import type { ReactNode } from "react";
import {
  IconBell,
  IconChartBar,
  IconChevronDown,
  IconHeadset,
  IconLayoutDashboard,
  IconListCheck,
  IconPhone,
  IconSettings,
  IconSpeakerphone,
  IconTicket,
  IconUsers,
  type Icon,
} from "@tabler/icons-react";

interface NavItem {
  label: string;
  icon: Icon;
  active?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: "工单工作台", icon: IconTicket },
  { label: "呼叫中心", icon: IconPhone },
  { label: "在线客服", icon: IconHeadset },
  { label: "任务中心", icon: IconListCheck },
  { label: "触达中心", icon: IconSpeakerphone, active: true },
  { label: "监控报表", icon: IconChartBar },
];

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-muted/60 p-4">
        <div className="flex h-12 items-center gap-3 px-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-foreground">
            <IconHeadset size={19} />
          </span>
          <div>
            <div className="font-display text-sm font-bold">OpenDesk</div>
            <div className="text-[10px] text-muted-foreground">客户服务平台</div>
          </div>
        </div>
        <nav className="mt-6 space-y-1">
          {NAV_ITEMS.map(({ label, icon: ItemIcon, active }) => (
            <div
              key={label}
              className={`flex h-10 items-center gap-3 rounded-lg px-3 text-sm ${active ? "bg-background font-semibold shadow-sm" : "text-muted-foreground"}`}
            >
              <ItemIcon size={18} stroke={1.8} />
              <span>{label}</span>
            </div>
          ))}
        </nav>
        <div className="mt-auto border-t border-border pt-3">
          <div className="flex h-10 items-center gap-3 rounded-lg px-3 text-sm text-muted-foreground">
            <IconSettings size={18} />
            <span>设置</span>
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-6">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <IconLayoutDashboard size={17} />
            <span>工作台</span>
            <span>/</span>
            <span className="text-foreground">触达中心</span>
          </div>
          <div className="flex items-center gap-4">
            <IconBell size={18} className="text-muted-foreground" />
            <div className="flex items-center gap-2 text-sm">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary font-semibold">李</span>
              <span>李婷</span>
              <IconChevronDown size={15} className="text-muted-foreground" />
            </div>
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
