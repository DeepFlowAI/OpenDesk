import type { ReactNode } from "react";
import {
  IconArrowLeft,
  IconBrain,
  IconCheck,
  IconChevronDown,
  IconHeadset,
  IconPlus,
  IconTimeline,
  IconTrash,
} from "@tabler/icons-react";
import { EngagementShell } from "../components/engagement-shell";
import { RETRY_POLICY_ROWS } from "../fixtures";

function WizardHeader({ step }: { step: 1 | 2 | 3 }) {
  const steps = ["基础信息", "执行方式", "外呼计划与呼叫策略"];
  return (
    <header className="shrink-0 border-b border-border">
      <div className="flex items-center gap-3 px-6 py-4">
        <span className="rounded-md p-2 text-muted-foreground"><IconArrowLeft size={18} /></span>
        <div>
          <h1 className="text-xl font-semibold">新建自动外呼任务</h1>
        </div>
      </div>
      <div className="flex items-center gap-2 px-6 pb-4">
        {steps.map((label, index) => {
          const current = index + 1 === step;
          const done = index + 1 < step;
          return (
            <div key={label} className="flex items-center gap-2">
              {index > 0 && <span className="mx-2 h-px w-10 bg-border" />}
              <span className={`grid h-6 w-6 place-items-center rounded-full text-[11px] font-semibold ${done ? "bg-emerald-100 text-emerald-700" : current ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>
                {done ? <IconCheck size={13} /> : index + 1}
              </span>
              <span className={`text-sm ${current ? "font-semibold" : "text-muted-foreground"}`}>{label}</span>
            </div>
          );
        })}
      </div>
    </header>
  );
}

function WizardFooter({ primary }: { primary: string }) {
  return (
    <div className="flex shrink-0 items-center justify-between border-t border-border px-6 py-4">
      <button className="h-9 rounded-md px-4 text-sm text-muted-foreground">取消</button>
      <div className="flex items-center gap-2">
        <button className="h-9 rounded-md border border-border px-4 text-sm">保存草稿</button>
        <button className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground">{primary}</button>
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-background p-5">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Field({ label, required, children, hint }: { label: string; required?: boolean; children: ReactNode; hint?: string }) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium text-muted-foreground">
        {required && <span className="mr-0.5 text-red-500">*</span>}{label}
      </div>
      {children}
      {hint && <div className="mt-1.5 text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

function SelectBox({ value }: { value: string }) {
  return (
    <div className="flex h-9 w-full items-center justify-between rounded-md border border-border bg-background px-3 text-sm">
      <span>{value}</span>
      <IconChevronDown size={14} className="text-muted-foreground" />
    </div>
  );
}

const MODE_CARDS = [
  { key: "ivr", icon: IconTimeline, title: "IVR 语音流程", desc: "接通后进入语音流程，自动播报、收集按键，适合通知类场景。" },
  { key: "bot", icon: IconBrain, title: "语音机器人", desc: "接通后由 VoiceSpeed Agent 多轮对话，识别意向并记录结果。" },
  { key: "agent", icon: IconHeadset, title: "自动转人工", desc: "接通后桥接空闲坐席，支持渐进式、比例多外呼与预测式拨号节奏。" },
] as const;

const TEMPLATE_FIELDS = [
  { name: "客户等级", type: "单选" },
  { name: "套餐到期", type: "日期" },
  { name: "意向产品", type: "单行文本" },
  { name: "回访问题", type: "多行文本" },
];

export function CreateBasicInfoScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <WizardHeader step={1} />
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface p-6">
          <div className="mx-auto max-w-3xl space-y-4">
            <Card title="基础信息">
              <div className="grid gap-4">
                <Field label="任务名称" required>
                  <div className="flex h-9 items-center rounded-md border border-border bg-background px-3 text-sm">到期续费提醒</div>
                </Field>
                <Field label="任务模板" required hint="选择后复制模板字段结构作为名单业务字段；自动外呼不使用话术流程快照">
                  <SelectBox value="续费提醒模板" />
                </Field>
                <Field label="任务说明">
                  <div className="min-h-[96px] rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground">
                    针对套餐即将到期的客户发起自动外呼，确认续费意向并记录结果。
                  </div>
                </Field>
                <Field label="负责人" hint="默认当前创建人">
                  <SelectBox value="李婷" />
                </Field>
              </div>
            </Card>
            <Card title="任务字段结构">
              <p className="mb-3 text-sm text-muted-foreground">已从模板复制，创建后仅影响本任务；后续修改模板不会同步到本任务。</p>
              <div className="overflow-hidden rounded-lg border border-border">
                <div className="grid grid-cols-[1fr_120px] items-center gap-3 border-b border-border bg-muted/50 px-3 py-2 text-[11px] font-medium text-muted-foreground">
                  <span>字段名称</span><span>字段类型</span>
                </div>
                {TEMPLATE_FIELDS.map((field) => (
                  <div key={field.name} className="grid grid-cols-[1fr_120px] items-center gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0">
                    <span>{field.name}</span>
                    <span className="text-muted-foreground">{field.type}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
        <WizardFooter primary="下一步" />
      </div>
    </EngagementShell>
  );
}

export function CreateModeScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <WizardHeader step={2} />
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface p-6">
          <div className="mx-auto max-w-3xl space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {MODE_CARDS.map(({ key, icon: ModeIcon, title, desc }) => {
                const selected = key === "agent";
                return (
                  <div key={key} className={`rounded-lg border bg-background p-4 ${selected ? "border-primary shadow-sm" : "border-border"}`}>
                    <div className="flex items-center justify-between">
                      <span className={`grid h-9 w-9 place-items-center rounded-lg ${selected ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}><ModeIcon size={18} /></span>
                      {selected && <span className="grid h-5 w-5 place-items-center rounded-full bg-primary text-primary-foreground"><IconCheck size={12} /></span>}
                    </div>
                    <div className="mt-3 text-sm font-semibold">{title}</div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{desc}</p>
                  </div>
                );
              })}
            </div>
            <Card title="自动转人工配置">
              <div className="grid grid-cols-2 gap-4">
                <Field label="接待队列" required><SelectBox value="续费接待队列" /></Field>
                <Field label="话后处理时长" required>
                  <div className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm"><span>60</span><span className="text-xs text-muted-foreground">秒</span></div>
                </Field>
              </div>
              <div className="mt-4">
                <Field label="拨号节奏" required>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="rounded-lg border border-border p-3.5">
                      <div className="text-sm font-medium">渐进式</div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">每名空闲坐席同时只发起 1 通呼叫，接通即接入，无呼损。</p>
                    </div>
                    <div className="rounded-lg border border-primary bg-primary/5 p-3.5">
                      <div className="flex items-center justify-between"><div className="text-sm font-medium">比例多外呼</div><span className="grid h-4 w-4 place-items-center rounded-full bg-primary text-primary-foreground"><IconCheck size={10} /></span></div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">按固定比例为每名空闲坐席同时发起多路呼叫，可能产生呼损。</p>
                    </div>
                    <div className="rounded-lg border border-border p-3.5">
                      <div className="text-sm font-medium">预测式</div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">按拨号强度动态提前多路拨号，系统自动调节，存在少量呼损。</p>
                    </div>
                  </div>
                </Field>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-4">
                <Field label="外呼比例" required hint="每名空闲坐席同时发起的呼叫路数，2–5">
                  <div className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm"><span>2</span><span className="text-xs text-muted-foreground">: 1</span></div>
                </Field>
                <Field label="呼损提示音" required hint="客户接通但无坐席空闲时的处理">
                  <SelectBox value="播放等待提示音" />
                </Field>
              </div>
              <div className="mt-4 rounded-lg bg-amber-50 px-3 py-2.5 text-xs text-amber-800">坐席较少（少于 5 人）时建议使用渐进式，避免呼损升高。</div>
            </Card>
          </div>
        </div>
        <WizardFooter primary="下一步" />
      </div>
    </EngagementShell>
  );
}

export function CreateScheduleScreen() {
  return (
    <EngagementShell>
      <div className="flex h-full flex-col overflow-hidden">
        <WizardHeader step={3} />
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface p-6">
          <div className="mx-auto max-w-3xl space-y-4">
            <Card title="外呼计划">
              <div className="grid grid-cols-2 gap-4">
                <Field label="开始日期" required><SelectBox value="2026-08-10" /></Field>
                <Field label="结束日期" required><SelectBox value="2026-08-24" /></Field>
              </div>
              <div className="mt-4">
                <Field label="每日呼叫时段" required hint="系统仅在时段内发起新呼叫；进行中的通话不受时段结束影响">
                  <div className="space-y-2">
                    {["09:00 – 12:00", "14:00 – 20:00"].map((slot) => (
                      <div key={slot} className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm">
                        <span className="font-mono text-[13px]">{slot}</span>
                        <IconTrash size={14} className="text-muted-foreground" />
                      </div>
                    ))}
                    <button className="inline-flex h-8 items-center gap-1 rounded-md border border-dashed border-border px-3 text-xs text-muted-foreground"><IconPlus size={13} />添加时段</button>
                  </div>
                </Field>
              </div>
              <div className="mt-4">
                <Field label="主叫号码" required hint="来自号码管理中已启用且允许外呼的号码"><SelectBox value="0755-8655 0123（深圳 · 主叫）" /></Field>
              </div>
            </Card>
            <Card title="呼叫策略">
              <div className="grid grid-cols-2 gap-4">
                <Field label="最大并发呼叫数" required hint="同一时刻进行中的自动呼叫上限">
                  <div className="flex h-9 items-center rounded-md border border-border px-3 text-sm">10</div>
                </Field>
                <Field label="单号码日频控" required hint="同一号码每日最大呼叫次数">
                  <div className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm"><span>3</span><span className="text-xs text-muted-foreground">次 / 日</span></div>
                </Field>
              </div>
              <div className="mt-4">
                <div className="mb-1.5 text-xs font-medium text-muted-foreground">重呼策略</div>
                <div className="overflow-hidden rounded-lg border border-border">
                  <div className="grid grid-cols-[1fr_120px_140px_90px] items-center gap-3 border-b border-border bg-muted/50 px-3 py-2 text-[11px] font-medium text-muted-foreground">
                    <span>未接通终态</span><span>重试次数</span><span>重试间隔</span><span>启用</span>
                  </div>
                  {RETRY_POLICY_ROWS.map((row) => (
                    <div key={row.disposition} className="grid grid-cols-[1fr_120px_140px_90px] items-center gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0">
                      <span>{row.disposition}</span>
                      <span className={row.enabled ? "" : "text-muted-foreground"}>{row.retries}</span>
                      <span className={row.enabled ? "" : "text-muted-foreground"}>{row.interval}</span>
                      <span className={`inline-flex h-5 w-9 items-center rounded-full px-0.5 ${row.enabled ? "justify-end bg-primary" : "justify-start bg-muted"}`}><span className="h-4 w-4 rounded-full bg-white shadow" /></span>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </div>
        </div>
        <WizardFooter primary="启动任务" />
      </div>
    </EngagementShell>
  );
}
