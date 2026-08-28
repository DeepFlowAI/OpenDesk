import type { ReactNode } from "react";
import { IconExternalLink } from "@tabler/icons-react";
import { ChatShell } from "../components/chat-shell";

type AuxTab = "basic" | "knowledge" | "member" | "reminder";

const TABS: { key: AuxTab; label: string }[] = [
  { key: "basic", label: "基本信息" },
  { key: "knowledge", label: "知识库" },
  { key: "member", label: "会员档案" },
  { key: "reminder", label: "服务提醒" },
];

/** Matches production auxiliary tab bar styles in auxiliary-panel.tsx. */
function AuxTabBar({ active }: { active: AuxTab }) {
  return (
    <div className="mx-5 mb-4 mt-5 flex shrink-0 rounded-lg border border-border bg-background p-0.5">
      {TABS.map(({ key, label }) => (
        <div
          key={key}
          className={`flex-1 rounded-md px-3 py-1.5 text-center text-xs font-medium ${
            key === active ? "bg-primary text-primary-foreground" : "text-muted-foreground"
          }`}
        >
          {label}
        </div>
      ))}
    </div>
  );
}

/** Review annotation, not part of the product UI. */
function ReviewNote({ children }: { children: ReactNode }) {
  return (
    <div className="mx-5 mb-4 shrink-0 rounded-lg border border-dashed border-amber-300 bg-amber-50/60 px-3 py-2 text-[11px] leading-4 text-amber-800">
      {children}
    </div>
  );
}

/** Static mock of the third-party CRM page rendered inside the iframe. */
function MemberProfileIframeMock() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-t border-border bg-[#F7F8FA]">
      <div className="flex shrink-0 items-center justify-between bg-[#1F2D3D] px-4 py-2.5">
        <span className="text-xs font-semibold text-white">ACME CRM · 会员档案</span>
        <IconExternalLink size={13} className="text-white/60" />
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        <div className="rounded-lg border border-[#E5E9F0] bg-white p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-[#1F2D3D]">张伟</span>
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">钻石会员</span>
          </div>
          <div className="mt-2.5 grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-[#8A94A6]">积分</div>
              <div className="mt-0.5 font-semibold text-[#1F2D3D]">12,580</div>
            </div>
            <div>
              <div className="text-[#8A94A6]">注册时间</div>
              <div className="mt-0.5 font-semibold text-[#1F2D3D]">2023-05-12</div>
            </div>
            <div>
              <div className="text-[#8A94A6]">累计消费</div>
              <div className="mt-0.5 font-semibold text-[#1F2D3D]">¥46,230</div>
            </div>
            <div>
              <div className="text-[#8A94A6]">最近登录</div>
              <div className="mt-0.5 font-semibold text-[#1F2D3D]">2026-08-06</div>
            </div>
          </div>
        </div>
        <div className="rounded-lg border border-[#E5E9F0] bg-white p-3.5">
          <div className="mb-2 text-xs font-semibold text-[#1F2D3D]">最近订单</div>
          {[
            { id: "AC20260731008", amount: "¥1,299.00", status: "配送中" },
            { id: "AC20260615021", amount: "¥399.00", status: "已完成" },
          ].map((order) => (
            <div key={order.id} className="flex items-center justify-between border-t border-[#F0F2F5] py-2 text-xs first:border-t-0">
              <span className="font-mono text-[#1F2D3D]">{order.id}</span>
              <span className="text-[#8A94A6]">{order.amount}</span>
              <span className={order.status === "配送中" ? "text-sky-600" : "text-[#8A94A6]"}>{order.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Static mock of the custom panel rendered by admin-configured React code. */
function ReminderReactMock() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden border-t border-border bg-background">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        <div className="text-sm font-semibold">服务提醒</div>
        <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          当前访客：张伟（微信渠道）
        </div>
        {[
          { label: "SLA 承诺", desc: "钻石会员 · 4 小时响应" },
          { label: "高频问题", desc: "会员积分 / 发票 / 退换货" },
        ].map((item) => (
          <div key={item.label} className="flex items-center justify-between rounded-lg border border-border px-3 py-2.5">
            <div>
              <div className="text-sm font-medium">{item.label}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">{item.desc}</div>
            </div>
            <IconExternalLink size={15} className="text-muted-foreground" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChatAuxIframeScreen() {
  return (
    <ChatShell
      auxiliaryPanel={
        <>
          <AuxTabBar active="member" />
          <ReviewNote>
            嵌入 Tab 追加在知识库之后，按排序值升序；本页为 iframe 类型，URL 变量已替换：…/member?visitor_id=98213
          </ReviewNote>
          <MemberProfileIframeMock />
        </>
      }
    />
  );
}

export function ChatAuxReactScreen() {
  return (
    <ChatShell
      auxiliaryPanel={
        <>
          <AuxTabBar active="reminder" />
          <ReviewNote>
            本页为 React 代码类型：运行时注入 context / config / api，上方面板由管理员配置的代码渲染
          </ReviewNote>
          <ReminderReactMock />
        </>
      }
    />
  );
}
