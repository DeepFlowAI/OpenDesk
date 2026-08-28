import {
  IconArrowLeft,
  IconPlus,
  IconSearch,
  IconUpload,
} from "@tabler/icons-react";
import { EngagementShell } from "../components/engagement-shell";
import {
  AUTO_TARGETS,
  CALL_RECORDS,
  LIVE_AGENTS,
  LIVE_CALLS,
  type Disposition,
} from "../fixtures";

type DetailTab = "targets" | "records" | "monitor";

interface DetailMeta {
  title: string;
  subtitle: string;
  modeLabel: string;
  modeBadge: string;
  tab: DetailTab;
  showMonitor: boolean;
  abandonRate?: string;
}

const BOT_META: DetailMeta = {
  title: "客户满意度回访",
  subtitle: "满意度回访模板 · 语音机器人",
  modeLabel: "语音机器人",
  modeBadge: "bg-violet-50 text-violet-700",
  tab: "targets",
  showMonitor: false,
};

const AGENT_META: DetailMeta = {
  title: "到期续费提醒",
  subtitle: "续费提醒模板 · 自动转人工 · 比例多外呼 2:1",
  modeLabel: "自动转人工",
  modeBadge: "bg-emerald-50 text-emerald-700",
  tab: "monitor",
  showMonitor: true,
  abandonRate: "1.2%",
};

const TARGET_STATUS_BADGE: Record<string, string> = {
  待呼叫: "bg-sky-50 text-sky-700",
  呼叫中: "bg-emerald-50 text-emerald-700",
  需重拨: "bg-amber-50 text-amber-700",
  已完成: "bg-muted text-muted-foreground",
  无效号码: "bg-red-50 text-red-700",
};

const DISPOSITION_BADGE: Record<Disposition, string> = {
  已接通: "bg-emerald-50 text-emerald-700",
  无人接听: "bg-amber-50 text-amber-700",
  忙线: "bg-amber-50 text-amber-700",
  关机停机: "bg-amber-50 text-amber-700",
  空号: "bg-red-50 text-red-700",
  呼叫失败: "bg-red-50 text-red-700",
};

const LIVE_STATE_BADGE: Record<string, string> = {
  通话中: "bg-emerald-50 text-emerald-700",
  振铃中: "bg-sky-50 text-sky-700",
  排队待接入: "bg-amber-50 text-amber-700",
};

const AGENT_STATE_DOT: Record<string, string> = {
  就绪: "bg-emerald-500",
  通话中: "bg-sky-500",
  话后处理: "bg-amber-500",
  小休: "bg-muted-foreground",
};

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 flex items-baseline gap-1.5 text-xl font-semibold">
        {value}
        {hint && <span className="text-[10px] font-normal text-muted-foreground">{hint}</span>}
      </div>
    </div>
  );
}

