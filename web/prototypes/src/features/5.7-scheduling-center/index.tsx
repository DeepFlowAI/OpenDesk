import type { ReactNode } from "react"
import {
  BoardAgentDayScreen,
  BoardCalendarScreen,
  BoardEmptyPoolScreen,
  BoardFilledScreen,
} from "./screens/board"
import {
  AddAgentsDialogScreen,
  CopyWeekDialogScreen,
  ShiftFormDialogScreen,
} from "./screens/dialogs"
import { SchedulingNavEntryScreen } from "./screens/nav"
import { ShiftsScreen } from "./screens/shifts"

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
      <div className="pointer-events-none absolute bottom-4 left-4 z-50 rounded-md border border-border bg-background/90 px-2.5 py-1 font-mono text-[10px] text-muted-foreground shadow-sm backdrop-blur">
        {id} · 1440×900
      </div>
    </div>
  )
}

export const SchedulingCenterScreens: PrototypeScreen[] = [
  {
    id: "scheduling/nav",
    title: "主导航 · 排班中心入口",
    description: "前台主导航在「学习中心」之后新增「排班中心」；点击打开 /scheduling 独立全屏页。",
    render: () => (
      <Frame id="scheduling/nav">
        <SchedulingNavEntryScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/board-empty-pool",
    title: "排班 · 未选排班池",
    description: "进入排班须先选员工组；导出与复制禁用；引导空状态。",
    render: () => (
      <Frame id="scheduling/board-empty-pool">
        <BoardEmptyPoolScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/board",
    title: "排班 · 班次+日期",
    description: "默认视图：横轴天、纵轴班次；视图切换；格子加人；底部「当日统计」行按列汇总。",
    render: () => (
      <Frame id="scheduling/board">
        <BoardFilledScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/agent-day",
    title: "排班 · 员工+日期",
    description: "纵轴员工、横轴天；格内班次为固定宽度竖向色卡，按时段排序后统一靠左；底部当日统计线框标签。",
    render: () => (
      <Frame id="scheduling/agent-day">
        <BoardAgentDayScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/calendar",
    title: "排班 · 日历（含日详情）",
    description: "月历选中某日后，右侧展开当日详情看板：按班次列人、添加员工、关闭。",
    render: () => (
      <Frame id="scheduling/calendar">
        <BoardCalendarScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/add-agents",
    title: "排班 · 添加员工",
    description: "格子加人弹层：仅池内人员；已在本格置灰；支持多选。",
    render: () => (
      <Frame id="scheduling/add-agents">
        <AddAgentsDialogScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/copy-week",
    title: "排班 · 复制上周",
    description: "二次确认：跳过已有格子（默认）/ 覆盖已有格子。",
    render: () => (
      <Frame id="scheduling/copy-week">
        <CopyWeekDialogScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/shifts",
    title: "班次管理 · 列表",
    description: "预置早 / 中 / 晚；颜色、时段、排序、启用状态；有记录时删除禁用。",
    render: () => (
      <Frame id="scheduling/shifts">
        <ShiftsScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling/shift-form",
    title: "班次管理 · 新建班次",
    description: "Dialog：名称、起止时间（可跨夜）、颜色、排序、启用。",
    render: () => (
      <Frame id="scheduling/shift-form">
        <ShiftFormDialogScreen />
      </Frame>
    ),
  },
]
