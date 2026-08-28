import type { ReactNode } from "react";
import { OutboundExecCallRecordsScreen } from "./screens/call-records";
import { OutboundExecOnCallScreen } from "./screens/on-call";
import { OutboundExecPreviewPanelScreen } from "./screens/preview-panel";
import { OutboundExecScreenPopScreen } from "./screens/screen-pop";
import { OutboundExecTaskListScreen } from "./screens/task-list";
import { OutboundExecWrapUpScreen } from "./screens/wrap-up";

interface PrototypeScreen {
  id: string;
  title: string;
  description: string;
  render: () => ReactNode;
}

function Frame({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div className="prototype-frame relative">
      {children}
      <div className="pointer-events-none absolute bottom-4 left-4 z-50 rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">
        {id} · 1440×900
      </div>
    </div>
  );
}

export const OutboundExecScreens: PrototypeScreen[] = [
  {
    id: "outbound-exec/task-list",
    title: "我的外呼任务 · 任务列表页",
    description: "进入我的外呼任务默认展示任务列表页：任务名称、状态、我的进度、截止时间与查看入口；左侧栏保持最近通话。",
    render: () => (
      <Frame id="outbound-exec/task-list">
        <OutboundExecTaskListScreen />
      </Frame>
    ),
  },
  {
    id: "outbound-exec/preview-panel",
    title: "我的外呼任务 · 任务执行页",
    description: "点击任务进入执行页：页头含返回任务列表与我的进度；对象列表展示最近呼叫摘要，右侧为对象预览卡与「业务记录 | 呼叫记录」面板 Tab，默认业务记录。",
    render: () => (
      <Frame id="outbound-exec/preview-panel">
        <OutboundExecPreviewPanelScreen />
      </Frame>
    ),
  },
  {
    id: "outbound-exec/call-records",
    title: "我的外呼任务 · 呼叫记录 Tab",
    description: "执行面板切换到呼叫记录 Tab：展示该对象全部呼叫记录（时间、结果、时长、接待客服、详情入口）。",
    render: () => (
      <Frame id="outbound-exec/call-records">
        <OutboundExecCallRecordsScreen />
      </Frame>
    ),
  },
  {
    id: "outbound-exec/on-call",
    title: "任务通话中 · 任务执行页",
    description: "任务通话发起后主区保持任务执行页，顶部通话条进入通话态；预览卡上「常规弹屏」入口保持可见，点击切换到常规弹屏。",
    render: () => (
      <Frame id="outbound-exec/on-call">
        <OutboundExecOnCallScreen />
      </Frame>
    ),
  },
  {
    id: "outbound-exec/screen-pop",
    title: "任务通话中 · 常规弹屏",
    description: "任务通话期间切换到常规弹屏三列：通话信息与实时字幕、客户信息、通话纪要/新建工单；可返回外呼任务，通话不中断。",
    render: () => (
      <Frame id="outbound-exec/screen-pop">
        <OutboundExecScreenPopScreen />
      </Frame>
    ),
  },
  {
    id: "outbound-exec/wrap-up",
    title: "我的外呼任务 · 话后处置屏",
    description: "通话结束进入整理态，执行面板替换为话后处置屏：通话事实、对象状态按钮组、业务字段、预约回拨与新建工单。",
    render: () => (
      <Frame id="outbound-exec/wrap-up">
        <OutboundExecWrapUpScreen />
      </Frame>
    ),
  },
];
