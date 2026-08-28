import {
  IconCalendarClock,
  IconChevronRight,
  IconNotes,
  IconPhone,
  IconSitemap,
  IconUser,
} from "@tabler/icons-react";
import { OUTBOUND_TARGETS } from "../fixtures";

export function TargetList() {
  return (
    <aside className="flex w-[306px] shrink-0 flex-col border-r border-border bg-background">
      <div className="border-b border-border p-4"><h2 className="font-display text-base font-semibold">我的外呼对象</h2><p className="mt-1 text-xs text-muted-foreground">待处理 12 · 今日到期 3</p><div className="mt-3 flex h-9 items-center justify-between rounded-md border border-border px-3 text-xs text-muted-foreground"><span>全部进行中任务</span><IconChevronRight size={14} /></div></div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {OUTBOUND_TARGETS.map((target) => (
          <div key={target.phone} className={`mb-2 rounded-lg border p-3 ${target.active ? "border-primary bg-muted/50" : "border-border"}`}>
            <div className="flex items-start justify-between gap-2"><div><div className="text-sm font-semibold">{target.name}</div><div className="mt-0.5 font-mono text-xs text-muted-foreground">{target.phone}</div></div><span className={`rounded-md px-1.5 py-0.5 text-[10px] ${target.status === "需重拨" ? "bg-amber-50 text-amber-700" : "bg-sky-50 text-sky-700"}`}>{target.status}</span></div>
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-muted-foreground"><IconNotes size={13} /><span className="truncate">{target.task}</span></div>
            <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground"><IconCalendarClock size={13} />下次跟进：今天 14:30</div>
          </div>
        ))}
      </div>
    </aside>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between border-b border-border py-3 last:border-b-0"><span className="text-xs text-muted-foreground">{label}</span><span className="text-sm font-medium">{value}</span></div>;
}

export function TargetDetail() {
  return (
    <section className="min-w-[420px] flex-1 overflow-y-auto bg-muted/30 p-5">
      <div className="mx-auto max-w-2xl space-y-4">
        <div className="rounded-xl border border-border bg-background p-5">
          <div className="flex items-start justify-between gap-4"><div><div className="text-xs text-muted-foreground">当前外呼对象</div><div className="mt-1 flex items-center gap-2"><span className="font-display text-xl font-semibold">王女士</span><span className="rounded bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-700">待呼叫</span></div><div className="mt-1.5 font-mono text-sm text-muted-foreground">138 0013 8000</div></div><div className="flex items-center gap-2"><button className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-xs"><IconSitemap size={15} />话术流程</button><button className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-xs font-medium text-primary-foreground"><IconPhone size={15} />呼叫</button></div></div>
          <div className="mt-5 grid grid-cols-3 gap-3 rounded-lg bg-muted/50 p-3 text-xs"><div><span className="text-muted-foreground">任务</span><div className="mt-1 font-medium">客户满意度回访</div></div><div><span className="text-muted-foreground">最近结果</span><div className="mt-1 font-medium">首次呼叫</div></div><div><span className="text-muted-foreground">累计呼叫</span><div className="mt-1 font-medium">0 次</div></div></div>
        </div>
        <div className="rounded-xl border border-border bg-background p-5"><div className="flex items-center gap-2"><IconUser size={16} className="text-muted-foreground" /><h3 className="text-sm font-semibold">客户信息</h3></div><div className="mt-3"><InfoRow label="客户等级" value="VIP 客户" /><InfoRow label="所属组织" value="星海科技有限公司" /><InfoRow label="最近服务" value="工单 #TK-20260803-018" /></div></div>
        <div className="rounded-xl border border-border bg-background p-5"><h3 className="text-sm font-semibold">外呼对象状态</h3><div className="mt-4 flex flex-wrap gap-2">{["待呼叫", "需重拨", "已完成", "勿扰", "无效号码"].map((item, index) => <span key={item} className={`rounded-md border px-3 py-2 text-xs ${index === 0 ? "border-primary bg-primary text-primary-foreground" : "border-border"}`}>{item}</span>)}</div></div>
      </div>
    </section>
  );
}
