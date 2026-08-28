import type { PaginatedResponse } from '@/models/common'

export type SatisfactionPrompt =
  | { kind: 'auto_tts'; text: string }
  | { kind: 'tts'; text: string }
  | { kind: 'audio'; asset_id: number }

export type SatisfactionOption = { id: string; dtmf: string; label: string }

export type SatisfactionQuestionData = {
  name: string
  required: boolean
  prompt: SatisfactionPrompt
  barge_in_disabled: boolean
  options: SatisfactionOption[]
  timeout_seconds: number
  retry: {
    enabled: boolean
    no_input: number
    no_match: number
    no_input_prompt: SatisfactionPrompt | null
    no_match_prompt: SatisfactionPrompt | null
  }
}

export type SatisfactionCondition = {
  question_node_id: string
  operator: 'eq' | 'neq' | 'is_answered'
  option_id: string | null
}

export type SatisfactionNode = {
  id: string
  type: 'start' | 'play' | 'question' | 'condition' | 'end'
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export type SatisfactionEdge = {
  id: string
  source: string
  target: string
  source_handle: string
}

export type SatisfactionFlowGraph = {
  version: number
  nodes: SatisfactionNode[]
  edges: SatisfactionEdge[]
}

export type SatisfactionFlowSettings = {
  auto_transfer: boolean
  agent_invite: boolean
  inbound: boolean
  outbound: boolean
}

export type SatisfactionFlowDraft = {
  name: string
  description: string | null
  graph_json: SatisfactionFlowGraph
  settings: SatisfactionFlowSettings
  comment?: string | null
}

export type SatisfactionFlow = SatisfactionFlowDraft & {
  id: number
  enabled: boolean
  current_version_no: number | null
  created_at: string | null
  updated_at: string | null
}

export type SatisfactionFlowListItem = {
  id: number
  name: string
  description: string | null
  enabled: boolean
  triggers: Array<'auto_transfer' | 'agent_invite'>
  directions: Array<'inbound' | 'outbound'>
  question_count: number
  current_version_no: number | null
  created_at: string | null
  updated_at: string | null
}

export type SatisfactionFlowListResponse = PaginatedResponse<SatisfactionFlowListItem>

export type SatisfactionFlowVersion = {
  id: number
  version_no: number
  name_snapshot: string
  comment: string | null
  is_current: boolean
  question_count: number
  created_at: string | null
  created_by_actor_name: string | null
}

export type SatisfactionFlowVersionListResponse = {
  items: SatisfactionFlowVersion[]
  current_version_no: number | null
}

export type SatisfactionFlowVersionDetail = SatisfactionFlowVersion & {
  description_snapshot: string | null
  graph_json: SatisfactionFlowGraph
  settings: SatisfactionFlowSettings
}

export type SatisfactionGraphError = {
  node_id: string | null
  field: string | null
  code: string
  message: string
}

export type SatisfactionGraphValidation = {
  ok: boolean
  errors: SatisfactionGraphError[]
}

export function newOption(label: string, dtmf: string): SatisfactionOption {
  return { id: `option_${crypto.randomUUID()}`, label, dtmf }
}

export function defaultSatisfactionDraft(): SatisfactionFlowDraft {
  return {
    name: '未命名满意度流程',
    description: null,
    settings: { auto_transfer: false, agent_invite: true, inbound: true, outbound: false },
    graph_json: {
      version: 1,
      nodes: [
        { id: 'start', type: 'start', position: { x: 80, y: 240 }, data: {} },
        {
          id: 'question-1',
          type: 'question',
          position: { x: 360, y: 240 },
          data: {
            name: '服务满意度',
            required: true,
            prompt: { kind: 'auto_tts', text: '请评价本次服务。满意请按 3，一般请按 2，不满意请按 1。' },
            barge_in_disabled: false,
            options: [
              { id: 'satisfied', dtmf: '3', label: '满意' },
              { id: 'neutral', dtmf: '2', label: '一般' },
              { id: 'dissatisfied', dtmf: '1', label: '不满意' },
            ],
            timeout_seconds: 8,
            retry: {
              enabled: true,
              no_input: 1,
              no_match: 1,
              no_input_prompt: { kind: 'tts', text: '未收到您的输入，请重新选择。' },
              no_match_prompt: { kind: 'tts', text: '输入无效，请按提示重新选择。' },
            },
          },
        },
        {
          id: 'end',
          type: 'end',
          position: { x: 700, y: 240 },
          data: {
            pre_play: { kind: 'tts', text: '感谢您的评价，祝您生活愉快。' },
            completion_type: 'completed',
          },
        },
      ],
      edges: [
        { id: 'edge-start', source: 'start', target: 'question-1', source_handle: 'next' },
        { id: 'edge-answered', source: 'question-1', target: 'end', source_handle: 'answered' },
        { id: 'edge-no-input', source: 'question-1', target: 'end', source_handle: 'no_input' },
        { id: 'edge-no-match', source: 'question-1', target: 'end', source_handle: 'no_match' },
        { id: 'edge-error', source: 'question-1', target: 'end', source_handle: 'error' },
      ],
    },
  }
}
