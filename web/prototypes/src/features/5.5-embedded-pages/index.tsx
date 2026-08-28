import type { ReactNode } from "react";
import { CallSettingsScreen, ChatSettingsScreen } from "./screens/list";
import { CallEditIframeScreen, ChatEditIframeScreen, ChatEditReactScreen } from "./screens/edit";
import { ChatAuxIframeScreen, ChatAuxReactScreen } from "./screens/chat-auxiliary";
import { CallPopEmbeddedScreen, CallPopSystemScreen } from "./screens/call-pop";

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

export const EmbeddedPagesScreens: PrototypeScreen[] = [
  {
    id: "embedded-pages/chat-settings",
    title: "会话设置 · 辅助区嵌入页面",
    description: "在线客服 → 会话设置页新增「辅助区嵌入页面」区块；列表仅展示辅助区页面，无嵌入位置列。",
    render: () => <Frame id="embedded-pages/chat-settings"><ChatSettingsScreen /></Frame>,
  },
  {
    id: "embedded-pages/chat-edit-iframe",
    title: "会话设置 · 编辑 iframe 页面",
    description: "辅助区 iframe 表单：返回会话设置；URL 变量为会话 / 访客相关字段。",
    render: () => <Frame id="embedded-pages/chat-edit-iframe"><ChatEditIframeScreen /></Frame>,
  },
  {
    id: "embedded-pages/chat-edit-react",
    title: "会话设置 · 编辑 React 代码页面",
    description: "辅助区 React 代码表单：代码编辑器 + 校验 / 预览 + 初始参数 JSON。",
    render: () => <Frame id="embedded-pages/chat-edit-react"><ChatEditReactScreen /></Frame>,
  },
  {
    id: "embedded-pages/chat-aux-iframe",
    title: "在线工作台 · 辅助区嵌入 Tab（iframe）",
    description: "嵌入 Tab 追加在知识库之后；iframe 页面内展示第三方 CRM 会员档案。",
    render: () => <Frame id="embedded-pages/chat-aux-iframe"><ChatAuxIframeScreen /></Frame>,
  },
  {
    id: "embedded-pages/chat-aux-react",
    title: "在线工作台 · 辅助区嵌入 Tab（React 代码）",
    description: "React 代码类型渲染自定义服务提醒面板。",
    render: () => <Frame id="embedded-pages/chat-aux-react"><ChatAuxReactScreen /></Frame>,
  },
  {
    id: "embedded-pages/call-settings",
    title: "呼叫中心设置 · 弹屏嵌入页面",
    description: "呼叫中心 → 呼叫中心设置页新增「弹屏嵌入页面」区块，与转写 / 提示音并列。",
    render: () => <Frame id="embedded-pages/call-settings"><CallSettingsScreen /></Frame>,
  },
  {
    id: "embedded-pages/call-edit-iframe",
    title: "呼叫中心设置 · 编辑 iframe 页面",
    description: "弹屏 iframe 表单：返回呼叫中心设置；URL 变量为通话相关字段，默认聚焦开启。",
    render: () => <Frame id="embedded-pages/call-edit-iframe"><CallEditIframeScreen /></Frame>,
  },
  {
    id: "embedded-pages/call-pop-system",
    title: "呼叫中心 · 系统弹屏 Tab",
    description: "弹屏区左上角新增 Tab 条；「系统弹屏」固定首个 Tab，内容为现有三列卡片。",
    render: () => <Frame id="embedded-pages/call-pop-system"><CallPopSystemScreen /></Frame>,
  },
  {
    id: "embedded-pages/call-pop-embedded",
    title: "呼叫中心 · 嵌入页面 Tab",
    description: "嵌入 Tab 激活时整区渲染第三方订单查询页；默认聚焦页面在新来电弹屏时自动激活。",
    render: () => <Frame id="embedded-pages/call-pop-embedded"><CallPopEmbeddedScreen /></Frame>,
  },
];
