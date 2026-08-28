import { IconGripVertical, IconInfoCircle, IconPlus, IconTrash } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { FORM_FIELDS } from "../fixtures";
import { FieldLabel, Segmented, SourceTag, StaticInput, StaticTextarea } from "./form-elements";

function FieldRows() {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-white">
      <div className="grid h-9 grid-cols-[30px_minmax(140px,1fr)_96px_116px_32px] items-center gap-2 border-b border-border bg-muted/40 px-3 text-xs font-medium text-muted-foreground">
        <span />
        <span>工单字段</span>
        <span>类型</span>
        <span>填写要求</span>
        <span />
      </div>
      {FORM_FIELDS.map((field) => (
        <div
          key={field.key}
          className="grid min-h-12 grid-cols-[30px_minmax(140px,1fr)_96px_116px_32px] items-center gap-2 border-b border-border px-3 py-2 last:border-b-0"
        >
          <IconGripVertical size={16} className="text-muted-foreground" />
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-sm font-medium">{field.name}</span>
            <SourceTag source={field.source} />
          </div>
          <span className="text-xs text-muted-foreground">{field.type}</span>
          <div className="flex rounded-md bg-muted p-0.5 text-xs">
            <span className={`flex-1 rounded px-2 py-1 text-center ${field.required ? "bg-white font-medium shadow-sm" : "text-muted-foreground"}`}>必填</span>
            <span className={`flex-1 rounded px-2 py-1 text-center ${!field.required ? "bg-white font-medium shadow-sm" : "text-muted-foreground"}`}>选填</span>
          </div>
          <IconTrash size={15} className="text-muted-foreground" />
        </div>
      ))}
    </div>
  );
}

export function MessageSettings() {
  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <FieldLabel required>留言方式</FieldLabel>
          <Segmented selected="表单留言" options={["会话留言", "表单留言"]} />
          <p className="text-xs leading-5 text-muted-foreground">留言入口命中后，只会展示当前选择的一种方式。切换不会转换历史留言或工单。</p>
        </div>

        <div className="h-px bg-border" />

        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-2">
            <FieldLabel required>表单标题</FieldLabel>
            <StaticInput value="请留下您的信息" />
          </div>
          <div className="flex flex-col gap-2">
            <FieldLabel required>提交按钮文案</FieldLabel>
            <StaticInput value="提交" />
          </div>
        </div>
        <div className="flex flex-col gap-2">
          <FieldLabel>表单说明</FieldLabel>
          <StaticTextarea value="请填写以下信息，我们会尽快与您联系。" height="h-16" />
        </div>

        <div className="flex items-center justify-between">
          <div>
            <FieldLabel required>工单字段</FieldLabel>
            <p className="mt-1 text-xs text-muted-foreground">访客侧按以下顺序展示；至少一个字段，且至少一个必填。</p>
          </div>
          <Button variant="outline" size="sm"><IconPlus size={15} />添加字段</Button>
        </div>
        <FieldRows />

        <div className="flex gap-2 rounded-lg border border-info/25 bg-info/5 px-3.5 py-3 text-xs leading-5 text-muted-foreground">
          <IconInfoCircle size={17} className="mt-0.5 shrink-0 text-info" />
          <span>表单工单将关联当前 Web SDK 用户。若网站已通过签名上下文传入客户信息，则关联该客户；否则关联当前匿名访客。</span>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-2"><FieldLabel required>成功标题</FieldLabel><StaticInput value="提交成功" /></div>
          <div className="flex items-center justify-between rounded-lg border border-border px-3.5 py-2">
            <div><div className="text-sm font-medium">展示工单编号</div><div className="text-xs text-muted-foreground">成功页向访客展示</div></div>
            <Switch defaultChecked />
          </div>
        </div>
      </div>
    </section>
  );
}
