import {
  IconArrowLeft,
  IconBook2,
  IconChevronDown,
  IconChevronRight,
  IconFileDescription,
  IconLayoutColumns,
  IconPhone,
  IconPlus,
  IconUser,
} from "@tabler/icons-react";
import type { CallRecordFixture, OutboundTargetFixture, TargetStatus } from "../fixtures";
import { TASKS } from "../fixtures";

function TaskStatusBadge({ status }: { status: "进行中" | "已暂停" }) {
  const cls = status === "进行中" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground";
  return <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium ${cls}`}>{status}</span>;
}

export function TaskListPage() {
  return (
    <section className="flex min-w-0 flex-1 flex-col bg-muted/40">
      <div className="border-b border-border bg-background px-6 py-4">
        <h1 className="text-base font-semibold">我的外呼任务</h1>
      </div>
      <div className="flex-1 overflow-hidden p-5">
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/60 text-xs">
                <th className="px-5 py-3 font-medium text-muted-foreground">任务名称</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">状态</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">我的进度</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">截止时间</th>
                <th className="px-5 py-3 text-right font-medium text-muted-foreground">操作</th>
              </tr>
            </thead>
            <tbody>
              {TASKS.map((task) => {
                const pct = Math.round((task.done / task.total) * 100);
                return (
                  <tr key={task.id} className="border-b border-border/50 last:border-0">
                    <td className="px-5 py-3.5 font-medium">{task.name}</td>
                    <td className="px-4 py-3.5">
                      <TaskStatusBadge status={task.status} />
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {task.done}/{task.total} · {pct}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-xs">
                      <span className={task.overdue ? "font-medium text-destructive" : "text-muted-foreground"}>
                        {task.overdue ? "已逾期 · " : ""}
                        {task.due}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <span className="inline-flex h-8 items-center gap-1 rounded-lg border border-border bg-background px-3 text-xs font-medium">
                        查看
                        <IconChevronRight size={13} />
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

export function ExecPageHeader() {
  return (
    <div className="flex items-center gap-3 border-b border-border bg-background px-5 py-3">
      <span className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground">
        <IconArrowLeft size={13} />
        返回任务列表
      </span>
      <div className="flex items-center gap-2">
        <h1 className="text-sm font-semibold">双 11 客户回访</h1>
        <TaskStatusBadge status="进行中" />
      </div>
      <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
        <span>我的进度 5/50 · 10%</span>
        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
          <div className="h-full w-[10%] rounded-full bg-primary" />
        </div>
      </div>
    </div>
  );
}

export function TargetStatusBadge({ status }: { status: TargetStatus }) {
  const cls =
    status === "待呼叫"
      ? "bg-info/10 text-info"
      : status === "需重拨"
        ? "bg-warning/15 text-foreground"
        : "bg-success/10 text-success";
  return <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium ${cls}`}>{status}</span>;
}

