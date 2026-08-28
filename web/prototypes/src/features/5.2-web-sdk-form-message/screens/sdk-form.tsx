import { IconChevronDown, IconPaperclip } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { DesktopSdkShell } from "../components/sdk-shell";

function FormControl({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm font-medium">{label}{required && <span className="ml-0.5 text-destructive">*</span>}</div>
      {children}
    </div>
  );
}

export function SdkFormScreen() {
  return (
    <DesktopSdkShell>
      <main className="flex-1 overflow-hidden bg-background">
        <div className="mx-auto w-full max-w-[560px] px-8 py-7">
          <div className="mb-6">
            <h2 className="text-xl font-semibold tracking-tight">请留下您的信息</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">请填写以下信息，我们会尽快与您联系。</p>
          </div>
          <div className="flex flex-col gap-5">
            <FormControl label="问题标题" required><div className="flex h-10 items-center rounded-lg border border-input px-3.5 text-sm text-muted-foreground">请简要概括您的问题</div></FormControl>
            <FormControl label="问题描述" required><div className="h-24 rounded-lg border border-input px-3.5 py-2.5 text-sm text-muted-foreground">请详细描述问题现象、发生时间和期望结果</div></FormControl>
            <FormControl label="问题类型" required><div className="flex h-10 items-center justify-between rounded-lg border border-input px-3.5 text-sm"><span>产品使用咨询</span><IconChevronDown size={16} className="text-muted-foreground" /></div></FormControl>
            <FormControl label="联系邮箱"><div className="flex h-10 items-center rounded-lg border border-input px-3.5 text-sm">yaoguang@example.com</div><p className="text-xs text-muted-foreground">仅保存到本工单，不会修改当前 Web SDK 用户资料。</p></FormControl>
            <FormControl label="相关附件"><div className="flex h-16 items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-muted/20 text-sm text-muted-foreground"><IconPaperclip size={17} />点击或拖拽上传附件</div></FormControl>
            <Button className="mt-1 h-10 w-full">提交</Button>
          </div>
        </div>
      </main>
    </DesktopSdkShell>
  );
}
