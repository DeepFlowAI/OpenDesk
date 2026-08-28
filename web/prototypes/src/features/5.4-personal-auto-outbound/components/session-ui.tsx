import type { ReactNode } from "react";
import { IconChevronDown, IconMicrophone, IconPhone, IconPhoneOff, IconUser } from "@tabler/icons-react";
import type { LaneSlot } from "../fixtures";

export function SessionHeader({
  status,
  statusTone = "muted",
  actions,
}: {
  status: string;
  statusTone?: "muted" | "info" | "warning" | "success";
  actions: ReactNode;
}) {
  const toneClass =
    statusTone === "info"
      ? "bg-info/10 text-info"
      : statusTone === "warning"
        ? "bg-warning/20 text-foreground"
        : statusTone === "success"
          ? "bg-success/10 text-success"
          : "bg-muted text-muted-foreground";
  return (
    <header className="flex h-[74px] shrink-0 items-center justify-between border-b border-border bg-background px-6">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="font-display text-xl font-bold tracking-tight">个人自动外呼</h1>
          <span className={`rounded-md px-2 py-1 text-[11px] font-medium ${toneClass}`}>{status}</span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">到期续费提醒 · 张琪的外呼对象</p>
      </div>
      <div className="flex items-center gap-2">{actions}</div>
    </header>
  );
}

export function RunningCallBar({ hint }: { hint: string }) {
  return (
    <div className="flex items-center gap-3 border-b border-border bg-background px-5 py-3.5">
      <div className="flex h-10 w-[220px] items-center rounded-lg border border-border px-3 text-sm text-muted-foreground">
        输入用户号码
      </div>
      <div className="flex h-10 w-[190px] items-center justify-between rounded-lg border border-border px-3 text-sm">
        <span>0755-8655 0123</span>
        <IconChevronDown size={14} className="text-muted-foreground" />
      </div>
      <span className="grid h-10 w-10 place-items-center rounded-full bg-success text-white">
        <IconPhone size={17} />
      </span>
      <span className="ml-auto text-xs text-muted-foreground">{hint}</span>
    </div>
  );
}

export function OnCallBar({ name, phone }: { name: string; phone: string }) {
  return (
    <div className="flex items-center gap-3 border-b border-success/30 bg-success/10 px-5 py-3.5">
      <span className="grid h-10 w-10 place-items-center rounded-full bg-success text-white">
        <IconPhone size={17} />
      </span>
      <div className="min-w-0">
        <div className="text-sm font-semibold">通话中</div>
        <div className="text-xs text-muted-foreground">
          {name} {phone}
        </div>
      </div>
      <span className="ml-3 font-mono text-sm tabular-nums text-muted-foreground">00:12</span>
      <span className="ml-auto grid h-10 w-10 place-items-center rounded-full bg-destructive text-white">
        <IconPhoneOff size={17} />
      </span>
    </div>
  );
}

function laneMeta(slot: LaneSlot) {
  if (slot.stage === "dialing") return { label: "拨号中", bar: "bg-info", text: "text-info" };
  if (slot.stage === "ringing") return { label: "振铃中", bar: "bg-info", text: "text-info" };
  if (slot.stage === "screening") return { label: "预筛中", bar: "bg-warning", text: "text-foreground" };
  if (slot.stage === "clearing") return { label: slot.result ?? "已结束", bar: "bg-muted-foreground/30", text: "text-muted-foreground" };
  return { label: "空闲", bar: "bg-transparent", text: "text-muted-foreground" };
}

export function ConcurrencyLanes({ lanes }: { lanes: LaneSlot[] }) {
  return (
    <section className="flex flex-col gap-3">
      {lanes.map((lane) => {
        const meta = laneMeta(lane);
        const empty = lane.stage === "empty";
        const clearing = lane.stage === "clearing";
        return (
          <div
            key={lane.slot}
            className={`rounded-xl border px-5 py-4 ${
              clearing
                ? "border-border/60 bg-card/50 opacity-45"
                : empty
                  ? "border-dashed border-border bg-muted/20"
                  : lane.stage === "screening"
                    ? "border-warning/40 bg-warning/5"
                    : "border-border bg-card"
            }`}
          >
            <div className="flex items-center gap-4">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-muted font-mono text-[11px] font-semibold text-muted-foreground">
                {lane.slot}
              </span>
              {empty ? (
                <div className="min-w-0 flex-1">
                  <div className="h-2 overflow-hidden rounded-full bg-muted">
                    <div className="h-full w-0" />
                  </div>
                </div>
              ) : (
                <>
                  <div className="w-[168px] shrink-0">
                    <div className="truncate text-sm font-semibold">{lane.customer}</div>
                    <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{lane.phone}</div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div
                        className={`h-full rounded-full ${meta.bar}`}
                        style={{ width: `${clearing ? 0 : lane.progress ?? 0}%` }}
                      />
                    </div>
                  </div>
                </>
              )}
              <div className={`w-[148px] shrink-0 text-right text-xs font-medium ${meta.text}`}>
                {clearing ? `${meta.label} · 正在收口` : meta.label}
              </div>
              <div className="w-12 shrink-0 text-right font-mono text-xs tabular-nums text-muted-foreground">
                {empty || clearing ? "" : lane.elapsed}
              </div>
            </div>
          </div>
        );
      })}
    </section>
  );
}

export function TaskPopPanel({
  name,
  phone,
  task,
  openingScript,
  lastUtterance,
}: {
  name: string;
  phone: string;
  task: string;
  openingScript?: string;
  lastUtterance: string;
}) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">{name}</h2>
              <span className="rounded-md bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success">通话中</span>
            </div>
            <p className="mt-1 font-mono text-xl font-semibold tracking-wide">{phone}</p>
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
              <IconUser size={13} />
              关联用户：{name} · {task}
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="text-sm font-semibold">预筛上下文</h3>
        <p className="mt-1 text-[11px] text-muted-foreground">客户刚听完开场白后的最后一句，未明确拒绝所以转入人工</p>
        <div className="mt-4 space-y-3">
          {openingScript ? (
            <div className="rounded-lg bg-muted/60 px-4 py-3">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                <IconMicrophone size={13} />
                开场白
              </div>
              <p className="mt-1.5 text-sm leading-6">{openingScript}</p>
            </div>
          ) : null}
          <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3">
            <div className="text-[11px] font-medium text-primary">客户刚才说</div>
            <p className="mt-1.5 text-sm font-medium leading-6">{lastUtterance}</p>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-border bg-card shadow-sm">
        <div className="border-b border-border px-5 py-3">
          <h3 className="text-sm font-semibold">业务记录</h3>
        </div>
        <div className="space-y-3 p-5">
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">意向等级</div>
            <div className="flex h-9 items-center justify-between rounded-md border border-border px-3 text-sm text-muted-foreground">
              待填写
              <IconChevronDown size={14} />
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">外呼备注</div>
            <div className="h-16 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">记录本次沟通要点…</div>
          </div>
        </div>
      </section>
    </div>
  );
}
