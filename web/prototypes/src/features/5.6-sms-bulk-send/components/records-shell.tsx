import type { ReactNode } from "react";
import {
  IconActivity,
  IconAddressBook,
  IconBook2,
  IconChartBar,
  IconHeadset,
  IconHistory,
  IconInbox,
  IconMessage,
  IconMessageCircle,
  IconPhone,
  IconSend,
  IconSettings,
  IconTicket,
} from "@tabler/icons-react";

const PRIMARY_NAV = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle },
  { label: "呼叫", icon: IconPhone },
  { label: "触达", icon: IconSend },
  { label: "服务运营", icon: IconHistory, active: true },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
];

const RECORD_NAV_GROUPS = [
  [
    { label: "在线监控", icon: IconActivity },
    { label: "会话记录", icon: IconMessageCircle },
    { label: "留言记录", icon: IconInbox },
    { label: "会话报表", icon: IconChartBar },
  ],
  [
    { label: "呼叫监控", icon: IconHeadset },
    { label: "通话记录", icon: IconPhone },
    { label: "通话报表", icon: IconChartBar },
    { label: "发送记录", icon: IconMessage, active: true },
  ],
];

/** Workspace service-ops shell: primary icon nav + records secondary nav. */
export function RecordsShell({ children }: { children: ReactNode }) {
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
                title={label}
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

      <nav className="flex w-[180px] shrink-0 flex-col border-r border-border bg-neutral-100 px-3 py-4">
        <div className="flex flex-col gap-3">
          {RECORD_NAV_GROUPS.map((group, groupIndex) => (
            <div
              key={groupIndex}
              className={`flex flex-col gap-0.5 ${groupIndex > 0 ? "border-t border-border/70 pt-3" : ""}`}
            >
              {group.map(({ label, icon: ItemIcon, active }) => (
                <div
                  key={label}
                  className={`flex items-center gap-2.5 px-3 py-2 text-sm ${
                    active
                      ? "rounded-md bg-background font-semibold text-foreground shadow-sm"
                      : "rounded-lg text-muted-foreground"
                  }`}
                >
                  <ItemIcon size={16} />
                  <span>{label}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </nav>

      <main className="min-w-0 flex-1 overflow-hidden bg-white">{children}</main>
    </div>
  );
}
