import type { ReactNode } from "react";
import { PersonalOutboundConfigScreen, PersonalOutboundRecordingScreen } from "./screens/config";
import { PersonalOutboundIntentSettingsScreen, PersonalOutboundNewIntentScreen } from "./screens/intent-settings";
import { PersonalOutboundRunningScreen } from "./screens/running";

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
      <div className="pointer-events-none absolute bottom-4 left-4 z-50 rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">{id} · 1440×900</div>
    </div>
  );
}

export const PersonalAutoOutboundScreens: PrototypeScreen[] = [
  { id: "personal-auto-outbound/config-ready", title: "个人自动外呼 · 启动配置", description: "选择本人开场录音和礼貌结束语、来源任务、主叫号码、兜底客服组与振铃并发；展示启动检查。", render: () => <Frame id="personal-auto-outbound/config-ready"><PersonalOutboundConfigScreen /></Frame> },
  { id: "personal-auto-outbound/config-recording", title: "个人自动外呼 · 直接录制", description: "录制礼貌结束语时展示输入设备、建议朗读文案、实时波形、计时与停止操作。", render: () => <Frame id="personal-auto-outbound/config-recording"><PersonalOutboundRecordingScreen /></Frame> },
  { id: "personal-auto-outbound/intent-settings", title: "呼叫中心设置 · 外呼预筛意图", description: "管理员新建、启停预筛意图，按一行一条维护相似表达与易混淆反例，并编辑相似度阈值。", render: () => <Frame id="personal-auto-outbound/intent-settings"><PersonalOutboundIntentSettingsScreen /></Frame> },
  { id: "personal-auto-outbound/intent-create", title: "呼叫中心设置 · 新建预筛意图", description: "填写意图名称和初始阈值；新意图默认停用，补足相似表达后才可启用。", render: () => <Frame id="personal-auto-outbound/intent-create"><PersonalOutboundNewIntentScreen /></Frame> },
  { id: "personal-auto-outbound/ringing", title: "个人自动外呼 · 并发振铃", description: "固定 4 行并发条：每行一路呼叫，从拨号到振铃。", render: () => <Frame id="personal-auto-outbound/ringing"><PersonalOutboundRunningScreen variant="ringing" /></Frame> },
  { id: "personal-auto-outbound/prescreen-gated", title: "个人自动外呼 · 接听预筛", description: "有人接听后该行进入预筛并停补号；其余振铃行继续，空槽不再补入。", render: () => <Frame id="personal-auto-outbound/prescreen-gated"><PersonalOutboundRunningScreen variant="screening" /></Frame> },
  { id: "personal-auto-outbound/lane-clearing", title: "个人自动外呼 · 挂断收口", description: "拒绝或未接通后该行淡出清空，同一槽位再补入下一个对象。", render: () => <Frame id="personal-auto-outbound/lane-clearing"><PersonalOutboundRunningScreen variant="clearing" /></Frame> },
  { id: "personal-auto-outbound/task-pop", title: "个人自动外呼 · 任务弹屏", description: "预筛非拒绝后整页换成任务弹屏：开场白 + 客户最后一句 + 业务记录，不再保留并发条。", render: () => <Frame id="personal-auto-outbound/task-pop"><PersonalOutboundRunningScreen variant="task-pop" /></Frame> },
  { id: "personal-auto-outbound/task-pop-no-script", title: "个人自动外呼 · 任务弹屏（无开场白）", description: "开场白选填为空时，弹屏只展示客户最后一句。", render: () => <Frame id="personal-auto-outbound/task-pop-no-script"><PersonalOutboundRunningScreen variant="task-pop-no-script" /></Frame> },
];
