import type { ReactNode } from "react";
import {
  IconArrowBackUp,
  IconArrowsExchange,
  IconChevronDown,
  IconChevronUp,
  IconDialpad,
  IconLogout,
  IconMessage,
  IconMicrophone,
  IconMicrophoneOff,
  IconPhone,
  IconPhoneOff,
  IconPlayerPause,
  IconPlayerPlay,
  IconStar,
  IconUserOff,
  IconUserPlus,
  IconUsersGroup,
} from "@tabler/icons-react";
import { CALL } from "../fixtures";

export type BarTone = "active" | "warning";

function toneClass(tone: BarTone) {
  return tone === "warning"
    ? "border-warning/30 bg-warning/10"
    : "border-success/30 bg-success/10";
}

function IconBtn({
  icon,
  label,
  title,
  active,
  warning,
  danger,
  solid,
  tooltip,
}: {
  icon: ReactNode;
  label: string;
  title?: string;
  active?: boolean;
  warning?: boolean;
  danger?: boolean;
  solid?: boolean;
  tooltip?: string;
}) {
  const name = title ?? label;
  return (
    <span className="group relative flex w-10 cursor-pointer flex-col items-center gap-1.5">
      <span
        title={name}
        aria-label={name}
        className={[
          "grid h-7 w-7 place-items-center transition-colors",
          solid
            ? "rounded-full bg-destructive text-white [&_svg]:text-white group-hover:bg-destructive/80"
            : danger
              ? "rounded-md bg-background/70 text-destructive group-hover:bg-destructive/10"
              : warning
                ? "rounded-md bg-warning/15 text-warning group-hover:bg-warning/30"
                : active
                  ? "rounded-md bg-primary/10 text-primary group-hover:bg-primary/20"
                  : "rounded-md bg-background/70 text-foreground/80 group-hover:bg-muted group-hover:text-foreground",
        ].join(" ")}
      >
        {icon}
      </span>
      <span
        className={[
          "text-[11px] leading-none",
          solid || danger ? "text-destructive" : warning || active ? "text-foreground" : "text-foreground/70",
        ].join(" ")}
      >
        {label}
      </span>
      {tooltip && (
        <span className="absolute left-1/2 top-[calc(100%+6px)] z-20 -translate-x-1/2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-[11px] font-medium text-background shadow-sm">
          {tooltip}
          <span className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-foreground" />
        </span>
      )}
    </span>
  );
}

function Divider() {
  return <span className="mx-0.5 h-8 w-px shrink-0 self-center bg-border/80" />;
}

function Status({
  title,
  number = CALL.number,
  duration = CALL.duration,
  extra,
}: {
  title: string;
  number?: string;
  duration?: string;
  extra?: string;
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <span className="shrink-0 text-sm font-semibold">{title}</span>
      <span className="min-w-0 truncate font-mono text-sm text-foreground/70">{number}</span>
      <span className="shrink-0 font-mono text-xs tabular-nums text-foreground/60">{duration}</span>
      {extra && (
        <span className="shrink-0 font-mono text-xs tabular-nums text-warning">{extra}</span>
      )}
    </div>
  );
}

