import type { ReactNode } from "react"
import { BoardDirtyScreen, BoardPublishedScreen } from "./screens/board"
import {
  GeneratePreviewScreen,
  HardBlockScreen,
  PublishConfirmScreen,
  ResetConfirmScreen,
  SoftWarnScreen,
} from "./screens/dialogs"
import { RotationTemplateFormScreen } from "./screens/rotation-template"
import { RulesDetailScreen, RulesEmptyScreen, RulesListScreen } from "./screens/rules"

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

export const SchedulingRulesScreens: PrototypeScreen[] = [
  {
    id: "scheduling-rules/board",
    title: "规则排班 · 排班表（有未发布变更）",
    description:
      "两排工具栏：一排池/生成/复制/筛选 + 最右状态·重置·发布；二排视图·时间·本周 + 导出 Excel；规则集在生成弹窗选择。",
    render: () => (
      <Frame id="scheduling-rules/board">
        <BoardDirtyScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/board-published",
    title: "规则排班 · 已发布（无变更）",
    description: "Tag 为已发布；「重置为已发布」禁用（当前已是已发布结果）。",
    render: () => (
      <Frame id="scheduling-rules/board-published">
        <BoardPublishedScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/rules",
    title: "规则排班 · 规则集列表",
    description: "规则集名称、默认标记、目标/约束摘要、复制与删除。",
    render: () => (
      <Frame id="scheduling-rules/rules">
        <RulesListScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/rules-empty",
    title: "规则排班 · 规则空状态",
    description: "引导新建规则集。",
    render: () => (
      <Frame id="scheduling-rules/rules-empty">
        <RulesEmptyScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/rules-detail",
    title: "规则排班 · 规则详情",
    description: "基本信息、排班目标矩阵（单位：人）、工时约束、轮班模板列表。",
    render: () => (
      <Frame id="scheduling-rules/rules-detail">
        <RulesDetailScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/rotation-template",
    title: "规则排班 · 新建轮班模板",
    description: "轮班模板表单：名称、天序列（班次/休）、增删天、默认模板、预览。",
    render: () => (
      <Frame id="scheduling-rules/rotation-template">
        <RotationTemplateFormScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/generate",
    title: "规则排班 · 生成预览",
    description: "按规则生成弹窗：选择规则集、模式与范围、预览后确认写入。",
    render: () => (
      <Frame id="scheduling-rules/generate">
        <GeneratePreviewScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/publish",
    title: "规则排班 · 发布确认",
    description: "发布即确认并持久化本周快照；可覆盖上一份；外发仍靠导出。",
    render: () => (
      <Frame id="scheduling-rules/publish">
        <PublishConfirmScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/reset",
    title: "规则排班 · 重置确认",
    description: "丢弃发布后改动，将编辑态恢复为上次已发布结果。",
    render: () => (
      <Frame id="scheduling-rules/reset">
        <ResetConfirmScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/soft-warn",
    title: "规则排班 · 软约束确认",
    description: "软约束警告，可「仍要继续」。",
    render: () => (
      <Frame id="scheduling-rules/soft-warn">
        <SoftWarnScreen />
      </Frame>
    ),
  },
  {
    id: "scheduling-rules/hard-block",
    title: "规则排班 · 硬约束阻止",
    description: "硬约束冲突阻止写入。",
    render: () => (
      <Frame id="scheduling-rules/hard-block">
        <HardBlockScreen />
      </Frame>
    ),
  },
]
