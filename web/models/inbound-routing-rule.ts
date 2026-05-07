import type { PaginatedResponse } from '@/models/common'

export type RoutingConditionType = 'caller_number' | 'callee_number' | 'call_time'

export type NumberOperator = 'eq' | 'ne'
export type TimeOperator = 'in_schedule' | 'not_in_schedule'

export type RoutingCondition = {
  condition_type: RoutingConditionType
  operator: string
  value: string
}

export type InboundRoutingRuleListItem = {
  id: number
  priority: number
  name: string
  enabled: boolean
  target_voice_flow_id: number
  target_flow_name: string
  created_at: string | null
  updated_at: string | null
}

export type InboundRoutingRule = {
  id: number
  priority: number
  name: string
  enabled: boolean
  conditions: RoutingCondition[]
  target_voice_flow_id: number
  target_flow_name: string
  created_at: string | null
  updated_at: string | null
}

export type InboundRoutingRuleListResponse = PaginatedResponse<InboundRoutingRuleListItem>

export type SaveInboundRoutingRulePayload = {
  name: string
  enabled: boolean
  conditions: RoutingCondition[]
  target_voice_flow_id: number
}
