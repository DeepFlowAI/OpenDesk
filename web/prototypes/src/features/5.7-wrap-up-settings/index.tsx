import type { ReactNode } from "react"
import { AutoOutboundTaskFormScreen, CallCenterSettingsScreen } from "./screens/settings"
import {
  AutoOutboundAgentWrapUpScreen,
  WorkspaceWrapUpScreen,
} from "./screens/workspace"

interface PrototypeScreen {
  id: string
  title: string
  description: string
  render: () => ReactNode
}

function Frame({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div className="prototype-frame relative">
      {children}
      <div className="pointer-events-none absolute bottom-4 left-4 z-[100] rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">
        {id} · 1440×900
      </div>
    </div>
  )
}

export const WrapUpSettingsScreens: PrototypeScreen[] = [
  {
    id: "wrap-up-settings/admin-default",
    title: "呼叫中心设置 · 整理中默认 30 秒",
    description: "通话转写下方新增「整理中」区块，带本区块独立保存；页底保存仍只覆盖转写与提示音。",
    render: () => (
      <Frame id="wrap-up-settings/admin-default">
        <CallCenterSettingsScreen duration="30" />
      </Frame>
    ),
  },
  {
    id: "wrap-up-settings/admin-zero",
    title: "呼叫中心设置 · 整理中为 0",
    description: "时长设为 0 时展示「挂断后直接就绪」说明，本区块保存可点。",
    render: () => (
      <Frame id="wrap-up-settings/admin-zero">
        <CallCenterSettingsScreen duration="0" dirty />
      </Frame>
    ),
  },
  {
    id: "wrap-up-settings/admin-invalid",
    title: "呼叫中心设置 · 时长校验失败",
    description: "超过 60 秒时输入框报错，保存禁用。",
    render: () => (
      <Frame id="wrap-up-settings/admin-invalid">
        <CallCenterSettingsScreen duration="90" invalid dirty />
      </Frame>
    ),
  },
  {
    id: "wrap-up-settings/workspace-wrap-up",
    title: "工作台 · 整理中倒计时",
    description: "呼入挂断后进入整理面板；倒计时纯文字紧挨完成整理按钮左侧。",
    render: () => (
      <Frame id="wrap-up-settings/workspace-wrap-up">
        <WorkspaceWrapUpScreen />
      </Frame>
    ),
  },
  {
    id: "wrap-up-settings/task-form",
    title: "自动外呼任务 · 话后处理时长说明",
    description: "坐席接待配置补充辅助说明：超时结束整理中、坐席就绪，不自动提交业务记录。",
    render: () => (
      <Frame id="wrap-up-settings/task-form">
        <AutoOutboundTaskFormScreen />
      </Frame>
    ),
  },
  {
    id: "wrap-up-settings/task-wrap-up",
    title: "工作台 · 自动外呼整理中",
    description: "通话条剩余时长与任务话后处理共用同一倒计时；业务记录不再另显示一套秒数。",
    render: () => (
      <Frame id="wrap-up-settings/task-wrap-up">
        <AutoOutboundAgentWrapUpScreen />
      </Frame>
    ),
  },
]
