import { IconEye, IconMessage, IconPlus, IconSearch } from "@tabler/icons-react";
import { EngagementShell } from "../components/engagement-shell";
import { SMS_TASKS, TASK_STATUS_LABEL, type SmsTask, type TaskStatus } from "../fixtures";

const STATUS_BADGE: Record<TaskStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  scheduled: "bg-amber-50 text-amber-700",
  sending: "bg-sky-50 text-sky-700",
  paused: "bg-amber-50 text-amber-700",
  completed: "bg-emerald-50 text-emerald-700",
  archived: "bg-muted text-muted-foreground",
};

function deliveryRate(task: SmsTask) {
  const terminal = task.delivered + task.failed;
  if (!terminal) return "—";
  return `${((task.delivered / terminal) * 100).toFixed(1)}%`;
}

function Header() {
  return (
    <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">短信群发任务</h1>
        <p className="mt-1 text-sm text-muted-foreground">选择已授权短信模板，导入名单后由系统自动分批发送，并回送达到任务统计</p>
      </div>
      <button className="inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
        <IconPlus size={16} />
        新建任务
      </button>
    </header>
  );
}

function Toolbar() {
  return (
    <div className="flex shrink-0 items-center gap-3 border-b border-border px-6 py-3">
      <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3">
        <IconSearch size={16} className="text-muted-foreground" />
        <span className="text-sm text-muted-foreground">搜索任务名称</span>
      </div>
      <div className="flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm text-muted-foreground">全部状态</div>
    </div>
  );
}

export function SmsTaskListScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <Header />
        <Toolbar />
        <main className="min-h-0 flex-1 overflow-auto p-6">
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">任务名称</th>
                  <th className="px-4 py-3 font-medium">短信模板</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">进度</th>
                  <th className="px-4 py-3 font-medium">送达率</th>
                  <th className="px-4 py-3 font-medium">发送时间</th>
                  <th className="px-4 py-3 font-medium">创建人</th>
                  <th className="px-4 py-3 font-medium">更新时间</th>
                  <th className="w-20 px-4 py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {SMS_TASKS.map((task) => {
                  const terminal = task.delivered + task.failed;
                  return (
                    <tr key={task.id} className="border-t border-border">
                      <td className="max-w-[180px] truncate px-4 py-3 font-medium">
                        <span className="hover:underline">{task.name}</span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{task.templateName}</td>
                      <td className="px-4 py-3">
                        <span className={`rounded-md px-2 py-1 text-[11px] ${STATUS_BADGE[task.status]}`}>{TASK_STATUS_LABEL[task.status]}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-sm">{terminal.toLocaleString()} / {task.total.toLocaleString()}</div>
                        <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary" style={{ width: task.total ? `${Math.round((terminal / task.total) * 100)}%` : "0%" }} />
                        </div>
                      </td>
                      <td className="px-4 py-3">{deliveryRate(task)}</td>
                      <td className="px-4 py-3 text-muted-foreground">{task.sendTime}</td>
                      <td className="px-4 py-3">{task.creator}</td>
                      <td className="px-4 py-3 text-muted-foreground">{task.updatedAt}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <IconEye size={17} />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
            <span>共 {SMS_TASKS.length} 条</span>
            <span>每页 20 条</span>
          </div>
        </main>
      </div>
    </EngagementShell>
  );
}

export function SmsTaskListEmptyScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <Header />
        <Toolbar />
        <main className="min-h-0 flex-1 overflow-auto p-6">
          <div className="flex h-full min-h-[320px] flex-col items-center justify-center rounded-lg border border-dashed border-border text-center">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-muted text-muted-foreground">
              <IconMessage size={22} />
            </span>
            <p className="mt-4 text-sm text-muted-foreground">暂无短信群发任务</p>
            <button className="mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
              <IconPlus size={16} />
              新建任务
            </button>
          </div>
        </main>
      </div>
    </EngagementShell>
  );
}
