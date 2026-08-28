import { IconCalendarStats } from "@tabler/icons-react"
import { WorkspaceNavShell } from "../components/workspace-nav-shell"

/** Primary-nav entry: Scheduling Center after Learning Center. */
export function SchedulingNavEntryScreen() {
  return (
    <WorkspaceNavShell>
      <div className="flex h-full items-center justify-center bg-muted/40">
        <div className="w-[480px] rounded-xl border border-border bg-white p-8 text-center shadow-sm">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <IconCalendarStats size={28} />
          </div>
          <h1 className="text-lg font-semibold">排班中心</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            主导航新增入口，位于「学习中心」之后。点击后当前窗口跳转
            <span className="mx-1 rounded bg-muted px-1.5 py-0.5 font-mono text-xs">/scheduling</span>
            独立全屏页面，不占工作台二级导航。
          </p>
          <div className="mt-5 rounded-lg border border-dashed border-border bg-muted/30 px-4 py-3 text-xs leading-5 text-muted-foreground">
            无 scheduling.center.manage 权限的员工不展示该入口；直接访问 /scheduling 展示 403。一期无坐席端「我的排班」。
          </div>
        </div>
      </div>
    </WorkspaceNavShell>
  )
}
