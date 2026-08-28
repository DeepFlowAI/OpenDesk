import type { ReactNode } from "react";
import { IconCheck, IconChevronDown, IconFileSpreadsheet, IconX } from "@tabler/icons-react";
import { TASK_TEMPLATE } from "../fixtures";
import { SmsTaskDetailScreen } from "./detail";

function DialogOverlay({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="relative h-full">
      <SmsTaskDetailScreen tab="targets" />
      <div className="absolute inset-0 flex items-center justify-center bg-black/30 p-8">
        <div className={`w-full ${wide ? "max-w-[720px]" : "max-w-[520px]"} rounded-xl border border-border bg-background shadow-2xl`}>
          {children}
        </div>
      </div>
    </div>
  );
}

function DialogHeader({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border px-5 py-4">
      <h2 className="text-base font-semibold">{title}</h2>
      <IconX size={18} className="text-muted-foreground" />
    </div>
  );
}

function DialogFooter({ primary }: { primary: string }) {
  return (
    <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
      <button className="h-9 rounded-md border border-border px-4 text-sm">取消</button>
      <button className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground">{primary}</button>
    </div>
  );
}

const IMPORT_STEPS = ["上传文件", "字段映射", "数据校验", "预览确认"];

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-2 px-5 pt-4">
      {IMPORT_STEPS.map((label, index) => {
        const done = index + 1 < current;
        const active = index + 1 === current;
        return (
          <div key={label} className="flex items-center gap-2">
            {index > 0 && <span className="mx-1 h-px w-8 bg-border" />}
            <span className={`grid h-5 w-5 place-items-center rounded-full text-[10px] font-semibold ${done ? "bg-emerald-100 text-emerald-700" : active ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>
              {done ? <IconCheck size={11} /> : index + 1}
            </span>
            <span className={`text-xs ${active ? "font-semibold" : "text-muted-foreground"}`}>{label}</span>
          </div>
        );
      })}
    </div>
  );
}

const MAPPING_ROWS = [
  { column: "手机号", target: "接收号码（必选）", sample: "13800138000", required: true },
  { column: "客户姓名", target: "变量 {name} · 客户姓名（必填）", sample: "王先生", required: true },
  { column: "回访时间", target: "变量 {time} · 预约时间（必填）", sample: "8月8日 14:00", required: true },
  { column: "备注", target: "不导入", sample: "VIP 客户", required: false },
];

export function SmsTaskImportScreen() {
  return (
    <DialogOverlay wide>
      <DialogHeader title="导入发送对象" />
      <StepBar current={2} />
      <div className="space-y-4 px-5 py-4">
        <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-3 py-2.5 text-sm">
          <IconFileSpreadsheet size={18} className="text-emerald-600" />
          <span>八月到期客户名单.xlsx</span>
          <span className="text-xs text-muted-foreground">共 2,846 行</span>
        </div>
        <div>
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">将文件列映射到接收号码与模板变量；必填变量必须映射</div>
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="grid grid-cols-[140px_1fr_140px] items-center gap-3 border-b border-border bg-muted/50 px-3 py-2 text-[11px] font-medium text-muted-foreground">
              <span>文件列</span><span>映射目标</span><span>示例值</span>
            </div>
            {MAPPING_ROWS.map((row) => (
              <div key={row.column} className="grid grid-cols-[140px_1fr_140px] items-center gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0">
                <span className="font-medium">{row.column}</span>
                <div className={`flex h-8 items-center justify-between rounded-md border px-2.5 text-[13px] ${row.target === "不导入" ? "border-border text-muted-foreground" : "border-border"}`}>
                  <span>{row.target}</span>
                  <IconChevronDown size={13} className="text-muted-foreground" />
                </div>
                <span className="truncate font-mono text-xs text-muted-foreground">{row.sample}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">任务内重复号码默认跳过；号码格式与必填变量将在下一步逐行校验。</p>
        </div>
      </div>
      <div className="flex items-center justify-between border-t border-border px-5 py-4">
        <button className="h-9 rounded-md px-4 text-sm text-muted-foreground">取消</button>
        <div className="flex items-center gap-2">
          <button className="h-9 rounded-md border border-border px-4 text-sm">上一步</button>
          <button className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground">下一步</button>
        </div>
      </div>
    </DialogOverlay>
  );
}

function FormInput({ placeholder, muted }: { placeholder: string; muted?: boolean }) {
  return (
    <div className={`flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm ${muted ? "text-muted-foreground" : ""}`}>
      {placeholder}
    </div>
  );
}

export function SmsTaskAddTargetScreen() {
  return (
    <DialogOverlay>
      <DialogHeader title="添加发送对象" />
      <div className="space-y-4 px-5 py-4">
        <div>
          <div className="mb-1.5 text-xs font-medium text-muted-foreground"><span className="mr-0.5 text-red-500">*</span>接收号码</div>
          <FormInput placeholder="请输入 11 位大陆手机号" muted />
        </div>
        {TASK_TEMPLATE.variables.map((variable) => (
          <div key={variable.key}>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">
              {variable.required && <span className="mr-0.5 text-red-500">*</span>}
              {variable.label}
              <span className="ml-1.5 font-mono text-[11px] text-muted-foreground">{`{${variable.key}}`}</span>
            </div>
            <FormInput placeholder={`请输入${variable.label}，不超过 ${variable.maxLength} 字`} muted />
          </div>
        ))}
        <div>
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">正文预览</div>
          <div className="rounded-lg border border-border bg-muted/30 px-3 py-3 text-sm leading-6 text-muted-foreground">
            <span className="font-medium text-foreground">【{TASK_TEMPLATE.signName}】</span>
            尊敬的<span className="rounded bg-amber-100 px-0.5 text-amber-800">{"{name}"}</span>，您预约的回访时间为<span className="rounded bg-amber-100 px-0.5 text-amber-800">{"{time}"}</span>，如需改期请回复本短信或致电客服。
          </div>
        </div>
      </div>
      <DialogFooter primary="添加" />
    </DialogOverlay>
  );
}

const PUBLISH_ROWS = [
  { label: "任务名称", value: "八月套餐到期提醒" },
  { label: "短信模板", value: "预约回访提醒（深流客服）" },
  { label: "发送对象数", value: "1,500" },
  { label: "发送时间", value: "立即发送" },
];

export function SmsTaskPublishConfirmScreen() {
  return (
    <DialogOverlay>
      <DialogHeader title="发布短信群发任务" />
      <div className="space-y-4 px-5 py-4">
        <p className="text-sm text-muted-foreground">确认发布以下任务？发布后系统将按发送时间自动发送，发送中可暂停。</p>
        <div className="rounded-lg border border-border">
          {PUBLISH_ROWS.map((row) => (
            <div key={row.label} className="grid grid-cols-[110px_1fr] gap-3 border-b border-border px-4 py-2.5 text-sm last:border-b-0">
              <span className="text-muted-foreground">{row.label}</span>
              <span className="font-medium">{row.value}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
        <button className="h-9 rounded-md border border-border px-4 text-sm">取消</button>
        <button className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground">确认发布</button>
      </div>
    </DialogOverlay>
  );
}
