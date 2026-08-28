import { IconPlayerPause, IconSquare } from "@tabler/icons-react";
import { ConcurrencyLanes, OnCallBar, RunningCallBar, SessionHeader, TaskPopPanel } from "../components/session-ui";
import { PersonalOutboundWorkspaceShell } from "../components/workspace-shell";
import { CLEARING_LANES, OPENING_SCRIPT, RINGING_LANES, SCREENING_LANES, TASK_POP_CUSTOMER, type LaneSlot } from "../fixtures";

type RunningVariant = "ringing" | "screening" | "clearing" | "task-pop" | "task-pop-no-script";

const VARIANT_DATA: Record<
  RunningVariant,
  {
    status: string;
    statusTone: "info" | "warning" | "success";
    agentState: "就绪" | "忙碌";
    barHint?: string;
    lanes?: LaneSlot[];
    endedHint?: string;
    showTaskPop?: boolean;
    openingScript?: string;
  }
> = {
  ringing: {
    status: "运行中 · 正在补号 4/4",
    statusTone: "info",
    agentState: "就绪",
    barHint: "个人自动外呼进行中 · 振铃 4 / 4",
    lanes: RINGING_LANES,
    endedHint: "本次已结束 0 通 · 未接通后该行清空并补入下一个对象",
  },
  screening: {
    status: "运行中 · 预筛中，已停补号",
    statusTone: "warning",
    agentState: "就绪",
    barHint: "已有客户接听，已暂停补充新呼叫",
    lanes: SCREENING_LANES,
    endedHint: "预筛拒绝或挂机后该行收口；非拒绝才切入任务弹屏",
  },
  clearing: {
    status: "运行中 · 正在补号 3/4",
    statusTone: "info",
    agentState: "就绪",
    barHint: "个人自动外呼进行中 · 一路已结束，正在补号",
    lanes: CLEARING_LANES,
    endedHint: "第 3 行明确拒绝后正在清空；第 4 行已补入新对象",
  },
  "task-pop": {
    status: "运行中 · 你正在通话",
    statusTone: "success",
    agentState: "忙碌",
    showTaskPop: true,
    openingScript: OPENING_SCRIPT,
  },
  "task-pop-no-script": {
    status: "运行中 · 你正在通话",
    statusTone: "success",
    agentState: "忙碌",
    showTaskPop: true,
  },
};

const SESSION_ACTIONS = (
  <>
    <button className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium">
      <IconPlayerPause size={16} />
      暂停
    </button>
    <button className="inline-flex h-9 items-center gap-2 rounded-md border border-destructive/30 bg-background px-3 text-sm font-medium text-destructive">
      <IconSquare size={14} />
      停止
    </button>
  </>
);

export function PersonalOutboundRunningScreen({ variant }: { variant: RunningVariant }) {
  const data = VARIANT_DATA[variant];
  const onCall = Boolean(data.showTaskPop);
  return (
    <PersonalOutboundWorkspaceShell
      agentState={data.agentState}
      callBar={
        onCall ? (
          <OnCallBar name={TASK_POP_CUSTOMER.name} phone={TASK_POP_CUSTOMER.phone} />
        ) : (
          <RunningCallBar hint={data.barHint ?? ""} />
        )
      }
    >
      <div className="flex h-full flex-col">
        <SessionHeader status={data.status} statusTone={data.statusTone} actions={SESSION_ACTIONS} />
        <div className="min-h-0 flex-1 overflow-hidden p-6">
          {onCall ? (
            <TaskPopPanel
              name={TASK_POP_CUSTOMER.name}
              phone={TASK_POP_CUSTOMER.phone}
              task={TASK_POP_CUSTOMER.task}
              openingScript={data.openingScript}
              lastUtterance={TASK_POP_CUSTOMER.lastUtterance}
            />
          ) : (
            <div className="flex h-full flex-col gap-4">
              <ConcurrencyLanes lanes={data.lanes ?? []} />
              <p className="px-1 text-[11px] text-muted-foreground">{data.endedHint}</p>
            </div>
          )}
        </div>
      </div>
    </PersonalOutboundWorkspaceShell>
  );
}