/** Current production pattern: labelled pills + collapse + second row. */
export function CurrentExpandedBar() {
  return (
    <div className={`rounded-lg border ${toneClass("active")}`}>
      <div className="flex min-h-11 flex-wrap items-center gap-3 px-3 py-2">
        <Status title={CALL.status} />
        <div className="flex shrink-0 items-center gap-2">
          <span className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium">
            <IconMicrophone size={15} />
            静音
          </span>
          <span className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium">
            <IconPlayerPause size={15} />
            保持
          </span>
          <span className="grid h-8 w-8 place-items-center rounded-md bg-destructive/90 text-destructive-foreground">
            <IconPhoneOff size={15} />
          </span>
        </div>
        <span className="flex h-8 shrink-0 items-center gap-1 rounded-md border border-border/60 bg-background/60 px-2 text-xs font-medium text-foreground/80">
          收起通话控制
          <IconChevronUp size={14} />
        </span>
      </div>
      <div className="border-t border-border/50 px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-md border border-border bg-background/60">
            <IconMessage size={16} />
          </span>
          <span className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium">
            <IconArrowsExchange size={15} />
            转接
          </span>
          <span className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium">
            <IconUserPlus size={15} />
            咨询
          </span>
          <span className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium">
            <IconUsersGroup size={15} />
            添加参与人
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * Production global on-call bar: AgentCallBar compact + UniversalCallBar,
 * default collapsed. Do not restyle this in the proposal.
 */
export function CurrentCompactGlobalBar() {
  return (
    <div className="w-full max-w-[min(760px,calc(100vw-8rem))] rounded-lg border border-success/30 bg-success/10">
      <div className="flex min-h-11 flex-wrap items-center gap-3 px-3 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <span className="shrink-0 text-sm font-semibold">{CALL.status}</span>
          <span className="shrink-0 font-mono text-xs tabular-nums text-foreground/60">{CALL.duration}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium">
            <IconMicrophone size={15} />
            静音
          </span>
          <span className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium">
            <IconPlayerPause size={15} />
            保持
          </span>
          <span
            title="挂断用户"
            aria-label="挂断用户"
            className="grid h-8 w-8 place-items-center rounded-full bg-destructive text-white [&_svg]:text-white"
          >
            <IconPhoneOff size={15} />
          </span>
        </div>
        <span
          title="展开通话控制"
          aria-label="展开通话控制"
          className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-border/60 bg-background/60 text-foreground/80"
        >
          <IconChevronDown size={16} />
        </span>
        <span className="ml-1 flex h-8 items-center gap-1 rounded-md px-2 text-xs font-medium text-foreground/70">
          <IconArrowBackUp size={14} />
          返回呼叫工作台
        </span>
      </div>
    </div>
  );
}

type ProposedState = "in-call" | "hold" | "consult" | "conference";

export function ProposedBar({
  state = "in-call",
  tooltipOn,
}: {
  state?: ProposedState;
  tooltipOn?: "transfer" | "endConsult" | "endAll";
}) {
  const title =
    state === "hold"
      ? "客户保持中"
      : state === "consult"
        ? `与 ${CALL.consultName} 咨询中`
        : state === "conference"
          ? "多方通话 3 人"
          : CALL.status;

  return (
    <div className="flex min-h-10 min-w-0 flex-1 items-center gap-3">
        <Status
          title={title}
          extra={state === "hold" ? CALL.holdDuration : undefined}
        />
        <div className="flex shrink-0 items-center gap-1">
          <IconBtn icon={<IconMicrophone size={16} />} label="静音" />
          {state === "in-call" && (
            <>
              <IconBtn icon={<IconPlayerPause size={16} />} label="保持" />
              <IconBtn icon={<IconDialpad size={16} />} label="按键" title="拨号盘" />
              <Divider />
              <IconBtn icon={<IconMessage size={16} />} label="短信" title="发短信" />
              <IconBtn
                icon={<IconArrowsExchange size={16} />}
                label="转接"
                tooltip={tooltipOn === "transfer" ? "转接" : undefined}
              />
              <IconBtn icon={<IconUserPlus size={16} />} label="咨询" />
              <IconBtn icon={<IconUsersGroup size={16} />} label="三方" title="添加参与人" />
              <IconBtn icon={<IconStar size={16} />} label="评价" title="邀请评价" />
              <Divider />
              <IconBtn icon={<IconPhoneOff size={16} />} label="挂断" title="挂断用户" solid />
            </>
          )}
          {state === "hold" && (
            <>
              <IconBtn icon={<IconPlayerPlay size={16} />} label="恢复" title="恢复通话" warning />
              <IconBtn icon={<IconDialpad size={16} />} label="按键" title="拨号盘" />
              <Divider />
              <IconBtn icon={<IconMessage size={16} />} label="短信" title="发短信" />
              <IconBtn icon={<IconArrowsExchange size={16} />} label="转接" />
              <IconBtn icon={<IconUserPlus size={16} />} label="咨询" />
              <IconBtn icon={<IconUsersGroup size={16} />} label="三方" title="添加参与人" />
            </>
          )}
          {state === "consult" && (
            <>
              <Divider />
              <IconBtn
                icon={<IconUserOff size={16} />}
                label="结束"
                title="结束咨询"
                warning
                tooltip={tooltipOn === "endConsult" ? "结束咨询" : undefined}
              />
            </>
          )}
          {state === "conference" && (
            <>
              <Divider />
              <IconBtn icon={<IconLogout size={16} />} label="离开" title="离开通话" danger />
              <IconBtn
                icon={<IconPhoneOff size={16} />}
                label="全挂"
                title="结束全部通话"
                danger
                tooltip={tooltipOn === "endAll" ? "结束全部通话" : undefined}
              />
              <Divider />
              <IconBtn icon={<IconPhoneOff size={16} />} label="挂断" title="挂断用户" solid />
            </>
          )}
        </div>
    </div>
  );
}

/** Hold + muted combined for the hold screen: mute stays available, hold is active. */
export function ProposedMutedHoldBar() {
  return (
    <div className="flex min-h-10 min-w-0 flex-1 items-center gap-3">
      <Status title="客户保持中" extra={CALL.holdDuration} />
      <div className="flex shrink-0 items-center gap-1">
        <IconBtn icon={<IconMicrophoneOff size={16} />} label="静音" title="已静音" active />
        <IconBtn icon={<IconPlayerPlay size={16} />} label="恢复" title="恢复通话" warning />
        <IconBtn icon={<IconDialpad size={16} />} label="按键" title="拨号盘" />
        <Divider />
        <IconBtn icon={<IconMessage size={16} />} label="短信" title="发短信" />
        <IconBtn icon={<IconArrowsExchange size={16} />} label="转接" />
        <IconBtn icon={<IconUserPlus size={16} />} label="咨询" />
        <IconBtn icon={<IconUsersGroup size={16} />} label="三方" title="添加参与人" />
      </div>
    </div>
  );
}

export function CallStrip({
  tone = "active",
  children,
}: {
  tone?: BarTone | "idle";
  children: ReactNode;
}) {
  const bg =
    tone === "idle"
      ? "border-border bg-background"
      : toneClass(tone);
  return (
    <div className={`flex items-center gap-3 border-b px-5 py-5 ${bg}`}>
      {children}
    </div>
  );
}

export function IdleDialRow() {
  return (
    <>
      <div className="relative flex h-10 w-[220px] items-center rounded-lg border border-border bg-background px-3 pr-9 text-sm text-muted-foreground shadow-sm">
        输入用户号码
        <span className="absolute inset-y-0 right-2 grid place-items-center text-muted-foreground">
          <IconDialpad size={18} />
        </span>
      </div>
      <div className="flex h-10 w-[190px] items-center justify-between rounded-lg border border-border bg-background px-3 text-sm shadow-sm">
        <span>20260526</span>
        <IconChevronDown size={14} className="text-muted-foreground" />
      </div>
      <span className="grid h-10 w-10 place-items-center rounded-lg border border-border bg-background text-foreground/80 shadow-sm">
        <IconMessage size={18} />
      </span>
      <span className="grid h-10 w-10 cursor-pointer place-items-center rounded-full bg-success text-white transition-colors hover:bg-success/80">
        <IconPhone size={18} />
      </span>
    </>
  );
}

