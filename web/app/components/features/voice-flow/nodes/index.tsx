'use client'
/**
 * Custom ReactFlow node visuals for the voice flow editor. All node types
 * live in this single file to keep the surface compact; each gets ~30 lines.
 */
import { Handle, Position, type NodeProps } from '@xyflow/react'
import {
  IconPlayerPlay,
  IconVolume,
  IconPhoneOff,
  IconUserCheck,
  IconKeyboard,
  IconGitBranch,
} from '@tabler/icons-react'
import {
  COLLECT_OUTLET_COLOR,
  NODE_COLOR,
  type AssignQueueData,
  type CollectData,
  type ConditionData,
  type HangupData,
  type PlayData,
} from '@/models/voice-flow-graph'

// Reusable card chrome
function NodeCard({
  color,
  icon,
  title,
  badge,
  selected,
  children,
  showInPort = true,
}: {
  color: string
  icon: React.ReactNode
  title: string
  badge?: string
  selected?: boolean
  children?: React.ReactNode
  showInPort?: boolean
}) {
  return (
    <div
      className="relative min-w-[180px] rounded-lg bg-white shadow-sm"
      style={{
        boxShadow: selected
          ? `0 0 0 2px ${color}, 0 1px 3px rgba(0,0,0,0.08)`
          : `0 0 0 2px ${color}40, 0 1px 3px rgba(0,0,0,0.05)`,
      }}
    >
      {showInPort && (
        <Handle
          type="target"
          position={Position.Left}
          style={{
            top: 18, width: 2, height: 14, background: color, borderRadius: 0, border: 0,
          }}
          isConnectable
        />
      )}
      <div
        className="flex items-center gap-1.5 rounded-t-lg px-3 py-1.5 text-xs font-semibold text-white"
        style={{ background: color }}
      >
        {icon}
        <span className="flex-1 truncate">{title}</span>
        {badge && <span className="rounded bg-white/25 px-1 text-[10px]">{badge}</span>}
      </div>
      {children && <div className="px-3 py-2 text-[11px] text-foreground/80">{children}</div>}
    </div>
  )
}

// ──────────────── start ────────────────

export function StartNodeView({ selected }: NodeProps) {
  return (
    <div
      className="relative flex h-10 items-center gap-2 rounded-full bg-black px-4 text-sm text-white shadow"
      style={{ boxShadow: selected ? '0 0 0 2px #111827' : undefined }}
    >
      <IconPlayerPlay size={16} fill="white" />
      <span className="font-medium">开始</span>
      <Handle
        type="source"
        position={Position.Right}
        id="next"
        style={{ width: 10, height: 10, background: '#111827', border: '2px solid white' }}
      />
    </div>
  )
}

// ──────────────── play ────────────────

export function PlayNodeView({ data, selected }: NodeProps) {
  const d = data as PlayData
  const preview =
    d.prompt.kind === 'tts' ? d.prompt.text || '未配置语音文案' : `音频文件 #${d.prompt.asset_id}`
  return (
    <NodeCard
      color={NODE_COLOR.play}
      icon={<IconVolume size={14} />}
      title="纯语音"
      badge="play"
      selected={selected}
    >
      <p className="line-clamp-2">{preview}</p>
      <Handle
        type="source"
        position={Position.Right}
        id="next"
        style={{ width: 8, height: 8, background: NODE_COLOR.play, top: '50%' }}
      />
    </NodeCard>
  )
}

// ──────────────── collect ────────────────

const COLLECT_OUTLETS: { key: 'success' | 'no_input' | 'no_match' | 'error'; label: string }[] = [
  { key: 'success', label: '成功' },
  { key: 'no_input', label: '无输入' },
  { key: 'no_match', label: '无匹配' },
  { key: 'error', label: '错误' },
]

export function CollectNodeView({ data, selected }: NodeProps) {
  const d = data as CollectData
  const modeLabel = { single: '单位数字', multi: '多位数字', any: '任意按键' }[d.input.mode]
  return (
    <NodeCard
      color={NODE_COLOR.collect}
      icon={<IconKeyboard size={14} />}
      title="收集输入"
      badge="collect"
      selected={selected}
    >
      <p>DTMF · {modeLabel}</p>
      <p className="mt-0.5 text-foreground/60">→ {d.output_variable}</p>
      {COLLECT_OUTLETS.map((o, i) => (
        <Handle
          key={o.key}
          type="source"
          position={Position.Right}
          id={o.key}
          style={{
            top: 16 + i * 16,
            width: 8,
            height: 8,
            background: COLLECT_OUTLET_COLOR[o.key],
          }}
        />
      ))}
    </NodeCard>
  )
}

// ──────────────── condition ────────────────

