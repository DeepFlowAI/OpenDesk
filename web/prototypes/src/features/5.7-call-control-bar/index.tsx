import type { ReactNode } from "react";
import { CallControlCompareScreen } from "./screens/compare";
import { CallControlConferenceScreen } from "./screens/conference";
import { CallControlConsultScreen } from "./screens/consult";
import { CallControlGlobalScreen } from "./screens/global";
import { CallControlHoldScreen } from "./screens/hold";
import { CallControlInCallScreen } from "./screens/in-call";
import { CallControlTooltipScreen } from "./screens/tooltip";

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

export const CallControlBarScreens: PrototypeScreen[] = [
  {
    id: "call-control/compare",
    title: "通话控制台 · 现状 vs 提案",
    description: "对照空闲发起呼叫区、提案同条带高度的图标+一词名称，以及现状展开后变高的两行按钮。",
    render: () => (
      <Frame id="call-control/compare">
        <CallControlCompareScreen />
      </Frame>
    ),
  },
  {
    id: "call-control/in-call",
    title: "通话控制台 · 单路通话",
    description: "通话中无号码输入框；静音、保持旁有「按键」打开拨号盘，其余操作为图标加一词名称。",
    render: () => (
      <Frame id="call-control/in-call">
        <CallControlInCallScreen />
      </Frame>
    ),
  },
  {
    id: "call-control/hold",
    title: "通话控制台 · 保持且已静音",
    description: "保持中底色切到警告；静音与恢复通话用激活底和图标切换表达，不只靠颜色。",
    render: () => (
      <Frame id="call-control/hold">
        <CallControlHoldScreen />
      </Frame>
    ),
  },
  {
    id: "call-control/consult",
    title: "通话控制台 · 咨询中",
    description: "原咨询位变为结束咨询；转接、三方和挂断用户不出现，避免和挂断混淆。",
    render: () => (
      <Frame id="call-control/consult">
        <CallControlConsultScreen />
      </Frame>
    ),
  },
  {
    id: "call-control/conference",
    title: "通话控制台 · 三方通话",
    description: "离开通话、结束全部通话、挂断用户同时可见，语义用描边 / 实心区分。",
    render: () => (
      <Frame id="call-control/conference">
        <CallControlConferenceScreen />
      </Frame>
    ),
  },
  {
    id: "call-control/global",
    title: "通话控制台 · 全局顶栏",
    description: "现网紧凑条只改两处：展开/收起改成 chevron，挂断改成红圆白图标。",
    render: () => (
      <Frame id="call-control/global">
        <CallControlGlobalScreen />
      </Frame>
    ),
  },
  {
    id: "call-control/tooltip",
    title: "通话控制台 · Tooltip",
    description: "图标下已有一词名称；悬停仍可看到完整操作名。",
    render: () => (
      <Frame id="call-control/tooltip">
        <CallControlTooltipScreen />
      </Frame>
    ),
  },
];
