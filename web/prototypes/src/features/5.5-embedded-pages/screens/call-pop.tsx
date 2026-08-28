import type { ReactNode } from "react";
import {
  IconArrowsExchange,
  IconMicrophone,
  IconPhoneCall,
  IconPhoneOff,
  IconPlayerPause,
} from "@tabler/icons-react";
import { CallShell } from "../components/call-shell";

function Field({ label, value, strong, color }: { label: string; value: string; strong?: boolean; color?: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-sm ${strong ? "font-semibold" : ""} ${color ?? ""}`}>{value}</div>
    </div>
  );
}

function Row({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2 last:border-b-0">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className={`min-w-0 truncate text-right text-sm font-medium ${valueClass ?? ""}`}>{value}</span>
    </div>
  );
}

function OnCallBar() {
  return (
    <div className="flex shrink-0 items-center gap-6 border-b-2 border-green-200 bg-green-50 px-5 py-[18px]">
      <div className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-green-100">
          <IconPhoneCall size={16} className="text-green-700" />
        </span>
        <span className="font-bold text-green-800">通话中</span>
      </div>
      <Field label="通话类型" value="呼入" />
      <Field label="用户号码" value="138 0013 8000" strong />
      <Field label="服务号码" value="0755-8655 0123" />
      <Field label="通话时长" value="01:42" strong color="text-green-700" />
      <div className="ml-auto flex items-center gap-2">
        <button className="grid h-8 w-8 place-items-center rounded-md text-foreground/80" title="静音"><IconMicrophone size={16} /></button>
        <button className="grid h-8 w-8 place-items-center rounded-md text-foreground/80" title="保持"><IconPlayerPause size={16} /></button>
        <button className="inline-flex h-8 items-center gap-1 rounded-md border border-border bg-background/60 px-2 text-xs" title="转接"><IconArrowsExchange size={14} />转接</button>
        <button className="grid h-9 w-9 place-items-center rounded-full bg-red-500 text-white" title="挂断"><IconPhoneOff size={16} /></button>
      </div>
    </div>
  );
}

type PopTab = "system" | "orders";

/** Top-left segmented tab bar above the whole screen-pop area. */
function PopTabBar({ active }: { active: PopTab }) {
  const tabs: { key: PopTab; label: string }[] = [
    { key: "system", label: "系统弹屏" },
    { key: "orders", label: "订单查询" },
  ];
  return (
    <div className="flex shrink-0 items-center gap-3">
      <div className="flex rounded-md border border-border bg-background p-0.5">
        {tabs.map(({ key, label }) => (
          <div
            key={key}
            className={`rounded px-3 py-1.5 text-xs font-medium ${
              key === active ? "bg-primary text-primary-foreground" : "text-muted-foreground"
            }`}
          >
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

function ReviewNote({ children }: { children: ReactNode }) {
  return (
    <div className="shrink-0 rounded-lg border border-dashed border-amber-300 bg-amber-50/60 px-3 py-2 text-[11px] leading-4 text-amber-800">
      {children}
    </div>
  );
}

function SystemPopGrid() {
  return (
    <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-3">
      <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5">
        <h3 className="shrink-0 border-b border-border pb-2 text-sm font-semibold">通话信息</h3>
        <div className="mt-3 min-h-0 flex-1 space-y-0.5 overflow-y-auto text-sm">
          <Row label="通话类型" value="呼入" />
          <Row label="用户号码" value="138 0013 8000" />
          <Row label="服务号码" value="0755-8655 0123" />
          <Row label="队列" value="售后客服组" />
          <Row label="开始时间" value="2026-08-07 14:26:03" />
          <Row label="通话时长" value="01:42" valueClass="text-green-700" />
          <Row label="用户关联状态" value="已关联用户" valueClass="text-emerald-700" />
        </div>
        <div className="mt-4 shrink-0 rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
          实时转写区域（沿用现网）
        </div>
      </section>

      <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5">
        <h3 className="shrink-0 border-b border-border pb-2 text-sm font-semibold">用户信息</h3>
        <div className="mt-3 min-h-0 flex-1 space-y-0.5 overflow-y-auto text-sm">
          <Row label="姓名" value="王女士" />
          <Row label="手机号" value="138 0013 8000" />
          <Row label="客户等级" value="VIP 客户" />
          <Row label="所属组织" value="星海科技有限公司" />
          <Row label="套餐到期" value="2026-08-31" />
        </div>
      </section>

      <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5">
        <div className="mb-3 flex shrink-0 items-center border-b border-border pb-2">
          <div className="flex shrink-0 rounded-md border border-border bg-muted p-0.5">
            <div className="rounded bg-white px-2 py-1 text-xs font-medium text-foreground shadow-sm">通话纪要</div>
            <div className="rounded px-2 py-1 text-xs font-medium text-muted-foreground">新建工单</div>
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">备注</div>
            <div className="h-9 rounded-md border border-border" />
          </div>
          <div>
            <div className="mb-1.5 text-xs text-muted-foreground">问题分类</div>
            <div className="h-9 rounded-md border border-border" />
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">通话纪要字段沿用现网配置</div>
        </div>
      </section>
    </div>
  );
}

/** Static mock of the third-party order page rendered inside the iframe. */
function OrdersIframeMock() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-[#F7F8FA]">
      <div className="flex shrink-0 items-center justify-between bg-[#1F2D3D] px-5 py-3">
        <span className="text-sm font-semibold text-white">ACME CRM · 订单查询</span>
        <span className="rounded bg-white/10 px-2 py-0.5 text-[11px] text-white/80">已按号码 138 0013 8000 查询</span>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        <div className="flex items-center gap-6 rounded-lg border border-[#E5E9F0] bg-white px-4 py-3 text-xs">
          <span className="font-semibold text-[#1F2D3D]">王女士</span>
          <span className="text-[#8A94A6]">VIP 客户</span>
          <span className="text-[#8A94A6]">累计 12 笔订单</span>
          <span className="text-[#8A94A6]">近 90 天 3 笔</span>
        </div>
        <div className="overflow-hidden rounded-lg border border-[#E5E9F0] bg-white">
          <table className="w-full text-xs">
            <thead className="bg-[#F0F2F5] text-left text-[#8A94A6]">
              <tr>
                <th className="px-4 py-2.5 font-medium">订单号</th>
                <th className="px-4 py-2.5 font-medium">商品</th>
                <th className="px-4 py-2.5 font-medium">金额</th>
                <th className="px-4 py-2.5 font-medium">状态</th>
                <th className="px-4 py-2.5 font-medium">下单时间</th>
              </tr>
            </thead>
            <tbody>
              {[
                { id: "AC20260731008", goods: "云主机标准版 · 年付", amount: "¥1,299.00", status: "配送中", tone: "text-sky-600", time: "2026-07-31 10:21" },
                { id: "AC20260615021", goods: "对象存储 500G 扩容包", amount: "¥399.00", status: "已完成", tone: "text-[#8A94A6]", time: "2026-06-15 16:40" },
                { id: "AC20260402007", goods: "企业版续费 · 50 坐席", amount: "¥23,800.00", status: "已完成", tone: "text-[#8A94A6]", time: "2026-04-02 09:12" },
                { id: "AC20251230116", goods: "云数据库 MySQL 高可用版", amount: "¥6,600.00", status: "已完成", tone: "text-[#8A94A6]", time: "2025-12-30 14:05" },
              ].map((order) => (
                <tr key={order.id} className="border-t border-[#F0F2F5]">
                  <td className="px-4 py-3 font-mono text-[#1F2D3D]">{order.id}</td>
                  <td className="px-4 py-3 text-[#1F2D3D]">{order.goods}</td>
                  <td className="px-4 py-3 text-[#1F2D3D]">{order.amount}</td>
                  <td className={`px-4 py-3 ${order.tone}`}>{order.status}</td>
                  <td className="px-4 py-3 text-[#8A94A6]">{order.time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function CallPopSystemScreen() {
  return (
    <CallShell phase="on_call">
      <div className="flex h-full flex-col">
        <OnCallBar />
        <div className="flex min-h-0 flex-1 flex-col gap-4 bg-muted p-5">
          <PopTabBar active="system" />
          <ReviewNote>
            弹屏 Tab 条位于整个弹屏区左上角；「系统弹屏」为固定首个 Tab，内容即现有三列卡片
          </ReviewNote>
          <SystemPopGrid />
        </div>
      </div>
    </CallShell>
  );
}

export function CallPopEmbeddedScreen() {
  return (
    <CallShell phase="on_call">
      <div className="flex h-full flex-col">
        <OnCallBar />
        <div className="flex min-h-0 flex-1 flex-col gap-4 bg-muted p-5">
          <PopTabBar active="orders" />
          <ReviewNote>
            嵌入 Tab 激活时整区渲染第三方页面；iframe URL 变量已按当前通话替换：…/pop?phone=13800138000&call_id=88213；本页为默认聚焦页面，新来电弹屏时自动激活
          </ReviewNote>
          <OrdersIframeMock />
        </div>
      </div>
    </CallShell>
  );
}