function TargetsPanel() {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border border-border p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-base font-semibold">外呼对象名单</h2>
          <p className="mt-1 text-sm text-muted-foreground">系统按呼叫策略自动消费名单；无坐席分配与领取。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm"><IconPlus size={16} />添加</button>
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-border px-3 text-sm"><IconUpload size={16} />导入</button>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-72 items-center gap-2 rounded-md border border-border px-3 text-sm text-muted-foreground"><IconSearch size={16} />搜索号码 / 用户 / 字段</div>
        <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm text-muted-foreground">全部状态</div>
      </div>
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-3 font-medium">呼叫号码</th>
              <th className="px-4 py-3 font-medium">关联用户</th>
              <th className="px-4 py-3 font-medium">客户等级</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">呼叫</th>
              <th className="px-4 py-3 font-medium">接通</th>
              <th className="px-4 py-3 font-medium">最近结果</th>
              <th className="px-4 py-3 font-medium">剩余重试</th>
              <th className="w-28 px-4 py-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {AUTO_TARGETS.map((target) => (
              <tr key={target.phone} className="border-t border-border">
                <td className="px-4 py-3 font-mono text-[13px]">{target.phone}</td>
                <td className={`px-4 py-3 ${target.user === "未匹配" ? "text-muted-foreground" : ""}`}>{target.user}</td>
                <td className="px-4 py-3 text-muted-foreground">{target.level}</td>
                <td className="px-4 py-3"><span className={`rounded-md px-2 py-1 text-[11px] ${TARGET_STATUS_BADGE[target.status]}`}>{target.status}</span></td>
                <td className="px-4 py-3">{target.calls}</td>
                <td className="px-4 py-3">{target.connected}</td>
                <td className="px-4 py-3 text-muted-foreground">{target.lastResult}</td>
                <td className="px-4 py-3">{target.retriesLeft > 0 ? `${target.retriesLeft} 次` : "—"}</td>
                <td className="px-4 py-3 text-xs text-primary">查看</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RecordsPanel() {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/60 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">呼叫号码</th>
            <th className="px-4 py-3 font-medium">呼叫开始时间</th>
            <th className="px-4 py-3 font-medium">呼叫终态</th>
            <th className="px-4 py-3 font-medium">接待方式</th>
            <th className="px-4 py-3 font-medium">通话时长</th>
            <th className="px-4 py-3 font-medium">接待结果</th>
            <th className="w-24 px-4 py-3 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {CALL_RECORDS.map((record) => (
            <tr key={record.time} className="border-t border-border">
              <td className="px-4 py-3 font-mono text-[13px]">{record.phone}</td>
              <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{record.time}</td>
              <td className="px-4 py-3"><span className={`rounded-md px-2 py-1 text-[11px] ${DISPOSITION_BADGE[record.disposition]}`}>{record.disposition}</span></td>
              <td className="px-4 py-3">{record.reception}</td>
              <td className="px-4 py-3 font-mono text-xs">{record.duration}</td>
              <td className="px-4 py-3 text-muted-foreground">{record.result}</td>
              <td className="px-4 py-3 text-xs text-primary">通话详情</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MonitorPanel() {
  return (
    <div className="grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-4">
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-sm font-semibold">进行中呼叫</span>
          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><span className="h-2 w-2 rounded-full bg-emerald-500" />每 5 秒自动刷新</span>
        </div>
        {LIVE_CALLS.map((call) => (
          <div key={call.phone} className="flex items-center justify-between border-b border-border px-4 py-3 text-sm last:border-b-0">
            <div>
              <div className="font-mono text-[13px]">{call.phone}</div>
              <div className="mt-0.5 text-xs text-muted-foreground">{call.user}</div>
            </div>
            <div className="flex items-center gap-4">
              {call.agent && <span className="text-xs text-muted-foreground">坐席 {call.agent}</span>}
              <span className={`rounded-md px-2 py-1 text-[11px] ${LIVE_STATE_BADGE[call.state]}`}>{call.state}</span>
              <span className="w-12 text-right font-mono text-xs">{call.elapsed}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-4">
        <div className="rounded-lg border border-border p-4">
          <div className="text-sm font-semibold">接待队列坐席</div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            {[{ label: "就绪", value: 2 }, { label: "通话中", value: 2 }, { label: "话后处理", value: 1 }].map((item) => (
              <div key={item.label} className="rounded-lg bg-muted/50 px-2 py-2.5">
                <div className="text-lg font-semibold">{item.value}</div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">{item.label}</div>
              </div>
            ))}
          </div>
          <div className="mt-3 space-y-1.5">
            {LIVE_AGENTS.map((agent) => (
              <div key={agent.name} className="flex items-center justify-between text-xs">
                <span>{agent.name}</span>
                <span className="flex items-center gap-1.5 text-muted-foreground"><span className={`h-1.5 w-1.5 rounded-full ${AGENT_STATE_DOT[agent.state]}`} />{agent.state}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-border p-4 text-xs">
          <div className="text-sm font-semibold">拨号参数</div>
          <div className="mt-3 space-y-2">
            <div className="flex justify-between"><span className="text-muted-foreground">拨号节奏</span><span>比例多外呼</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">外呼比例</span><span>2 : 1</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">排队待接入</span><span>1 通</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">呼损率</span><span>1.2%</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AutoOutboundDetailScreen({ tab }: { tab: DetailTab }) {
  const meta: DetailMeta = tab === "monitor" ? { ...AGENT_META } : { ...BOT_META, tab };
  const metrics = meta.showMonitor
    ? [
        { label: "外呼对象总数", value: "480" },
        { label: "已终态对象", value: "212" },
        { label: "呼叫 / 接通", value: "512 / 314" },
        { label: "接通率", value: "61.4%" },
        { label: "当前并发", value: "6" },
        { label: "已派坐席", value: "298" },
        { label: "呼损率", value: "1.2%", hint: "上限 3%" },
      ]
    : [
        { label: "外呼对象总数", value: "1,500" },
        { label: "已终态对象", value: "860" },
        { label: "呼叫 / 接通", value: "1,642 / 860" },
        { label: "接通率", value: "52.3%" },
        { label: "当前并发", value: "8" },
        { label: "转人工次数", value: "96" },
      ];

  const tabs: { key: DetailTab | "stats"; label: string; count?: string }[] = [
    { key: "targets", label: "外呼对象", count: meta.showMonitor ? "480" : "1,500" },
    { key: "records", label: "呼叫记录" },
    { key: "stats", label: "统计" },
    ...(meta.showMonitor ? [{ key: "monitor" as const, label: "实时监控" }] : []),
  ];

  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="rounded-md p-2 text-muted-foreground"><IconArrowLeft size={18} /></span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold">{meta.title}</h1>
                <span className={`rounded-md px-2 py-1 text-[11px] ${meta.modeBadge}`}>{meta.modeLabel}</span>
                <span className="rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">进行中</span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{meta.subtitle}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="rounded-md border border-border px-3 py-2 text-sm">编辑</button>
            <button className="rounded-md border border-border px-3 py-2 text-sm">暂停</button>
            <button className="rounded-md border border-border px-3 py-2 text-sm">归档</button>
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-6">
          <div className="space-y-6">
            <section className={`grid gap-4 ${meta.showMonitor ? "grid-cols-7" : "grid-cols-6"}`}>
              {metrics.map((metric) => (
                <Metric key={metric.label} label={metric.label} value={metric.value} hint={"hint" in metric ? metric.hint : undefined} />
              ))}
            </section>

            <section>
              <div className="flex items-center border-b border-border">
                <div className="flex gap-6">
                  {tabs.map(({ key, label, count }) => {
                    const active = key === meta.tab;
                    return (
                      <div
                        key={key}
                        className={`border-b-2 px-1 pb-3 text-sm font-medium ${active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground"}`}
                      >
                        {label}
                        {count && <span className="ml-2 text-xs text-muted-foreground">{count}</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="pt-4">
                {meta.tab === "targets" && <TargetsPanel />}
                {meta.tab === "records" && <RecordsPanel />}
                {meta.tab === "monitor" && <MonitorPanel />}
              </div>
            </section>
          </div>
        </main>
      </div>
    </EngagementShell>
  );
}
