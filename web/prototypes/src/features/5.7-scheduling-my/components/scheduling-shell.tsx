import type { ReactNode } from "react"
import { IconCalendarStats } from "@tabler/icons-react"
import { AGENT_NAME } from "../fixtures"

export type SchedulingMyTab = "me" | "board" | "shifts" | "rules"

export type ShellMode = "agent-only" | "with-manage"

/** Standalone /scheduling shell for phase-3 My Schedule review. */
export function SchedulingShell({
  tab,
  mode,
  children,
}: {
  tab: SchedulingMyTab
  mode: ShellMode
  children: ReactNode
}) {
  const tabs =
    mode === "agent-only"
      ? ([{ id: "me" as const, label: "我的排班" }] as const)
      : ([
          { id: "me" as const, label: "我的排班" },
          { id: "board" as const, label: "排班" },
          { id: "shifts" as const, label: "班次管理" },
          { id: "rules" as const, label: "规则" },
        ] as const)

  return (
    <div className="flex h-full flex-col bg-muted/30 text-foreground">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <div className="flex self-stretch items-center gap-4">
          <div className="flex items-center gap-2">
            <IconCalendarStats size={22} className="text-foreground" />
            <span className="text-base font-semibold">排班中心</span>
          </div>
          <nav className="ml-6 flex items-stretch gap-1 self-stretch">
            {tabs.map((item) => (
              <TabItem key={item.id} label={item.label} active={tab === item.id} />
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
            {AGENT_NAME.slice(0, 1)}
          </div>
          <span>{AGENT_NAME}</span>
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
