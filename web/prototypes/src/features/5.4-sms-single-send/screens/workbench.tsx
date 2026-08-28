import { IconChevronDown, IconX } from "@tabler/icons-react";
import { CallShell } from "../components/call-shell";
import { SMS_TEMPLATES } from "../fixtures";

function AuxPlaceholder() {
  return (
    <div className="flex h-full gap-4 p-5">
      <section className="flex-1 rounded-xl border border-border bg-white p-5">
        <h3 className="text-sm font-semibold">通话信息</h3>
        <p className="mt-3 text-xs text-muted-foreground">弹屏区沿用现网；本期不改布局。</p>
      </section>
      <section className="flex-1 rounded-xl border border-border bg-white p-5">
        <h3 className="text-sm font-semibold">用户信息</h3>
        <p className="mt-3 text-xs text-muted-foreground">13800138000 · 王先生</p>
      </section>
      <section className="flex-1 rounded-xl border border-border bg-white p-5">
        <h3 className="text-sm font-semibold">通话纪要</h3>
        <p className="mt-3 text-xs text-muted-foreground">整理态 / 通话中填写区</p>
      </section>
    </div>
  );
}

export function WorkbenchIdleScreen() {
  return (
    <CallShell phase="idle" dialNumber="13800138000">
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        空闲态 · 拨号区右侧新增短信图标按钮
      </div>
    </CallShell>
  );
}

export function WorkbenchOnCallScreen() {
  return (
    <CallShell phase="on_call">
      <AuxPlaceholder />
    </CallShell>
  );
}

export function SendSmsDialogScreen({ phase = "idle" }: { phase?: "idle" | "on_call" }) {
  const template = SMS_TEMPLATES[0];
  const phoneReadonly = phase === "on_call";

  return (
    <div className="relative h-full">
      <CallShell phase={phase} dialNumber="13800138000">
        {phase === "on_call" ? <AuxPlaceholder /> : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            空闲态拨号后打开发送短信弹窗
          </div>
        )}
      </CallShell>
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 p-8">
        <div className="w-full max-w-[520px] rounded-xl border border-border bg-background shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="text-base font-semibold">发送短信</h2>
            <IconX size={18} className="text-muted-foreground" />
          </div>
          <div className="space-y-4 px-5 py-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                接收号码{phoneReadonly ? "" : " *"}
              </label>
              <div
                className={`flex h-10 items-center rounded-md border border-border px-3 font-mono text-sm ${
                  phoneReadonly ? "bg-muted/40 text-foreground" : "bg-background"
                }`}
              >
                13800138000
              </div>
              {phoneReadonly ? (
                <p className="mt-1 text-[11px] text-muted-foreground">通话中取当前用户号码，只读</p>
              ) : null}
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">短信模板 *</label>
              <div className="flex h-10 items-center justify-between rounded-md border border-border px-3 text-sm">
                <span>
                  {template.name}
                  <span className="ml-1 text-muted-foreground">（{template.signName}）</span>
                </span>
                <IconChevronDown size={14} className="text-muted-foreground" />
              </div>
            </div>

            {template.variables.map((variable) => (
              <div key={variable.key}>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  {variable.label}
                  {variable.required ? " *" : ""}
                </label>
                <div className="flex h-10 items-center rounded-md border border-border px-3 text-sm">
                  {variable.sample}
                </div>
              </div>
            ))}

            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">正文预览</div>
              <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
                【{template.signName}】尊敬的王先生，您预约的回访时间为8月8日 14:00，如需改期请回复本短信或致电客服。
              </div>
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
            <button className="h-9 rounded-md border border-border px-4 text-sm">取消</button>
            <button className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground">发送</button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function SendSmsValidationErrorScreen() {
  const template = SMS_TEMPLATES[0];
  return (
    <div className="relative h-full">
      <CallShell phase="idle" dialNumber="13800138000">
        <div className="flex h-full items-center justify-center text-sm text-muted-foreground">变量未填完</div>
      </CallShell>
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 p-8">
        <div className="w-full max-w-[520px] rounded-xl border border-border bg-background shadow-2xl">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="text-base font-semibold">发送短信</h2>
            <IconX size={18} className="text-muted-foreground" />
          </div>
          <div className="space-y-4 px-5 py-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">接收号码 *</label>
              <div className="flex h-10 items-center rounded-md border border-border px-3 font-mono text-sm">
                13800138000
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">短信模板 *</label>
              <div className="flex h-10 items-center justify-between rounded-md border border-border px-3 text-sm">
                <span>
                  {template.name}
                  <span className="ml-1 text-muted-foreground">（{template.signName}）</span>
                </span>
                <IconChevronDown size={14} className="text-muted-foreground" />
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">客户姓名 *</label>
              <div className="flex h-10 items-center rounded-md border border-border px-3 text-sm">王先生</div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-red-600">预约时间 *</label>
              <div className="flex h-10 items-center rounded-md border border-red-400 px-3 text-sm text-muted-foreground">
                请填写预约时间
              </div>
              <p className="mt-1 text-xs text-red-600">请填写预约时间</p>
            </div>
            <div>
              <div className="mb-1.5 text-xs font-medium text-muted-foreground">正文预览</div>
              <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 text-sm leading-6">
                【{template.signName}】尊敬的王先生，您预约的回访时间为{"{time}"}，如需改期请回复本短信或致电客服。
              </div>
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
            <button className="h-9 rounded-md border border-border px-4 text-sm">取消</button>
            <button className="h-9 rounded-md bg-primary/60 px-4 text-sm font-medium text-primary-foreground">发送</button>
          </div>
        </div>
      </div>
    </div>
  );
}
