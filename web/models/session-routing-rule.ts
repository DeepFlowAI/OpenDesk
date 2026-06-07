import type { PaginatedResponse } from '@/models/common'

export type SessionConditionType = 'channel' | 'web_sdk' | 'current_time'

export type ChannelOperator = 'eq' | 'ne'
export type WebSdkOperator = 'eq' | 'ne' | 'any_eq' | 'any_ne'
export type TimeOperator = 'in_schedule' | 'not_in_schedule'

export type SessionRoutingCondition = {
  condition_type: SessionConditionType
  operator: string
  value: string | string[]
}

export type SessionRoutingTargetStrategy =
  | 'sequential_overflow'
  | 'least_waiting_count'
  | 'shortest_tail_wait'

export type SessionRoutingQueueSourceType = 'user_field' | 'employee' | 'employee_group'

export type SessionRoutingQueueSource = {
  source_type: SessionRoutingQueueSourceType
  target_ids: number[]
}

export type SessionRoutingRuleListItem = {
  id: number
  priority: number
  name: string
  enabled: boolean
  target_group_id: number | null
  target_group_name: string
  target_strategy: SessionRoutingTargetStrategy
  target_queue_sources: SessionRoutingQueueSource[]
  target_summary: string
  created_at: string | null
  updated_at: string | null
}

export type SessionRoutingRule = {
  id: number
  priority: number
  name: string
  enabled: boolean
  conditions: SessionRoutingCondition[]
  target_group_id: number | null
  target_group_name: string
  target_strategy: SessionRoutingTargetStrategy
  target_queue_sources: SessionRoutingQueueSource[]
  target_summary: string
  created_at: string | null
  updated_at: string | null
}

export type SessionRoutingRuleListResponse = PaginatedResponse<SessionRoutingRuleListItem>

export type SaveSessionRoutingRulePayload = {
  name: string
  enabled: boolean
  conditions: SessionRoutingCondition[]
  target_group_id?: number | null
  target_strategy: SessionRoutingTargetStrategy
  target_queue_sources: SessionRoutingQueueSource[]
}
