import {
  IconEye,
  IconPlus,
  IconSearch,
} from "@tabler/icons-react";
import { EngagementShell } from "../components/engagement-shell";
import { AUTO_TASKS, MODE_LABEL, type TaskMode } from "../fixtures";

const MODE_BADGE: Record<TaskMode, string> = {
  ivr: "bg-sky-50 text-sky-700",
  bot: "bg-violet-50 text-violet-700",
  agent: "bg-emerald-50 text-emerald-700",
};

const STATUS_BADGE: Record<string, string> = {
  进行中: "bg-emerald-50 text-emerald-700",
  暂停: "bg-amber-50 text-amber-700",
  草稿: "bg-muted text-muted-foreground",
  已完成: "bg-sky-50 text-sky-700",
};

export function AutoOutboundListScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold text-foreground">自动外呼任务</h1>
            <p className="mt-1 text-sm text-muted-foreground">系统按外呼计划自动批量拨号，接通后由语音流程、语音机器人或人工坐席接待</p>
          </div>
          <button className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
            <IconPlus size={16} />
            新建任务
          </button>
        </header>

        <div className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-3">
          <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3">
            <IconSearch size={16} className="text-muted-foreground" />
            <span className="text-sm text-muted-foreground">搜索任务名称</span>
          </div>
          <div className="flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm text-muted-foreground">全部状态</div>
          <div className="flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm text-muted-foreground">全部执行方式</div>
        </div>

        <main className="min-h-0 flex-1 overflow-auto p-6">
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">任务名称</th>
                  <th className="px-4 py-3 font-medium">执行方式</th>
                  <th className="px-4 py-3 font-medium">接待目标</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">进度</th>
                  <th className="px-4 py-3 font-medium">接通率</th>
                  <th className="px-4 py-3 font-medium">更新时间</th>
                  <th className="w-20 px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {AUTO_TASKS.map((task) => (
                  <tr key={task.name} className="border-t border-border">
                    <td className="px-4 py-3 font-medium">
                      <span className="hover:underline">{task.name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-md px-2 py-1 text-[11px] ${MODE_BADGE[task.mode]}`}>{MODE_LABEL[task.mode]}</span>
                    </td>
                    <td className="max-w-[180px] truncate px-4 py-3 text-muted-foreground">{task.target}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <span className={`rounded-md px-2 py-1 text-[11px] ${STATUS_BADGE[task.status]}`}>{task.status}</span>
                        {task.waitingWindow && (
                          <span className="rounded-md border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">待拨</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm">{task.done.toLocaleString()} / {task.total.toLocaleString()}</div>
                      <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary" style={{ width: task.total ? `${Math.round((task.done / task.total) * 100)}%` : "0%" }} />
                      </div>
                    </td>
                    <td className="px-4 py-3">{task.connectRate}</td>
                    <td className="px-4 py-3 text-muted-foreground">{task.updatedAt}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <IconEye size={17} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </main>
      </div>
    </EngagementShell>
  );
}