export function RecordsTable({ records }: { records: CallRecordFixture[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border bg-muted/60">
            <th className="px-3 py-2 font-medium text-muted-foreground">呼叫时间</th>
            <th className="px-3 py-2 font-medium text-muted-foreground">结果</th>
            <th className="px-3 py-2 font-medium text-muted-foreground">时长</th>
            <th className="px-3 py-2 font-medium text-muted-foreground">接待客服</th>
            <th className="px-3 py-2 text-right font-medium text-muted-foreground">操作</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record, index) => (
            <tr key={index} className="border-b border-border/50 last:border-0">
              <td className="px-3 py-2 font-mono text-[11px]">{record.time}</td>
              <td className="px-3 py-2">
                <span
                  className={
                    record.result === "已接通" ? "font-medium text-success" : "text-muted-foreground"
                  }
                >
                  {record.result}
                </span>
              </td>
              <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{record.duration}</td>
              <td className="px-3 py-2 text-muted-foreground">{record.agent}</td>
              <td className="px-3 py-2 text-right">
                <span className="font-medium text-primary">详情</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TargetRow({
  target,
  selected,
}: {
  target: OutboundTargetFixture;
  selected?: boolean;
}) {
  return (
    <div
      className={
        selected
          ? "rounded-lg border border-primary/60 bg-muted/50 p-3"
          : "rounded-lg border border-border bg-card p-3"
      }
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium">{target.name ?? target.phone}</span>
        <TargetStatusBadge status={target.status} />
      </div>
      {target.name ? <p className="mt-0.5 font-mono text-xs text-muted-foreground">{target.phone}</p> : null}
      <p className="mt-1.5 text-xs text-muted-foreground">{target.lastCall}</p>
    </div>
  );
}

export function TargetListPane({
  targets,
  selectedId,
}: {
  targets: OutboundTargetFixture[];
  selectedId: number;
}) {
  return (
    <section className="flex w-[320px] shrink-0 flex-col border-r border-border bg-background">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">对象列表</h2>
        <div className="flex h-8 items-center gap-1 rounded-md border border-border px-2.5 text-xs text-muted-foreground">
          全部状态
          <IconChevronDown size={12} />
        </div>
      </div>
      <div className="flex-1 space-y-2 overflow-hidden p-3">
        {targets.map((target) => (
          <TargetRow key={target.id} target={target} selected={target.id === selectedId} />
        ))}
      </div>
    </section>
  );
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/60 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 truncate text-xs font-medium">{value}</div>
    </div>
  );
}

export function PreviewPanel({
  target,
  activeTab = "business",
  calling = false,
}: {
  target: OutboundTargetFixture;
  activeTab?: "business" | "records";
  calling?: boolean;
}) {
  return (
    <section className="flex min-w-0 flex-1 flex-col overflow-hidden bg-muted/40">
      <div className="flex-1 space-y-4 overflow-hidden p-5">
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">{target.name ?? target.phone}</h2>
                <TargetStatusBadge status={target.status} />
              </div>
              <p className="mt-1 font-mono text-xl font-semibold tracking-wide">{target.phone}</p>
              <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                <IconUser size={13} />
                {target.name ? `关联用户：${target.name} · 普通客户 · 历史工单 2 个` : "未关联用户"}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted-foreground">
                <IconLayoutColumns size={15} />
                常规弹屏
              </span>
              <span className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-sm font-medium">
                <IconBook2 size={15} />
                话术流程
              </span>
              <span
                className={
                  calling
                    ? "inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary/40 px-4 text-sm font-medium text-primary-foreground"
                    : "inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm"
                }
              >
                <IconPhone size={15} />
                呼叫
              </span>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-4 gap-2.5">
            <InfoItem label="任务" value="双 11 客户回访" />
            <InfoItem label="最近结果" value={target.records[0]?.result ?? "—"} />
            <InfoItem label="下次跟进" value={target.followUp} />
            <InfoItem label="累计呼叫" value={`${target.callCount} 次`} />
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between border-b border-border pr-5">
            <div className="flex items-center gap-1 px-3 pt-2.5">
              <span
                className={
                  activeTab === "business"
                    ? "border-b-2 border-primary px-3 pb-2 text-sm font-medium text-primary"
                    : "px-3 pb-2 text-sm text-muted-foreground"
                }
              >
                业务记录
              </span>
              <span
                className={
                  activeTab === "records"
                    ? "border-b-2 border-primary px-3 pb-2 text-sm font-medium text-primary"
                    : "px-3 pb-2 text-sm text-muted-foreground"
                }
              >
                呼叫记录
              </span>
            </div>
            {activeTab === "records" ? (
              <span className="text-xs text-muted-foreground">共 {target.records.length} 条</span>
            ) : null}
          </div>
          {activeTab === "business" ? (
            <div className="space-y-3 p-5">
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">外呼结果</div>
                <div className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm text-muted-foreground">
                  待填写
                  <IconChevronDown size={14} />
                </div>
              </div>
              <div>
                <div className="mb-1 text-xs font-medium text-muted-foreground">外呼备注</div>
                <div className="h-16 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
                  记录本次沟通要点…
                </div>
              </div>
              <div className="flex justify-end">
                <span className="inline-flex h-9 items-center rounded-lg border border-border bg-background px-4 text-sm font-medium">
                  保存业务记录
                </span>
              </div>
            </div>
          ) : (
            <div className="p-5">
              {target.records.length > 0 ? (
                <RecordsTable records={target.records} />
              ) : (
                <div className="grid h-20 place-items-center rounded-lg border border-dashed border-border text-xs text-muted-foreground">
                  暂无呼叫记录
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

export function WrapUpPanel() {
  return (
    <section className="flex min-w-0 flex-1 flex-col overflow-hidden bg-muted/40">
      <div className="flex-1 space-y-4 overflow-hidden p-5">
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold">本次通话</h3>
          <div className="grid grid-cols-3 gap-2.5">
            <InfoItem label="呼叫结果" value="已接通" />
            <InfoItem label="通话时长" value="05:32" />
            <InfoItem label="开始时间" value="2026-08-17 14:30" />
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold">对象状态</h3>
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex h-9 items-center rounded-lg bg-success px-4 text-sm font-medium text-white shadow-sm">
              已完成
            </span>
            <span className="inline-flex h-9 items-center rounded-lg bg-warning/15 px-4 text-sm font-medium">
              需重拨
            </span>
            <span className="inline-flex h-9 items-center rounded-lg border border-border bg-background px-4 text-sm font-medium">
              待呼叫
            </span>
            <span className="inline-flex h-9 items-center rounded-lg bg-destructive/10 px-4 text-sm font-medium text-destructive">
              勿扰
            </span>
            <span className="inline-flex h-9 items-center rounded-lg bg-destructive/10 px-4 text-sm font-medium text-destructive">
              无效号码
            </span>
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold">业务记录</h3>
          <div className="space-y-3">
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">外呼结果</div>
              <div className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
                已接通 · 有意向
                <IconChevronDown size={14} className="text-muted-foreground" />
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">外呼备注</div>
              <div className="h-16 rounded-md border border-border px-3 py-2 text-sm">
                客户对续费有意向，希望本周内收到报价单。
              </div>
            </div>
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">预约回拨</div>
              <div className="flex h-9 items-center rounded-md border border-dashed border-border bg-muted/50 px-3 text-sm text-muted-foreground">
                选择「需重拨」后预约回拨时间
              </div>
            </div>
          </div>
        </section>
      </div>
      <footer className="flex items-center justify-between border-t border-border bg-background px-5 py-3">
        <span className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted-foreground">
          <IconFileDescription size={15} />
          新建工单
        </span>
        <span className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground shadow-sm">
          <IconPlus size={15} />
          提交
        </span>
      </footer>
    </section>
  );
}
