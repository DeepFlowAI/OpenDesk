import type { ReactNode } from "react";
import {
  IconAddressBook,
  IconBook2,
  IconBrandWechat,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconMoodSmile,
  IconPaperclip,
  IconPhone,
  IconSearch,
  IconSend,
  IconSettings,
  IconTicket,
  IconWorld,
} from "@tabler/icons-react";

const PRIMARY_NAV = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle, active: true },
  { label: "呼叫", icon: IconPhone },
  { label: "触达", icon: IconSend },
  { label: "历史", icon: IconHistory },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
];

const CONVERSATIONS = [
  { name: "张伟", preview: "好的，我这边再确认一下订单状态", time: "14:32", channel: "wechat" as const, unread: 2, active: true },
  { name: "李芳", preview: "请问发票什么时候能开出来？", time: "13:58", channel: "web" as const, unread: 0, active: false },
  { name: "王强", preview: "物流显示签收了但我没收到", time: "11:20", channel: "wechat" as const, unread: 0, active: false },
  { name: "陈晨", preview: "会员积分怎么兑换？", time: "昨天", channel: "web" as const, unread: 0, active: false },
];

const MESSAGES = [
  { from: "visitor" as const, text: "你好，我想查一下上周五下的订单现在什么状态", time: "14:28" },
  { from: "agent" as const, text: "您好，请提供一下订单号，我马上为您查询", time: "14:29" },
  { from: "visitor" as const, text: "AC20260731008", time: "14:30" },
  { from: "agent" as const, text: "收到，正在查询，请稍等", time: "14:31" },
  { from: "visitor" as const, text: "好的，我这边再确认一下订单状态", time: "14:32" },
];

/**
 * Mirrors production chat workspace `/workspace/chat`:
 * 64px icon nav → 280px conversation list → message panel → auxiliary panel.
 * See `web/app/workspace/chat/page.tsx` and `components/features/chat/auxiliary-panel.tsx`.
 */
export function ChatShell({ auxiliaryPanel }: { auxiliaryPanel: ReactNode }) {
  return (
    <div className="flex h-full bg-background text-foreground">
      <aside className="relative z-30 flex w-16 shrink-0 flex-col justify-between border-r border-[#E5E5E5] bg-[#F5F5F5] py-4">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-full items-center justify-center">
            <IconHeadset size={28} className="text-[#1a1a1a]" />
          </div>
          <nav className="flex w-full flex-col items-center gap-1">
            {PRIMARY_NAV.map(({ label, icon: ItemIcon, active }) => (
              <div
                key={label}
                className={`flex h-11 w-11 items-center justify-center rounded-lg ${active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"}`}
              >
                <ItemIcon size={20} stroke={1.7} />
              </div>
            ))}
          </nav>
        </div>
        <div className="flex flex-col items-center gap-2">
          <div className="grid h-10 w-10 place-items-center rounded-lg text-muted-foreground"><IconSettings size={20} /></div>
          <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">张</span>
        </div>
      </aside>

      <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-background">
        <div className="border-b border-border p-3">
          <div className="flex h-9 items-center gap-2 rounded-md border border-border px-3">
            <IconSearch size={15} className="text-muted-foreground" />
            <span className="text-sm text-muted-foreground">搜索会话</span>
          </div>
          <div className="mt-2 flex gap-1 text-xs">
            <span className="rounded-md bg-muted px-2.5 py-1 font-medium">全部(4)</span>
            <span className="px-2.5 py-1 text-muted-foreground">我处理的(2)</span>
            <span className="px-2.5 py-1 text-muted-foreground">未分配(1)</span>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {CONVERSATIONS.map((item) => (
            <div
              key={item.name}
              className={`mb-1 rounded-lg px-3 py-2.5 ${item.active ? "bg-muted" : ""}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">
                    {item.name.slice(0, 1)}
                  </span>
                  <span className="text-sm font-medium">{item.name}</span>
                  {item.channel === "wechat" ? (
                    <IconBrandWechat size={14} className="text-emerald-600" />
                  ) : (
                    <IconWorld size={14} className="text-sky-600" />
                  )}
                </div>
                <span className="text-[11px] text-muted-foreground">{item.time}</span>
              </div>
              <div className="mt-1 flex items-center justify-between pl-10">
                <span className="truncate text-xs text-muted-foreground">{item.preview}</span>
                {item.unread > 0 && (
                  <span className="ml-2 grid h-4 min-w-4 place-items-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
                    {item.unread}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">张伟</span>
            <span className="flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700">
              <IconBrandWechat size={12} />
              微信
            </span>
            <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">会话中</span>
          </div>
          <span className="text-xs text-muted-foreground">接入于 14:26 · 队列：在线客服组</span>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-muted/30 px-6 py-4">
          {MESSAGES.map((message, index) => (
            <div key={index} className={`flex ${message.from === "agent" ? "justify-end" : ""}`}>
              <div className={`max-w-[70%] ${message.from === "agent" ? "text-right" : ""}`}>
                <div
                  className={`inline-block rounded-xl px-3.5 py-2.5 text-sm leading-5 ${
                    message.from === "agent"
                      ? "bg-primary text-primary-foreground"
                      : "border border-border bg-background"
                  }`}
                >
                  {message.text}
                </div>
                <div className="mt-1 text-[10px] text-muted-foreground">{message.time}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="shrink-0 border-t border-border">
          <div className="flex items-center gap-3 px-4 pt-2 text-muted-foreground">
            <IconMoodSmile size={18} />
            <IconPaperclip size={18} />
          </div>
          <div className="px-4 py-2">
            <div className="min-h-16 text-sm text-muted-foreground">输入回复内容…</div>
          </div>
          <div className="flex items-center justify-end gap-2 px-4 pb-3">
            <button className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground">
              <IconSend size={14} />
              发送
            </button>
          </div>
        </div>
      </section>

      <aside className="flex w-[360px] shrink-0 flex-col border-l border-border bg-background">
        {auxiliaryPanel}
      </aside>
    </div>
  );
}
