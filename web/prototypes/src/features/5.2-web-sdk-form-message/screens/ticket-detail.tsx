import { IconArrowLeft, IconHeadset, IconMessageCircle, IconPhone, IconSettings, IconTicket } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { TICKET_NUMBER } from "../fixtures";

function WorkspaceRail() {
  return (
    <aside className="flex w-16 shrink-0 flex-col justify-between border-r border-[#E5E5E5] bg-[#F5F5F5] py-4">
      <div className="flex flex-col items-center gap-4">
        <div className="flex h-12 items-center justify-center"><IconHeadset size={28} /></div>
        <nav className="flex flex-col gap-1">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#E5E5E5]"><IconTicket size={22} /></div>
          <div className="flex h-11 w-11 items-center justify-center text-[#999]"><IconMessageCircle size={22} /></div>
          <div className="flex h-11 w-11 items-center justify-center text-[#999]"><IconPhone size={22} /></div>
        </nav>
      </div>
      <div className="flex h-11 items-center justify-center text-[#999]"><IconSettings size={22} /></div>
    </aside>
  );
}

function SnapshotField({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-sm leading-5 text-foreground">{value}</dd></div>;
}

export function TicketDetailScreen() {
  return (
    <div className="prototype-frame flex bg-white">
      <WorkspaceRail />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-end border-b border-border bg-white px-6">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">李</div>
        </header>
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-border px-6 py-4">
            <div className="flex items-center gap-3.5"><IconArrowLeft size={20} /><h2 className="text-lg font-semibold">账号无法完成企业认证</h2><span className="rounded-md bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">{TICKET_NUMBER}</span></div>
            <Button className="h-9 px-5">保存</Button>
          </div>
          <div className="flex min-h-0 flex-1 overflow-hidden">
            <main className="w-[800px] shrink-0 overflow-hidden px-6 py-[18px]">
              <div className="rounded-lg border border-border">
                <div className="border-b border-border px-4 py-3 text-sm font-semibold">工单基础信息</div>
                <dl className="grid grid-cols-2 gap-x-8 gap-y-5 p-4"><SnapshotField label="状态" value="待处理" /><SnapshotField label="优先级" value="普通" /><SnapshotField label="关联用户" value="匿名访客 #V-8F31A2" /><SnapshotField label="负责组" value="售后支持组" /></dl>
              </div>
              <div className="mt-[18px] rounded-lg border border-border">
                <div className="flex items-center justify-between border-b border-border px-4 py-3"><div><div className="text-sm font-semibold">表单留言信息</div><div className="mt-1 text-xs text-muted-foreground">提交快照 · 不随字段定义或工单后续修改而变化</div></div><span className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground">Web SDK 表单</span></div>
                <div className="grid grid-cols-3 gap-5 border-b border-border bg-muted/25 px-4 py-3"><SnapshotField label="来源渠道" value="官网在线咨询" /><SnapshotField label="提交时间" value="2026-08-04 14:32" /><SnapshotField label="来源会话" value="C-20260804-217" /></div>
                <dl className="grid grid-cols-2 gap-x-8 gap-y-5 p-4"><SnapshotField label="问题标题" value="账号无法完成企业认证" /><SnapshotField label="问题类型" value="账号与认证" /><SnapshotField label="问题描述" value="上传营业执照后一直提示识别失败，已尝试 PNG 和 JPG 格式。" /><SnapshotField label="联系邮箱" value="yaoguang@example.com" /><SnapshotField label="相关附件" value="营业执照.png · 1.8 MB" /></dl>
              </div>
            </main>
            <aside className="flex min-w-0 flex-1 flex-col border-l border-border bg-[#f5f5f5]">
              <div className="flex gap-4 px-5 pt-1"><span className="border-b-2 border-foreground pb-3 pt-2 text-xs font-semibold">评论</span><span className="pb-3 pt-2 text-xs text-muted-foreground">变更记录</span><span className="pb-3 pt-2 text-xs text-muted-foreground">全部</span></div>
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">暂无评论</div>
              <div className="m-5 rounded-lg border border-border bg-white px-3 py-3 text-sm text-muted-foreground">添加评论…</div>
            </aside>
          </div>
        </div>
      </div>
    </div>
  );
}
