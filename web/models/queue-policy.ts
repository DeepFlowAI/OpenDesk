import type { PaginatedResponse } from '@/models/common'

export const QUEUE_CHANNELS = ['online_chat', 'call_center'] as const
export type QueueChannel = (typeof QUEUE_CHANNELS)[number]

export type QueuePolicyScopeType = 'global' | 'employee_group' | 'employee'

export type QueueAssignmentStrategy =
  | 'round_robin'
  | 'fixed_order'
  | 'random'
  | 'today_assignments_low'
  | 'today_call_duration_low'
  | 'idle_longest'
  | 'current_load_low'

export const DEFAULT_QUEUE_ASSIGNMENT_STRATEGY: QueueAssignmentStrategy = 'round_robin'

export const QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL: Record<QueueChannel, QueueAssignmentStrategy[]> = {
  online_chat: [
    'round_robin',
    'fixed_order',
    'random',
    'current_load_low',
  ],
  call_center: [
    'round_robin',
    'fixed_order',
    'random',
  ],
}

export function isQueueAssignmentStrategySupported(
  channel: QueueChannel,
  strategy: QueueAssignmentStrategy | null | undefined,
): strategy is QueueAssignmentStrategy {
  return !!strategy && QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL[channel].includes(strategy)
}

export type QueuePolicyConfig = {
  returning_agent_priority_enabled?: boolean
  returning_agent_window_hours?: number
  [key: string]: unknown
}

export type QueuePolicy = {
  id: number
  tenant_id: number
  channel: QueueChannel
  scope_type: QueuePolicyScopeType
  scope_id: number | null
  enabled: boolean
  assignment_strategy: QueueAssignmentStrategy | null
  max_waiting_count: number | null
  max_wait_seconds: number | null
  config: QueuePolicyConfig
  created_at: string | null
  updated_at: string | null
}

export type QueuePolicyListResponse = PaginatedResponse<QueuePolicy>

export type QueuePolicyUpsertPayload = {
  channel: QueueChannel
  scope_type: QueuePolicyScopeType
  scope_id?: number | null
  enabled: boolean
  assignment_strategy?: QueueAssignmentStrategy | null
  max_waiting_count?: number | null
  max_wait_seconds?: number | null
  config?: QueuePolicyConfig
}

export type QueuePolicyListParams = {
  channel?: QueueChannel
  scope_type?: QueuePolicyScopeType
  scope_id?: number
}
