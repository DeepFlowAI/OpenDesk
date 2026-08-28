import type { ReactNode } from "react"
import {
  MyScheduleFilledScreen,
  MyScheduleNoShiftsScreen,
  MyScheduleUnpublishedScreen,
  MyScheduleWithManageScreen,
} from "./screens/me"
import { SchedulingMyNavEntryScreen } from "./screens/nav"

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

export const SchedulingMyScreens: PrototypeScreen[] = [
  {
    id: "scheduling-my/nav",
    title: "我的排班 · 主导航入口",
    description: "仅有 scheduling.my.view 时，左侧主导航出现「排班中心」；默认进我的排班。",
    render: () => (
      <Frame id="scheduling-my/nav">
        <SchedulingMyNavEntryScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-my/me",
    title: "我的排班 · 本周有班",
    description: "仅查看权：只有「我的排班」Tab；今日摘要 + 周一至周日班次芯片（仅本人、已发布）。",
    render: () => (
      <Frame id="scheduling-my/me">
        <MyScheduleFilledScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-my/me-unpublished",
    title: "我的排班 · 尚未发布",
    description: "该周无已发布快照时的空状态。",
    render: () => (
      <Frame id="scheduling-my/me-unpublished">
        <MyScheduleUnpublishedScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-my/me-no-shifts",
    title: "我的排班 · 已发布无班",
    description: "周已发布但本人无排班记录的空状态。",
    render: () => (
      <Frame id="scheduling-my/me-no-shifts">
        <MyScheduleNoShiftsScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-my/me-with-manage",
    title: "我的排班 · 含管理 Tab",
    description: "同时有 manage + my.view：我的排班 | 排班 | 班次管理 | 规则；当前高亮我的排班。",
    render: () => (
      <Frame id="scheduling-my/me-with-manage">
        <MyScheduleWithManageScreen />
      </Frame>
    ),
  },
]
