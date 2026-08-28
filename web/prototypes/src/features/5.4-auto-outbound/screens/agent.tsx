import {
  IconArrowsExchange,
  IconCheck,
  IconMicrophone,
  IconPhoneCall,
  IconPhoneOff,
  IconPlayerPause,
} from "@tabler/icons-react";
import { CallShell } from "../components/call-shell";

type RightTab = "summary" | "ticket" | "outbound";

function Field({
  label,
  value,
  strong,
  color,
}: {
  label: string;
  value: string;
  strong?: boolean;
  color?: string;
}) {
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

/** Production on-call bar pattern (AgentCallBar / §3.2.3), green strip. */
function OnCallBar() {
  return (
    <div className="flex shrink-0 items-center gap-6 border-b-2 border-green-200 bg-green-50 px-5 py-[18px]">
      <div className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-green-100">
          <IconPhoneCall size={16} className="text-green-700" />
        </span>
        <span className="font-bold text-green-800">通话中</span>
      </div>
      <Field label="通话类型" value="自动外呼" />
      <Field label="用户号码" value="138 0013 8000" strong />
      <Field label="服务号码" value="0755-8655 0123" />
      <Field label="通话时长" value="01:42" strong color="text-green-700" />
      <div className="rounded-md bg-white/80 px-2 py-1 text-[10px] text-muted-foreground">任务：到期续费提醒</div>
      <div className="ml-auto flex items-center gap-2">
        <button className="grid h-8 w-8 place-items-center rounded-md text-foreground/80" title="静音"><IconMicrophone size={16} /></button>
        <button className="grid h-8 w-8 place-items-center rounded-md text-foreground/80" title="保持"><IconPlayerPause size={16} /></button>
        <button className="inline-flex h-8 items-center gap-1 rounded-md border border-border bg-background/60 px-2 text-xs" title="转接"><IconArrowsExchange size={14} />转接</button>
        <button className="grid h-9 w-9 place-items-center rounded-full bg-red-500 text-white" title="挂断"><IconPhoneOff size={16} /></button>
      </div>
    </div>
  );
}

function WrapupBar() {
  return (
    <div className="flex shrink-0 items-center gap-6 border-b border-border bg-background px-5 py-[18px]">
      <div className="flex items-center gap-2">
        <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100">
          <IconCheck size={16} className="text-amber-700" />
        </span>
        <div>
          <p className="font-bold">通话已结束，请整理本次记录</p>
          <p className="text-xs text-muted-foreground">本次通话时长：03:12 · 自动外呼 · 到期续费提醒</p>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <span className="rounded-md bg-amber-50 px-2 py-1 font-mono text-[11px] text-amber-700">话后处理剩余 00:42</span>
        <button className="grid h-9 w-9 place-items-center rounded-full bg-green-500 text-white" title="完成整理">
          <IconCheck size={16} />
        </button>
      </div>
    </div>
  );
}

function CallInfoCard({ duration }: { duration: string }) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5">
      <h3 className="text-sm font-semibold">通话信息</h3>
      <div className="mt-3 min-h-0 flex-1 space-y-0.5 overflow-y-auto text-sm">
        <Row label="通话类型" value="自动外呼" />
        <Row label="用户号码" value="138 0013 8000" />
        <Row label="服务号码" value="0755-8655 0123" />
        <Row label="通话时长" value={duration} valueClass="text-green-700" />
        <Row label="任务来源" value="到期续费提醒" />
        <Row label="接听方式" value="Web 电话 · 自动接听" />
      </div>
      <div className="mt-4 rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
        暂无对话记录
      </div>
    </section>
  );
}

function UserInfoCard() {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5">
      <h3 className="text-sm font-semibold">用户信息</h3>
      <div className="mt-3 min-h-0 flex-1 space-y-0.5 overflow-y-auto text-sm">
        <Row label="姓名" value="王女士" />
        <Row label="手机号" value="138 0013 8000" />
        <Row label="客户等级" value="VIP 客户" />
        <Row label="所属组织" value="星海科技有限公司" />
        <Row label="套餐到期" value="2026-08-31" />
        <Row label="当前套餐" value="企业版 · 50 坐席" />
      </div>
    </section>
  );
}

