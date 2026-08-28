import type { ReactNode } from "react";
import {
  IconAddressBook,
  IconBook2,
  IconClipboardList,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconPhone,
  IconRobot,
  IconSend,
  IconSettings,
  IconTemplate,
  IconTicket,
  type Icon,
} from "@tabler/icons-react";

const PRIMARY_NAV: { label: string; icon: Icon; active?: boolean }[] = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle },
  { label: "呼叫", icon: IconPhone },
  { label: "触达", icon: IconSend, active: true },
  { label: "历史", icon: IconHistory },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
];

const SUB_NAV: { label: string; icon: Icon; active?: boolean }[] = [
  { label: "人工外呼任务", icon: IconClipboardList },
  { label: "自动外呼任务", icon: IconRobot, active: true },
  { label: "外呼任务模板", icon: IconTemplate },
];

export function EngagementShell({ children }: { children: ReactNode }) {
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
                className={`flex h-11 w-11 flex-col items-center justify-center gap-0.5 rounded-lg text-[10px] ${active ? "bg-background font-semibold text-foreground shadow-sm" : "text-muted-foreground"}`}
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
          <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">李</span>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1">
        <nav className="flex w-[180px] shrink-0 flex-col border-r border-border bg-neutral-100 px-3 py-4">
          <div className="flex flex-col gap-0.5">
            {SUB_NAV.map(({ label, icon: ItemIcon, active }) => (
              <div
                key={label}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${active ? "bg-background font-semibold text-foreground shadow-sm" : "text-muted-foreground"}`}
              >
                <ItemIcon size={18} className="shrink-0" />
                {label}
              </div>
            ))}
          </div>
        </nav>
        <div className="min-h-0 flex-1 overflow-hidden bg-background">{children}</div>
      </div>
    </div>
  );
}
