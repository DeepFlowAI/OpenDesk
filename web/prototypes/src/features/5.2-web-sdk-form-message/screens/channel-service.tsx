import { IconArrowLeft } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { AdminShell } from "../components/admin-shell";
import { MessageSettings } from "../components/message-settings";

function ChannelEditorHeader() {
  return (
    <div className="flex h-14 items-center justify-between border-b border-border bg-white px-6">
      <div className="flex items-center gap-2">
        <IconArrowLeft size={20} className="text-muted-foreground" />
        <span className="text-base font-semibold">编辑：官网在线咨询</span>
      </div>
      <Button className="px-5">保存</Button>
    </div>
  );
}

export function ChannelServiceScreen() {
  return (
    <AdminShell>
      <div className="flex h-full flex-col">
        <ChannelEditorHeader />
        <div className="flex-1 overflow-hidden px-8 pb-8 pt-5">
          <div className="flex w-[720px] flex-col p-6">
            <MessageSettings />
          </div>
        </div>
      </div>
    </AdminShell>
  );
}

export { ChannelEditorHeader };
