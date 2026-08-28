import type { ReactNode } from "react"
import { CallTrajectoryBusinessScreen, CallTrajectoryTechnicalScreen } from "./screens/trajectory"

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

export const CallTrajectoryScreens: PrototypeScreen[] = [
  {
    id: "call-trajectory/business",
    title: "通话轨迹 · 业务视图",
    description: "通话详情抽屉默认态：全宽业务时间线、组合操作卡片与结束结算。",
    render: () => (
      <Frame id="call-trajectory/business">
        <CallTrajectoryBusinessScreen />
      </Frame>
    ),
  },
  {
    id: "call-trajectory/technical",
    title: "通话轨迹 · 技术详情",
    description: "技术排障态：媒体腿、原始事件 key、来源与一次直接转接的全部内部步骤。",
    render: () => (
      <Frame id="call-trajectory/technical">
        <CallTrajectoryTechnicalScreen />
      </Frame>
    ),
  },
]