function RightPanelTabs({ active }: { active: RightTab }) {
  const tabs: { key: RightTab; label: string }[] = [
    { key: "summary", label: "通话纪要" },
    { key: "ticket", label: "新建工单" },
    { key: "outbound", label: "外呼任务业务记录" },
  ];
  return (
    <div className="mb-3 flex items-center border-b border-border pb-2">
      <div className="flex shrink-0 rounded-md border border-border bg-muted p-0.5">
        {tabs.map(({ key, label }) => (
          <div
            key={key}
            className={`rounded px-2 py-1 text-xs font-medium ${key === active ? "bg-white text-foreground shadow-sm" : "text-muted-foreground"}`}
          >
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Outbound task business record: editable template fields only. */
function OutboundTaskRecordPanel({ wrapUp }: { wrapUp?: boolean }) {
  return (
    <div className="space-y-5">
      <div className="rounded-lg bg-muted/50 px-3 py-2 text-[11px] leading-4 text-muted-foreground">
        任务：到期续费提醒 · 续费提醒模板
        {wrapUp ? "" : " · 通话中可预填，挂断后进入话后处理倒计时"}
      </div>

      <div>
        <div className="mb-2 text-xs font-semibold text-foreground">任务业务字段</div>
        <p className="mb-3 text-[11px] text-muted-foreground">来自外呼任务模板中「允许客服编辑」的字段</p>
        <div className="space-y-3">
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">客户等级</div>
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">VIP 客户</div>
          </div>
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">套餐到期</div>
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">2026-08-31</div>
          </div>
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">意向产品</div>
            <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm text-muted-foreground">企业版续费</div>
          </div>
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted-foreground">外呼备注</div>
            <div className="min-h-[72px] rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
              客户表示本周内部评估后回复，下周三上午再联系。
            </div>
          </div>
        </div>
      </div>

      {wrapUp && (
        <button className="h-10 w-full rounded-lg bg-primary text-sm font-medium text-primary-foreground">
          提交业务记录并继续接单
        </button>
      )}
    </div>
  );
}

function ScreenPop({
  duration,
  rightTab,
  wrapUp,
}: {
  duration: string;
  rightTab: RightTab;
  wrapUp?: boolean;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
      <div className="grid h-full min-h-[520px] gap-4 xl:grid-cols-3">
        <CallInfoCard duration={duration} />
        <UserInfoCard />
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5">
          <RightPanelTabs active={rightTab} />
          <div className="min-h-0 flex-1 overflow-y-auto">
            {rightTab === "outbound" ? (
              <OutboundTaskRecordPanel wrapUp={wrapUp} />
            ) : rightTab === "ticket" ? (
              <div className="py-10 text-center text-sm text-muted-foreground">新建工单（沿用现网）</div>
            ) : (
              <div className="space-y-3">
                <div>
                  <div className="mb-1.5 text-xs text-muted-foreground">备注</div>
                  <div className="h-9 rounded-md border border-border" />
                </div>
                <div>
                  <div className="mb-1.5 text-xs text-muted-foreground">单行文本</div>
                  <div className="h-9 rounded-md border border-border" />
                </div>
                <div className="rounded-lg bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">通话纪要字段沿用现网配置</div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export function AgentDispatchScreen() {
  return (
    <CallShell phase="on_call">
      <div className="flex h-full flex-col bg-muted/30">
        <OnCallBar />
        <ScreenPop duration="01:42" rightTab="outbound" />
      </div>
    </CallShell>
  );
}

export function AgentWrapupScreen() {
  return (
    <CallShell phase="wrap_up">
      <div className="flex h-full flex-col bg-muted/30">
        <WrapupBar />
        <ScreenPop duration="03:12" rightTab="outbound" wrapUp />
      </div>
    </CallShell>
  );
}
