import type { ReactNode } from "react"
import { IconCalendarStats } from "@tabler/icons-react"

export type SchedulingTab = "board" | "shifts"

/** Standalone full-page shell for /scheduling. */
export function SchedulingShell({
  tab,
  children,
}: {
  tab?: SchedulingTab
  children: ReactNode
}) {
  return (
    <div className="flex h-full flex-col bg-muted/30 text-foreground">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex self-stretch items-center gap-4">
          <div className="flex items-center gap-2">
            <IconCalendarStats size={22} className="text-foreground" />
            <span className="text-base font-semibold">排班中心</span>
          </div>
          {tab ? (
            <nav className="ml-6 flex items-stretch gap-1 self-stretch">
              <TabItem label="排班" active={tab === "board"} />
              <TabItem label="班次管理" active={tab === "shifts"} />
            </nav>
          ) : null}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
            张
          </div>
          <span>张敏</span>
        </div>
      </header>
      <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
    </div>
  )
}

function TabItem({ label, active }: { label: string; active?: boolean }) {
  return (
    <div
      className={`-mb-px flex items-center border-b-2 px-3 text-sm ${
        active
          ? "border-primary font-semibold text-foreground"
          : "border-transparent text-muted-foreground"
      }`}
    >
      {label}
    </div>
  )
}
