'use client'

import { Handle, Position, type NodeProps } from '@xyflow/react'
import {
  IconFlag,
  IconGitBranch,
  IconSquareRoundedCheck,
  IconStar,
  IconVolume,
} from '@tabler/icons-react'
import type { SatisfactionQuestionData } from '@/models/satisfaction-flow'
import { NODE_COLOR } from '@/models/voice-flow-graph'

const COLORS = {
  start: NODE_COLOR.start,
  play: NODE_COLOR.play,
  question: NODE_COLOR.collect,
  condition: NODE_COLOR.condition,
  end: NODE_COLOR.assign_queue,
} as const

function Card({
  color,
  icon,
  title,
  selected,
  children,
  sourceHandles,
  badge,
}: {
  color: string
  icon: React.ReactNode
  title: string
  selected?: boolean
  children?: React.ReactNode
  sourceHandles: string[]
  badge?: string
}) {
  return (
    <div
      className="relative w-[220px] max-w-[220px] rounded-lg bg-white shadow-sm"
      style={{
        boxShadow: selected
          ? `0 0 0 2px ${color}, 0 1px 3px rgba(0,0,0,0.08)`
          : `0 0 0 2px ${color}40, 0 1px 3px rgba(0,0,0,0.05)`,
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        style={{ top: 18, width: 2, height: 14, background: color, borderRadius: 0, border: 0 }}
      />
      <div className="flex items-center gap-1.5 rounded-t-lg px-3 py-1.5 text-xs font-semibold text-white" style={{ background: color }}>
        {icon}
        <span className="flex-1 truncate">{title}</span>
        {badge && <span className="rounded bg-white/25 px-1 text-[10px]">{badge}</span>}
      </div>
      {children && <div className="px-3 py-2 text-[11px] break-words text-foreground/80 [overflow-wrap:anywhere]">{children}</div>}
      {sourceHandles.map((handle, index) => (
        <Handle
          key={handle}
          id={handle}
          type="source"
          position={Position.Right}
          style={{ width: 8, height: 8, background: color, top: sourceHandles.length === 1 ? '50%' : 16 + index * 16 }}
        />
      ))}
    </div>
  )
}

export function StartNode({ selected }: NodeProps) {
  return (
    <div
      className="relative flex h-10 items-center gap-2 rounded-full bg-black px-4 text-sm text-white shadow"
      style={{ boxShadow: selected ? '0 0 0 2px #111827' : undefined }}
    >
      <IconFlag size={16} />
      <span className="font-medium">开始</span>
      <Handle type="source" position={Position.Right} id="next" style={{ width: 10, height: 10, background: COLORS.start, border: '2px solid white' }} />
    </div>
  )
}

export function PlayNode({ data, selected }: NodeProps) {
  const prompt = data.prompt as { text?: string } | undefined
  return <Card color={COLORS.play} icon={<IconVolume size={14} />} title="播放提示" badge="play" selected={selected} sourceHandles={['next']}><p className="line-clamp-3 break-all">{prompt?.text || '音频提示'}</p></Card>
}

export function QuestionNode({ data, selected }: NodeProps) {
  const question = data as unknown as SatisfactionQuestionData
  const keys = question.options?.map((option) => option.dtmf).join('、') || '—'
  return <Card color={COLORS.question} icon={<IconStar size={14} />} title="评价问题" badge="question" selected={selected} sourceHandles={['answered', 'no_input', 'no_match', 'error']}><p className="font-medium text-foreground">{question.name || '未命名问题'}</p><p className="mt-0.5 text-foreground/60">{question.options?.length ?? 0} 个选项 · 按 {keys}</p></Card>
}

export function ConditionNode({ data, selected }: NodeProps) {
  const groups = (data.groups as Array<{ id: string; name: string }> | undefined) ?? []
  return <Card color={COLORS.condition} icon={<IconGitBranch size={14} />} title="条件判断" badge="condition" selected={selected} sourceHandles={[...groups.map((group) => group.id), 'default']}><p>{groups.length} 个条件组 + 默认出口</p></Card>
}

export function EndNode({ data, selected }: NodeProps) {
  const completion = data.completion_type === 'incomplete' ? '未完成结束' : '正常完成'
  return <Card color={COLORS.end} icon={<IconSquareRoundedCheck size={14} />} title="结束" badge="end" selected={selected} sourceHandles={[]}><p>{completion}</p></Card>
}

export const SATISFACTION_NODE_COLOR = COLORS

export const SATISFACTION_NODE_TYPES = {
  start: StartNode,
  play: PlayNode,
  question: QuestionNode,
  condition: ConditionNode,
  end: EndNode,
}
