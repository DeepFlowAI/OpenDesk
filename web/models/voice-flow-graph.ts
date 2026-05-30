/**
 * Voice flow graph types — mirrors the backend Pydantic discriminated unions
 * defined in server/app/schemas/voice_flow_graph.py.
 *
 * Keep the two in sync when extending node types or operators.
 */

export type NodeType =
  | 'start'
  | 'play'
  | 'collect'
  | 'condition'
  | 'assign_queue'
  | 'hangup'

// ───────────── Prompt (TTS or audio) ─────────────

export type TtsPrompt = { kind: 'tts'; text: string }
export type AudioPromptRef = { kind: 'audio'; asset_id: number }
export type Prompt = TtsPrompt | AudioPromptRef

// ───────────── Node-specific data ─────────────

export type StartData = Record<string, never>

export type PlayData = { prompt: Prompt }

export type CollectMode = 'single' | 'multi' | 'any'

export type CollectData = {
  prompt: Prompt
  barge_in_disabled: boolean
  input: {
    mode: CollectMode
    min_digits: number
    max_digits: number
    terminator: '#' | '*' | null
    skip_terminator_on_single: boolean
  }
  timeout: { first_input_ms: number; inter_digit_ms: number }
  retry: { enabled: boolean; no_input: number; no_match: number }
  output_variable: string
}

export type ConditionOperator =
  | 'eq'
  | 'neq'
  | 'any_eq'
  | 'any_neq'
  | 'is_empty'
  | 'is_not_empty'
  | 'time_in'
  | 'time_not_in'

export type ConditionItem = {
  variable: string
  operator: ConditionOperator
  value: string | string[] | number | null
}

export type ConditionGroup = {
  id: string
  name: string
  logic: 'AND' | 'OR'
  conditions: ConditionItem[]
}

export type ConditionData = { groups: ConditionGroup[] }

export type AssignQueueData = {
  employee_group_id: number | null
  timeout_seconds: number | null
}

export type HangupData = { pre_play: Prompt | null }

// ───────────── Node + Edge + Graph ─────────────

export type NodePosition = { x: number; y: number }

type NodeBase<T extends NodeType, D> = {
  id: string
  type: T
  position: NodePosition
  data: D
}

export type StartNode = NodeBase<'start', StartData>
export type PlayNode = NodeBase<'play', PlayData>
export type CollectNode = NodeBase<'collect', CollectData>
export type ConditionNode = NodeBase<'condition', ConditionData>
export type AssignQueueNode = NodeBase<'assign_queue', AssignQueueData>
export type HangupNode = NodeBase<'hangup', HangupData>

export type FlowNode =
  | StartNode
  | PlayNode
  | CollectNode
  | ConditionNode
  | AssignQueueNode
  | HangupNode

export type FlowEdge = {
  id: string
  source: string
  target: string
  source_handle: string
}

export type GraphVariable = { name: string; source_node_id: string }

export type VoiceFlowGraph = {
  version: number
  nodes: FlowNode[]
  edges: FlowEdge[]
  variables: GraphVariable[]
}

// ───────────── Helpers ─────────────

export function genNodeId(): string {
  return `n_${Math.random().toString(36).slice(2, 10)}`
}

export function genEdgeId(): string {
  return `e_${Math.random().toString(36).slice(2, 10)}`
}

export function defaultPromptTts(): Prompt {
  return { kind: 'tts', text: '' }
}

export function defaultCollectData(): CollectData {
  return {
    prompt: defaultPromptTts(),
    barge_in_disabled: false,
    input: {
      mode: 'single',
      min_digits: 1,
      max_digits: 1,
      terminator: '#',
      skip_terminator_on_single: true,
    },
    timeout: { first_input_ms: 5000, inter_digit_ms: 10000 },
    retry: { enabled: false, no_input: 1, no_match: 1 },
    output_variable: 'user_input',
  }
}

export function defaultGroup(): ConditionGroup {
  return {
    id: `g_${Math.random().toString(36).slice(2, 8)}`,
    name: '条件组',
    logic: 'AND',
    conditions: [{ variable: 'sys.caller_number', operator: 'eq', value: '' }],
  }
}

export function defaultDataFor(type: NodeType): FlowNode['data'] {
  switch (type) {
    case 'start':
      return {}
    case 'play':
      return { prompt: defaultPromptTts() }
    case 'collect':
      return defaultCollectData()
    case 'condition':
      return { groups: [defaultGroup()] }
    case 'assign_queue':
      return { employee_group_id: null, timeout_seconds: 60 }
    case 'hangup':
      return { pre_play: null }
  }
}

export const NODE_COLOR: Record<NodeType, string> = {
  start: '#111827',
  play: '#3B82F6',
  collect: '#F59E0B',
  condition: '#8B5CF6',
  assign_queue: '#10B981',
  hangup: '#EF4444',
}

export const COLLECT_OUTLET_COLOR: Record<string, string> = {
  success: '#22C55E',
  no_input: '#EF4444',
  no_match: '#F59E0B',
  error: '#9CA3AF',
}
