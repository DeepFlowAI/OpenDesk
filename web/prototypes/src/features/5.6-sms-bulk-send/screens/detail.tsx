import {
  IconArrowLeft,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconTrash,
  IconUpload,
} from "@tabler/icons-react";
import { EngagementShell } from "../components/engagement-shell";
import {
  SMS_TARGETS,
  TARGET_STATUS_LABEL,
  TASK_TEMPLATE,
  type TargetStatus,
} from "../fixtures";

export type DetailTab = "targets" | "info";

const TARGET_STATUS_BADGE: Record<TargetStatus, string> = {
  pending: "bg-muted text-muted-foreground",
  sending: "bg-sky-50 text-sky-700",
  submitted: "bg-amber-50 text-amber-700",
  delivered: "bg-emerald-50 text-emerald-700",
  failed: "bg-red-50 text-red-700",
};

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-border px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${tone ?? ""}`}>{value}</div>
    </div>
  );
}

function HighlightedBody({ body }: { body: string }) {
  const parts = body.split(/(\{[^}]+\})/g);
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
      <span className="font-medium">【{TASK_TEMPLATE.signName}】</span>
      {parts.map((part, index) =>
        part.startsWith("{") && part.endsWith("}") ? (
          <span key={index} className="rounded bg-amber-100 px-0.5 text-amber-800">{part}</span>
        ) : (
          <span key={index}>{part}</span>
        )
      )}
    </div>
  );
}

function TargetsPanel() {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border border-border p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold">发送对象名单</h2>
          <p className="mt-1 text-sm text-muted-foreground">发布后系统按批自动发送；发送中不可修改名单，可先暂停。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm"><IconPlus size={16} />添加对象</button>
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm"><IconUpload size={16} />导入对象</button>
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm"><IconRefresh size={16} />重发失败对象</button>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground"><IconSearch size={16} />搜索接收号码</div>
        <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm text-muted-foreground">全部状态</div>
        <button className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm text-muted-foreground"><IconTrash size={15} />批量删除</button>
      </div>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-left text-muted-foreground">
            <tr>
              <th className="w-10 px-4 py-3"><span className="block h-4 w-4 rounded border border-border" /></th>
              <th className="px-4 py-3 font-medium">接收号码</th>
              <th className="px-4 py-3 font-medium">变量摘要</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">失败原因</th>
              <th className="px-4 py-3 font-medium">提交时间</th>
              <th className="px-4 py-3 font-medium">送达时间</th>
              <th className="w-20 px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {SMS_TARGETS.map((target) => (
              <tr key={target.phone} className="border-t border-border">
                <td className="px-4 py-3"><span className="block h-4 w-4 rounded border border-border" /></td>
                <td className="px-4 py-3 font-mono text-[13px]">{target.phone}</td>
                <td className="max-w-[220px] truncate px-4 py-3 text-muted-foreground">{`客户姓名：${target.name} · 预约时间：${target.time}`}</td>
                <td className="px-4 py-3"><span className={`rounded-md px-2 py-1 text-[11px] ${TARGET_STATUS_BADGE[target.status]}`}>{TARGET_STATUS_LABEL[target.status]}</span></td>
                <td className="max-w-[180px] truncate px-4 py-3 text-muted-foreground">{target.failReason ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{target.submittedAt ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{target.deliveredAt ?? "—"}</td>
                <td className="px-4 py-3 text-xs text-primary">查看</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>共 1,500 条</span>
        <span>每页 20 条</span>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-3 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function InfoPanel() {
  return (
    <div className="grid max-w-3xl gap-4">
      <section className="rounded-lg border border-border bg-background p-5">
        <h2 className="text-base font-semibold">基本信息</h2>
        <div className="mt-3 divide-y divide-border/60">
          <InfoRow label="任务名称" value="八月套餐到期提醒" />
          <InfoRow label="任务说明" value="针对 8 月底套餐到期的客户发送回访提醒，确认续费意向。" />
          <InfoRow label="发送时间" value="立即发送" />
          <InfoRow label="创建人" value="李婷" />
          <InfoRow label="创建时间" value="2026-08-08 09:12" />
        </div>
      </section>
      <section className="rounded-lg border border-border bg-background p-5">
        <h2 className="text-base font-semibold">短信内容</h2>
        <div className="mt-3 divide-y divide-border/60">
          <InfoRow label="短信模板" value={`${TASK_TEMPLATE.name}（${TASK_TEMPLATE.type}）`} />
          <InfoRow label="签名" value={TASK_TEMPLATE.signName} />
        </div>
        <div className="mt-3">
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">正文预览（发布时快照）</div>
          <HighlightedBody body={TASK_TEMPLATE.body} />
        </div>
        <div className="mt-4">
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">变量映射</div>
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="grid grid-cols-[120px_140px_1fr] items-center gap-3 border-b border-border bg-muted/50 px-3 py-2 text-[11px] font-medium text-muted-foreground">
              <span>变量</span><span>显示名</span><span>名单取值来源</span>
            </div>
            {TASK_TEMPLATE.variables.map((variable, index) => (
              <div key={variable.key} className="grid grid-cols-[120px_140px_1fr] items-center gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0">
                <span className="font-mono text-[13px]">{`{${variable.key}}`}</span>
                <span>{variable.label}</span>
                <span className="text-muted-foreground">名单列「{["客户姓名", "回访时间"][index]}」</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">模板内容于发布时快照；平台侧后续修改模板不影响本任务。</p>
        </div>
      </section>
    </div>
  );
}

export function SmsTaskDetailScreen({ tab }: { tab: DetailTab }) {
  const tabs: { key: DetailTab; label: string; count?: string }[] = [
    { key: "targets", label: "发送对象", count: "1,500" },
    { key: "info", label: "任务信息" },
  ];

  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="rounded-md p-2 text-muted-foreground"><IconArrowLeft size={18} /></span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold">八月套餐到期提醒</h1>
                <span className="rounded-md bg-sky-50 px-2 py-1 text-[11px] text-sky-700">发送中</span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">模板：预约回访提醒（深流客服） · 立即发送 · 创建于 2026-08-08 09:12</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="rounded-md border border-border px-3 py-2 text-sm">暂停</button>
            <button className="rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">归档</button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-6">
          <div className="space-y-6">
            <section className="grid grid-cols-6 gap-4">
              <Metric label="对象总数" value="1,500" />
              <Metric label="待发送" value="640" />
              <Metric label="已提交" value="120" />
              <Metric label="送达成功" value="702" tone="text-emerald-700" />
              <Metric label="发送失败" value="38" tone="text-red-600" />
              <Metric label="送达率" value="94.9%" />
            </section>

            <section>
              <div className="flex items-center border-b border-border">
                <div className="flex gap-6">
                  {tabs.map(({ key, label, count }) => {
                    const active = key === tab;
                    return (
                      <div
                        key={key}
                        className={`border-b-2 px-1 pb-3 text-sm font-medium ${active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground"}`}
                      >
                        {label}
                        {count && <span className="ml-2 text-xs text-muted-foreground">{count}</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="pt-4">
                {tab === "targets" ? <TargetsPanel /> : <InfoPanel />}
              </div>
            </section>
          </div>
        </main>
      </div>
    </EngagementShell>
  );
}
