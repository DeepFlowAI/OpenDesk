import { IconChevronDown, IconSearch } from "@tabler/icons-react";
import { RecordsShell } from "../components/records-shell";
import { SMS_RECORD_ROWS, TARGET_STATUS_LABEL, type SmsRecordRow } from "../fixtures";

type RecordStatus = SmsRecordRow["status"];

function statusTone(status: RecordStatus) {
  if (status === "delivered") return "bg-emerald-50 text-emerald-700";
  if (status === "failed") return "bg-red-50 text-red-700";
  if (status === "submitted" || status === "pending") return "bg-amber-50 text-amber-700";
  return "bg-muted text-muted-foreground";
}

function SourceCell({ source }: { source: SmsRecordRow["source"] }) {
  if (source.kind === "single") {
    return <span className="text-muted-foreground">单发</span>;
  }
  return <span className="text-sky-700 underline-offset-2 hover:underline">{source.taskName}</span>;
}

export function SmsRecordsSourceScreen() {
  return (
    <RecordsShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold text-foreground">发送记录</h1>
          <p className="mt-1 text-sm text-muted-foreground">查看本租户短信发送记录与送达状态，支持按来源区分单发与群发任务</p>
        </header>
        <div className="shrink-0 border-b border-border px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-64 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground">
              <IconSearch size={16} />
              <span>按手机号搜索</span>
            </div>
            <div className="flex h-9 w-36 items-center justify-between rounded-md border border-border px-3 text-sm">
              <span>全部状态</span>
              <IconChevronDown size={14} className="text-muted-foreground" />
            </div>
            <div className="flex h-9 w-36 items-center justify-between rounded-md border border-border px-3 text-sm">
              <span>全部来源</span>
              <IconChevronDown size={14} className="text-muted-foreground" />
            </div>
          </div>
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">接收号码</th>
                  <th className="px-4 py-3 font-medium">模板名称</th>
                  <th className="px-4 py-3 font-medium">签名</th>
                  <th className="px-4 py-3 font-medium">发送状态</th>
                  <th className="px-4 py-3 font-medium">来源</th>
                  <th className="px-4 py-3 font-medium">发起人</th>
                  <th className="px-4 py-3 font-medium">关联通话</th>
                  <th className="px-4 py-3 font-medium">发送时间</th>
                </tr>
              </thead>
              <tbody>
                {SMS_RECORD_ROWS.map((row) => (
                  <tr key={row.id} className="border-t border-border">
                    <td className="px-4 py-3 font-mono font-medium">{row.phone}</td>
                    <td className="px-4 py-3">{row.templateName}</td>
                    <td className="px-4 py-3">{row.signName}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-md px-2 py-1 text-[11px] ${statusTone(row.status)}`}>
                        {TARGET_STATUS_LABEL[row.status]}
                      </span>
                    </td>
                    <td className="px-4 py-3"><SourceCell source={row.source} /></td>
                    <td className="px-4 py-3">{row.sender}</td>
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
          <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
            <span>共 {SMS_RECORD_ROWS.length} 条</span>
            <span>每页 20 条</span>
          </div>
        </main>
      </div>
    </RecordsShell>
  );
}
