import type { ReactNode } from "react";
import { IconArrowLeft, IconChevronDown } from "@tabler/icons-react";
import { EngagementShell } from "../components/engagement-shell";
import { TASK_TEMPLATE } from "../fixtures";

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-background p-5">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Field({ label, required, children, hint }: { label: string; required?: boolean; children: ReactNode; hint?: string }) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium text-muted-foreground">
        {required && <span className="mr-0.5 text-red-500">*</span>}{label}
      </div>
      {children}
      {hint && <div className="mt-1.5 text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

function SelectBox({ value }: { value: string }) {
  return (
    <div className="flex h-9 w-full items-center justify-between rounded-md border border-border bg-background px-3 text-sm">
      <span>{value}</span>
      <IconChevronDown size={14} className="text-muted-foreground" />
    </div>
  );
}

function BodyPreview({ body, highlight }: { body: string; highlight: boolean }) {
  const parts = body.split(/(\{[^}]+\})/g);
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
      <span className="font-medium">【{TASK_TEMPLATE.signName}】</span>
      {parts.map((part, index) =>
        part.startsWith("{") && part.endsWith("}") ? (
          <span key={index} className={highlight ? "rounded bg-amber-100 px-0.5 text-amber-800" : "text-muted-foreground"}>
            {part}
          </span>
        ) : (
          <span key={index}>{part}</span>
        )
      )}
    </div>
  );
}

export function SmsTaskCreateScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="rounded-md p-2 text-muted-foreground"><IconArrowLeft size={18} /></span>
            <div>
              <h1 className="text-xl font-semibold">新建短信群发任务</h1>
              <p className="mt-1 text-sm text-muted-foreground">选择短信模板并设定发送时间，保存后进入详情页维护发送名单</p>
            </div>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto bg-surface p-6">
          <div className="mx-auto max-w-3xl space-y-4">
            <Card title="基本信息">
              <div className="grid gap-4">
                <Field label="任务名称" required>
                  <div className="flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm">八月套餐到期提醒</div>
                </Field>
                <Field label="任务说明">
                  <div className="min-h-[80px] rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground">
                    针对 8 月底套餐到期的客户发送回访提醒，确认续费意向。
                  </div>
                </Field>
              </div>
            </Card>

            <Card title="短信内容">
              <div className="grid gap-4">
                <Field label="短信模板" required hint="仅列出本租户已授权且可用的模板">
                  <SelectBox value={`${TASK_TEMPLATE.name}（${TASK_TEMPLATE.signName}）`} />
                </Field>
                <div>
                  <div className="mb-1.5 text-xs font-medium text-muted-foreground">变量说明</div>
                  <div className="overflow-hidden rounded-lg border border-border">
                    <div className="grid grid-cols-[120px_1fr_80px_100px] items-center gap-3 border-b border-border bg-muted/50 px-3 py-2 text-[11px] font-medium text-muted-foreground">
                      <span>变量</span><span>显示名</span><span>是否必填</span><span>最大长度</span>
                    </div>
                    {TASK_TEMPLATE.variables.map((variable) => (
                      <div key={variable.key} className="grid grid-cols-[120px_1fr_80px_100px] items-center gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0">
                        <span className="font-mono text-[13px]">{`{${variable.key}}`}</span>
                        <span>{variable.label}</span>
                        <span>{variable.required ? "必填" : "选填"}</span>
                        <span className="text-muted-foreground">{variable.maxLength} 字</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-1.5 text-[11px] text-muted-foreground">导入名单时将文件列映射到上述变量，逐人生成差异化内容</div>
                </div>
                <div>
                  <div className="mb-1.5 text-xs font-medium text-muted-foreground">正文预览</div>
                  <BodyPreview body={TASK_TEMPLATE.body} highlight />
                </div>
              </div>
            </Card>

            <Card title="发送时间">
              <div className="space-y-3">
                <label className="flex items-center gap-2.5 text-sm">
                  <span className="grid h-4 w-4 place-items-center rounded-full border border-primary">
                    <span className="h-2 w-2 rounded-full bg-primary" />
                  </span>
                  <span className="font-medium">立即发送</span>
                  <span className="text-xs text-muted-foreground">发布后系统立即开始分批发送</span>
                </label>
                <label className="flex items-center gap-2.5 text-sm">
                  <span className="grid h-4 w-4 place-items-center rounded-full border border-border" />
                  <span className="font-medium">定时发送</span>
                  <div className="flex h-9 w-48 items-center rounded-md border border-border bg-muted/40 px-3 text-sm text-muted-foreground">2026-08-10 09:00</div>
                </label>
                <p className="text-[11px] text-muted-foreground">定时任务到点自动开始发送；到点前可在详情页修改时间或暂停</p>
              </div>
            </Card>
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-between border-t border-border px-6 py-4">
          <button className="h-9 rounded-md px-4 text-sm text-muted-foreground">取消</button>
          <button className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground">保存并继续</button>
        </div>
      </div>
    </EngagementShell>
  );
}
