import { IconCalendarStats } from "@tabler/icons-react"
import { WorkspaceNavShell } from "../components/workspace-nav-shell"

/** Agent with scheduling.my.view only: Scheduling Center appears in primary nav. */
export function SchedulingMyNavEntryScreen() {
  return (
    <WorkspaceNavShell>
      <div className="flex h-full items-center justify-center bg-muted/40">
        <div className="w-[480px] rounded-xl border border-border bg-white p-8 text-center shadow-sm">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <IconCalendarStats size={28} />
          </div>
          <h1 className="text-lg font-semibold">排班中心</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            三期：拥有
            <span className="mx-1 rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              scheduling.my.view
            </span>
            时显示同一主导航入口；默认进入「我的排班」，只读本人已发布班表。
          </p>
          <div className="mt-5 rounded-lg border border-dashed border-border bg-muted/30 px-4 py-3 text-xs leading-5 text-muted-foreground">
            无 my.view 且无 manage 时不展示入口。默认角色均不预置 my.view。不看同事班表。
          </div>
        </div>
      </div>
    </WorkspaceNavShell>
  )
}
