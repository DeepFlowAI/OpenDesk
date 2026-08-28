import { IconChevronDown, IconSearch, IconX } from "@tabler/icons-react";
import { RecordsShell } from "../components/records-shell";
import {
  SEND_STATUS_LABEL,
  SMS_RECORDS,
  type SendStatus,
  type SmsSendRecord,
} from "../fixtures";

function statusTone(status: SendStatus) {
  if (status === "delivered") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-red-50 text-red-700";
  if (status === "submitted" || status === "pending") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

function RecordTable({ rows }: { rows: SmsSendRecord[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">接收号码</th>
            <th className="px-4 py-3 font-medium">模板名称</th>
            <th className="px-4 py-3 font-medium">签名</th>
            <th className="px-4 py-3 font-medium">发送状态</th>
            <th className="px-4 py-3 font-medium">发起人</th>
            <th className="px-4 py-3 font-medium">关联通话</th>
            <th className="px-4 py-3 font-medium">发送时间</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-border">
              <td className="px-4 py-3 font-mono font-medium">{row.phone}</td>
              <td className="px-4 py-3">{row.templateName}</td>
              <td className="px-4 py-3">{row.signName}</td>
              <td className="px-4 py-3">
                <span className={`rounded-md px-2 py-1 text-[11px] ${statusTone(row.status)}`}>
                  {SEND_STATUS_LABEL[row.status]}
                </span>
              </td>
              <td className="px-4 py-3">{row.agentName}</td>
              <td className="px-4 py-3">
                {row.callId ? (
                  <span className="text-sky-700 underline-offset-2 hover:underline">{row.callId}</span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
              <td className="px-4 py-3 text-muted-foreground">{row.sentAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="mb-1 text-xs text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}

export function SmsRecordsScreen() {
  return (
    <RecordsShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold text-foreground">发送记录</h1>
          <p className="mt-1 text-sm text-muted-foreground">查看本租户短信单发记录与送达状态</p>
        </header>
        <div className="shrink-0 border-b border-border px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-64 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground">
              <IconSearch size={16} />
              <span>按手机号搜索</span>
            </div>
            <div className="flex h-9 w-40 items-center justify-between rounded-md border border-border px-3 text-sm">
              <span>全部状态</span>
              <IconChevronDown size={14} className="text-muted-foreground" />
            </div>
          </div>
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <RecordTable rows={SMS_RECORDS} />
          <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
            <span>共 {SMS_RECORDS.length} 条</span>
            <span>每页 20 条</span>
          </div>
        </main>
      </div>
    </RecordsShell>
  );
}

export function SmsRecordDetailScreen() {
  const record = SMS_RECORDS[2];
  return (
    <div className="relative h-full">
      <SmsRecordsScreen />
      <div className="absolute inset-0 bg-black/20" />
      <aside className="absolute inset-y-0 right-0 flex w-[440px] flex-col border-l border-border bg-background shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold">发送详情</h2>
          <IconX size={18} className="text-muted-foreground" />
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4 text-sm">
          <Field label="接收号码" value={record.phone} />
          <Field label="模板名称" value={record.templateName} />
          <Field label="签名" value={record.signName} />
          <div>
            <div className="mb-1 text-xs text-muted-foreground">发送状态</div>
            <span className={`rounded-md px-2 py-1 text-[11px] ${statusTone(record.status)}`}>
              {SEND_STATUS_LABEL[record.status]}
            </span>
          </div>
          {record.failReason ? (
            <div>
              <div className="mb-1 text-xs text-muted-foreground">失败原因</div>
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700">{record.failReason}</div>
            </div>
          ) : null}
          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">短信正文快照</div>
            <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 leading-6">{record.bodySnapshot}</div>
          </div>
          <Field label="发起人" value={record.agentName} />
          <Field label="关联通话" value={record.callId ?? "—"} />
          <Field label="发送时间" value={record.sentAt} />
          <Field label="通道回执 ID" value={record.bizId} />
        </div>
      </aside>
    </div>
  );
}
