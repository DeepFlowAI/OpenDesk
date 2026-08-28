import type { ReactNode } from "react";
import { IconSearch, IconX } from "@tabler/icons-react";
import { AdminShell } from "../components/admin-shell";
import {
  SMS_TEMPLATES,
  STATUS_LABEL,
  TYPE_LABEL,
  type TemplateStatus,
  type SmsTemplate,
} from "../fixtures";

function statusTone(status: TemplateStatus) {
  if (status === "available") return "bg-emerald-50 text-emerald-700";
  return "bg-muted text-muted-foreground";
}

function TemplateTable({ rows }: { rows: SmsTemplate[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">模板名称</th>
            <th className="px-4 py-3 font-medium">签名</th>
            <th className="px-4 py-3 font-medium">类型</th>
            <th className="px-4 py-3 font-medium">变量</th>
            <th className="px-4 py-3 font-medium">状态</th>
            <th className="px-4 py-3 font-medium">更新时间</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-border">
              <td className="px-4 py-3 font-medium">{row.name}</td>
              <td className="px-4 py-3">{row.signName}</td>
              <td className="px-4 py-3">
                <span className="rounded-md bg-sky-50 px-2 py-1 text-[11px] text-sky-700">{TYPE_LABEL[row.type]}</span>
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {row.variables.length ? row.variables.map((v) => v.label).join("、") : "—"}
              </td>
              <td className="px-4 py-3">
                <span className={`rounded-md px-2 py-1 text-[11px] ${statusTone(row.status)}`}>
                  {STATUS_LABEL[row.status]}
                </span>
              </td>
              <td className="px-4 py-3 text-muted-foreground">{row.updatedAt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SmsAdminPage({ children, filters }: { children: ReactNode; filters?: ReactNode }) {
  return (
    <AdminShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold text-foreground">短信管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            查看已授权的短信模板；模板由外部租户管理系统经平台 API 配置，租户侧只读。发送记录请前往服务运营查看。
          </p>
        </header>
        <div className="shrink-0 border-b border-border px-6 py-3">{filters}</div>
        <main className="min-h-0 flex-1 overflow-y-auto px-6 py-4">{children}</main>
      </div>
    </AdminShell>
  );
}

function SearchFilter() {
  return (
    <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground">
      <IconSearch size={16} />
      <span>按模板名称搜索</span>
    </div>
  );
}

export function SmsTemplatesScreen() {
  return (
    <SmsAdminPage filters={<SearchFilter />}>
      <TemplateTable rows={SMS_TEMPLATES} />
      <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
        <span>共 {SMS_TEMPLATES.length} 条</span>
        <span>每页 20 条</span>
      </div>
    </SmsAdminPage>
  );
}

export function SmsTemplatesEmptyScreen() {
  return (
    <SmsAdminPage filters={<SearchFilter />}>
      <div className="flex h-[420px] flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20">
        <p className="text-sm text-muted-foreground">暂无可用短信模板，请联系平台管理员为当前租户授权模板。</p>
      </div>
    </SmsAdminPage>
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

export function SmsTemplateDetailScreen() {
  const template = SMS_TEMPLATES[0];
  return (
    <div className="relative h-full">
      <SmsTemplatesScreen />
      <div className="absolute inset-0 bg-black/20" />
      <aside className="absolute inset-y-0 right-0 flex w-[420px] flex-col border-l border-border bg-background shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold">模板详情</h2>
          <IconX size={18} className="text-muted-foreground" />
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4 text-sm">
          <Field label="模板名称" value={template.name} />
          <Field label="签名" value={template.signName} />
          <Field label="类型" value={TYPE_LABEL[template.type]} />
          <Field label="状态" value={STATUS_LABEL[template.status]} />
          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">模板正文</div>
            <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 leading-6">{template.body}</div>
          </div>
          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">变量</div>
            <div className="space-y-2">
              {template.variables.map((variable) => (
                <div key={variable.key} className="rounded-md border border-border px-3 py-2">
                  <div className="font-medium">
                    {variable.label}
                    {variable.required ? <span className="ml-1 text-red-500">*</span> : null}
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-muted-foreground">{`{${variable.key}}`}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
