import type { ReactNode } from "react"
import {
  IconAddressBook,
  IconBook2,
  IconCalendarStats,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconPhone,
  IconSchool,
  IconSend,
  IconSettings,
  IconTicket,
} from "@tabler/icons-react"

const PRIMARY_NAV = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle },
  { label: "呼叫", icon: IconPhone },
  { label: "触达", icon: IconSend },
  { label: "服务运营", icon: IconHistory },
  { label: "学习中心", icon: IconSchool },
  { label: "排班中心", icon: IconCalendarStats, active: true, isNew: true },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
]

/** Front-desk primary nav with Scheduling Center visible for my.view holders. */
export function WorkspaceNavShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="relative z-30 flex w-16 shrink-0 flex-col justify-between border-r border-[#E5E5E5] bg-[#F5F5F5] py-4">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-full items-center justify-center">
            <IconHeadset size={28} className="text-[#1a1a1a]" />
          </div>
          <nav className="flex w-full flex-col items-center gap-1">
            {PRIMARY_NAV.map(({ label, icon: ItemIcon, active, isNew }) => (
              <div key={label} className="relative">
                <div
                  className={`flex h-11 w-11 items-center justify-center rounded-lg ${
                    active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"
                  }`}
                  title={label}
                >
                  <ItemIcon size={20} stroke={1.7} />
                </div>
                {isNew ? (
                  <span className="absolute -right-1.5 -top-1.5 rounded-md bg-primary px-1 py-px text-[9px] font-semibold text-primary-foreground">
                    NEW
                  </span>
                ) : null}
              </div>
            ))}
          </nav>
        </div>
        <div className="flex flex-col items-center gap-2">
          <div className="grid h-10 w-10 place-items-center rounded-lg text-muted-foreground">
            <IconSettings size={20} />
          </div>
          <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">
            张
          </span>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-hidden bg-white">{children}</main>
    </div>
  )
}
