import type { ReactNode } from "react"
import {
  IconAddressBook,
  IconBook2,
  IconChartBar,
  IconHeadset,
  IconHistory,
  IconInbox,
  IconMessageCircle,
  IconPhone,
  IconSearch,
  IconSend,
  IconSettings,
  IconTicket,
} from "@tabler/icons-react"
import { CALL_RECORDS } from "../fixtures"

const PRIMARY_NAV = [
  { label: "工单", icon: IconTicket },
  { label: "在线", icon: IconMessageCircle },
  { label: "呼叫", icon: IconPhone },
  { label: "触达", icon: IconSend },
  { label: "服务运营", icon: IconHistory, active: true },
  { label: "通讯录", icon: IconAddressBook },
  { label: "知识库", icon: IconBook2 },
]

const RECORD_NAV = [
  { label: "在线监控", icon: IconChartBar },
  { label: "会话记录", icon: IconMessageCircle },
  { label: "留言记录", icon: IconInbox },
  { label: "呼叫监控", icon: IconHeadset },
  { label: "通话记录", icon: IconPhone, active: true },
  { label: "通话报表", icon: IconChartBar },
]

export function RecordsBackdrop({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex h-full bg-background text-foreground">
      <aside className="flex w-16 shrink-0 flex-col justify-between border-r border-[#e5e5e5] bg-[#f5f5f5] py-4">
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-12 w-full items-center justify-center">
            <IconHeadset size={28} className="text-[#1a1a1a]" />
          </div>
          <nav className="flex w-full flex-col items-center gap-1">
            {PRIMARY_NAV.map(({ label, icon: ItemIcon, active }) => (
              <div
                key={label}
                className={`flex h-11 w-11 items-center justify-center rounded-lg ${active ? "bg-background text-foreground shadow-sm" : "text-muted-foreground"}`}
                title={label}
              >
                <ItemIcon size={20} stroke={1.7} />
              </div>
            ))}
          </nav>
        </div>
        <div className="flex flex-col items-center gap-2">
          <div className="grid h-10 w-10 place-items-center rounded-lg text-muted-foreground">
            <IconSettings size={20} />
          </div>
          <span className="grid h-8 w-8 place-items-center rounded-full bg-secondary text-xs font-semibold">张</span>
        </div>
      </aside>

      <nav className="flex w-[180px] shrink-0 flex-col border-r border-border bg-neutral-100 px-3 py-4">
        <div className="mb-4 px-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">服务运营</div>
        <div className="flex flex-col gap-0.5">
          {RECORD_NAV.map(({ label, icon: ItemIcon, active }) => (
            <div
              key={label}
              className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm ${active ? "bg-background font-semibold text-foreground shadow-sm" : "text-muted-foreground"}`}
            >
              <ItemIcon size={16} />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </nav>

      <main className="min-w-0 flex-1 bg-white">
        <header className="border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold">通话记录</h1>
          <p className="mt-1 text-sm text-muted-foreground">查看呼入、呼出及完整通话历史</p>
        </header>
        <div className="flex items-center gap-3 border-b border-border px-6 py-3">
          <div className="flex h-9 w-28 items-center justify-between rounded-md border border-border px-3 text-sm">
            <span>全部类型</span><span className="text-[10px] text-muted-foreground">⌄</span>
          </div>
          <div className="flex h-9 w-60 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground">
            <IconSearch size={15} /><span>搜索号码或通话 ID</span>
          </div>
          <div className="flex h-9 w-32 items-center rounded-md border border-border px-3 text-sm">2026-08-09</div>
          <span className="text-xs text-muted-foreground">至</span>
          <div className="flex h-9 w-32 items-center rounded-md border border-border px-3 text-sm">2026-08-09</div>
        </div>
        <div className="p-6">
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/70 text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">用户号码</th>
                  <th className="px-4 py-3 font-medium">类型</th>
                  <th className="px-4 py-3 font-medium">关联用户</th>
                  <th className="px-4 py-3 font-medium">服务号码</th>
                  <th className="px-4 py-3 font-medium">最后队列</th>
                  <th className="px-4 py-3 font-medium">接待客服</th>
                  <th className="px-4 py-3 font-medium">开始时间</th>
                  <th className="px-4 py-3 font-medium">时长</th>
                  <th className="px-4 py-3 font-medium">通话结果</th>
                </tr>
              </thead>
              <tbody>
                {CALL_RECORDS.map((row, index) => (
                  <tr key={row.id} className={index === 0 ? "border-t border-border bg-sky-50/50" : "border-t border-border"}>
                    <td className="px-4 py-3 font-medium">{row.customerNumber}</td>
                    <td className="px-4 py-3 text-muted-foreground">{row.direction}</td>
                    <td className="px-4 py-3">{row.user}</td>
                    <td className="px-4 py-3 text-muted-foreground">{row.serviceNumber}</td>
                    <td className="px-4 py-3">{row.queue}</td>
                    <td className="px-4 py-3">{row.agent}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{row.startedAt}</td>
                    <td className="px-4 py-3 font-mono text-xs">{row.duration}</td>
                    <td className="px-4 py-3">
                      <span className={`whitespace-nowrap rounded-md px-2 py-1 text-xs ${row.result === "客服接通" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{row.result}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      {children}
    </div>
  )
}