export function ConditionNodeView({ data, selected }: NodeProps) {
  const d = data as ConditionData
  return (
    <NodeCard
      color={NODE_COLOR.condition}
      icon={<IconGitBranch size={14} />}
      title="信息判定"
      badge="condition"
      selected={selected}
    >
      {d.groups.map((g, i) => (
        <div key={g.id} className="flex items-center gap-1">
          <span className="text-foreground/70">[{g.name}]</span>
          <Handle
            type="source"
            position={Position.Right}
            id={g.id}
            style={{
              top: 16 + i * 16,
              width: 8,
              height: 8,
              background: NODE_COLOR.condition,
            }}
          />
        </div>
      ))}
      <div className="mt-1 text-foreground/50">默认</div>
      <Handle
        type="source"
        position={Position.Right}
        id="default"
        style={{
          top: 16 + d.groups.length * 16,
          width: 8,
          height: 8,
          background: '#9CA3AF',
        }}
      />
    </NodeCard>
  )
}

// ──────────────── assign_queue ────────────────

export function AssignQueueNodeView({ data, selected }: NodeProps) {
  const d = data as AssignQueueData
  const targets = assignQueueTargets(d)
  const strategy = assignQueueStrategyLabel(d.target_strategy)
  const customPrompt = Boolean(d.queue_prompt_text && d.queue_prompt_text !== '正在为您转接，请稍候。')
  const targetSummary =
    d.target_strategy === 'sequential_overflow'
      ? targets.length
        ? `${strategy}：${targets.slice(0, 2).map(queueTargetLabel).join(' → ')}${targets.length > 2 ? ` 等 ${targets.length} 个队列` : ''}`
        : '未选择队列'
      : targets.length
        ? `${strategy}：${targets.length} 个候选队列`
        : '未选择队列'
  // assign_queue has a single outlet: `timeout`. On a successful bridge the
  // workflow ends (user is now talking directly to the agent through the
  // kernel), so there's no `next` outlet — connecting `timeout` is only
  // required if you want a custom path when no agent picks up in time.
  return (
    <NodeCard
      color={NODE_COLOR.assign_queue}
      icon={<IconUserCheck size={14} />}
      title="分配队列"
      badge="assignQueue"
      selected={selected}
    >
      <p>{targetSummary}</p>
      {customPrompt && <p className="text-foreground/60">自定义排队提示</p>}
      {d.timeout_seconds && (
        <p className="text-foreground/60">超时 {d.timeout_seconds}s → 跳转</p>
      )}
      <Handle
        type="source"
        position={Position.Right}
        id="timeout"
        style={{ top: 20, width: 8, height: 8, background: '#9CA3AF' }}
      />
    </NodeCard>
  )
}

function assignQueueTargets(d: AssignQueueData): AssignQueueData['queue_targets'] {
  if (d.queue_targets?.length) return d.queue_targets
  if (d.employee_group_id) {
    return [{ queue_type: 'employee_group', queue_id: d.employee_group_id }]
  }
  return []
}

function assignQueueStrategyLabel(strategy: AssignQueueData['target_strategy'] | undefined): string {
  if (strategy === 'least_waiting_count') return '最少排队队列'
  if (strategy === 'shortest_tail_wait') return '最短排队时间队列'
  return '顺序溢出'
}

function queueTargetLabel(target: AssignQueueData['queue_targets'][number]): string {
  const prefix =
    target.queue_type === 'user_field'
      ? '用户字段'
      : target.queue_type === 'employee'
        ? '员工'
        : '员工组'
  return target.queue_id ? `${prefix} #${target.queue_id}` : `未选择${prefix}`
}

// ──────────────── hangup ────────────────

export function HangupNodeView({ data, selected }: NodeProps) {
  const d = data as HangupData
  return (
    <div
      className="relative flex h-10 items-center gap-2 rounded-full px-4 text-sm text-white shadow"
      style={{
        background: NODE_COLOR.hangup,
        boxShadow: selected ? '0 0 0 2px #EF4444' : undefined,
      }}
    >
      <IconPhoneOff size={16} />
      <span className="font-medium">挂断</span>
      {d.pre_play && <span className="text-[10px] opacity-80">含播报</span>}
      <Handle
        type="target"
        position={Position.Left}
        style={{ width: 2, height: 14, background: NODE_COLOR.hangup, top: 16, borderRadius: 0, border: 0 }}
      />
    </div>
  )
}

// Map for ReactFlow
export const NODE_TYPES = {
  start: StartNodeView,
  play: PlayNodeView,
  collect: CollectNodeView,
  condition: ConditionNodeView,
  assign_queue: AssignQueueNodeView,
  hangup: HangupNodeView,
}
