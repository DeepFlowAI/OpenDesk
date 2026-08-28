import type { ReactNode } from "react";
import { DEFAULT_AGENT_PROMPT, INVALID_AGENT_PROMPT } from "./fixtures";
import { SettingsScreen } from "./screens/settings";
import { WorkspaceScreen } from "./screens/workspace";

interface PrototypeScreen {
  id: string;
  title: string;
  description: string;
  render: () => ReactNode;
}

function PrototypeStamp({ text }: { text: string }) {
  return (
    <div className="pointer-events-none absolute bottom-4 left-4 z-50 rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">
      {text}
    </div>
  );
}

function Frame({ stamp, children }: { stamp: string; children: ReactNode }) {
  return (
    <div className="prototype-frame relative">
      {children}
      <PrototypeStamp text={stamp} />
    </div>
  );
}

export const LingoMasterScreens: PrototypeScreen[] = [
  {
    id: "lingomaster/settings-overview",
    title: "多语言大师 · 配置页",
    description: "管理后台采用纵向设置布局：每个分区均为上方标题说明、下方配置内容，不使用内部左侧分区栏；导航位于「会话纪要」之后。",
    render: () => (
      <Frame stamp="lingomaster/settings-overview · 1440×900">
        <SettingsScreen agentPrompt={DEFAULT_AGENT_PROMPT} />
      </Frame>
    ),
  },
  {
    id: "lingomaster/settings-validation-error",
    title: "多语言大师 · 校验错误态",
    description: "客服方向提示词缺少 {{message}} 变量：行内错误提示，保存按钮禁用。",
    render: () => (
      <Frame stamp="lingomaster/settings-validation-error · 1440×900">
        <SettingsScreen
          agentPrompt={INVALID_AGENT_PROMPT}
          agentError="提示词必须包含变量 {{message}}"
          saveDisabled
        />
      </Frame>
    ),
  },
  {
    id: "lingomaster/workspace-translated",
    title: "工作台 · 原文译文对照态",
    description:
      "按真实客服工作台还原。客服侧每条翻译消息同时展示原文和译文，无需点击切换；访客侧仍只收到最终译文。",
    render: () => (
      <Frame stamp="lingomaster/workspace-translated · 1440×900">
        <WorkspaceScreen variant="translated" />
      </Frame>
    ),
  },
  {
    id: "lingomaster/workspace-language-picker",
    title: "工作台 · 翻译控制浮层",
    description:
      "点击会话头部语种标记，可改选访客语种、设置访客消息译文目标语种、分别关闭双向翻译，或一键全部关闭。",
    render: () => (
      <Frame stamp="lingomaster/workspace-language-picker · 1440×900">
        <WorkspaceScreen variant="picker" />
      </Frame>
    ),
  },
  {
    id: "lingomaster/workspace-target-language-picker",
    title: "工作台 · 译文目标语种",
    description:
      "访客消息翻译默认跟随客服语种，也可在本会话固定选择其他目标语种；跟随模式会展示客服当前语种。",
    render: () => (
      <Frame stamp="lingomaster/workspace-target-language-picker · 1440×900">
        <WorkspaceScreen variant="target-picker" />
      </Frame>
    ),
  },
  {
    id: "lingomaster/workspace-outgoing-disabled",
    title: "工作台 · 关闭发送翻译",
    description:
      "发送消息翻译关闭后，仅停止模型翻译，发送流程不变；客服输入什么，访客就收到什么。会话头部展示关闭状态，输入框不重复提醒。",
    render: () => (
      <Frame stamp="lingomaster/workspace-outgoing-disabled · 1440×900">
        <WorkspaceScreen variant="outgoing-disabled" />
      </Frame>
    ),
  },
  {
    id: "lingomaster/workspace-send-translation-error",
    title: "工作台 · 翻译失败阻止发送",
    description:
      "发送翻译失败或超时时不创建消息、不通知访客；输入内容原样保留，并在输入框上方显示可重试的错误提示。",
    render: () => (
      <Frame stamp="lingomaster/workspace-send-translation-error · 1440×900">
        <WorkspaceScreen variant="send-error" />
      </Frame>
    ),
  },
];
