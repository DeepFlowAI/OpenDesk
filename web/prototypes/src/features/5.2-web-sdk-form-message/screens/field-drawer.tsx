import { IconArrowLeft, IconSearch } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { AdminShell } from "../components/admin-shell";
import { ChannelTabs, SourceTag } from "../components/form-elements";
import { MessageSettings } from "../components/message-settings";
import { AVAILABLE_FIELDS } from "../fixtures";
import { ChannelEditorHeader } from "./channel-service";

function FieldDrawer() {
  return (
    <div className="absolute inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" />
      <aside className="relative z-10 flex h-full w-[560px] flex-col bg-white shadow-xl">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
          <div className="flex items-center gap-2"><IconArrowLeft size={20} className="text-muted-foreground" /><span className="text-base font-semibold">添加工单字段</span></div>
          <Button size="sm" className="px-5">添加 2 个字段</Button>
        </div>
        <div className="flex-1 p-8">
          <div className="flex h-10 items-center gap-2 rounded-lg border border-border px-3.5 text-sm text-muted-foreground">
            <IconSearch size={17} />
            <span>搜索字段名称</span>
          </div>
          <div className="mt-6 flex items-center justify-between">
            <div><h3 className="text-sm font-semibold">工单字段</h3><p className="mt-1 text-xs text-muted-foreground">仅展示启用且允许访客填写的字段</p></div>
            <span className="text-xs text-muted-foreground">4 个可添加</span>
          </div>
          <div className="mt-3 overflow-hidden rounded-lg border border-border">
            {AVAILABLE_FIELDS.map((field, index) => (
              <div key={field.key} className="flex min-h-16 items-center gap-3 border-b border-border px-4 last:border-b-0">
                <Checkbox defaultChecked={index < 2} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2"><span className="text-sm font-medium">{field.name}</span><SourceTag source={field.source} /></div>
                  <p className="mt-1 text-xs text-muted-foreground">{field.type} · 适用于工单</p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-5 rounded-lg bg-muted/50 px-4 py-3 text-xs leading-5 text-muted-foreground">
            用户、组织、受理人、负责组和系统生成字段不会出现在此处。本页只选择字段，不修改字段定义。
          </div>
        </div>
      </aside>
    </div>
  );
}

export function FieldDrawerScreen() {
  return (
    <div className="relative h-full">
      <AdminShell>
        <div className="flex h-full flex-col">
          <ChannelEditorHeader />
          <div className="flex-1 overflow-hidden p-8">
            <div className="flex w-[720px] flex-col gap-6 p-6"><ChannelTabs /><h3 className="text-base font-semibold">服务配置</h3><MessageSettings /></div>
          </div>
        </div>
      </AdminShell>
      <FieldDrawer />
    </div>
  );
}
