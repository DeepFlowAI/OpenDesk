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

export type SessionRoutingRuleListItem = {
  id: number
  priority: number
  name: string
  enabled: boolean
  target_group_id: number
  target_group_name: string
  created_at: string | null
  updated_at: string | null
}

export type SessionRoutingRule = {
  id: number
  priority: number
  name: string
  enabled: boolean
  conditions: SessionRoutingCondition[]
  target_group_id: number
  target_group_name: string
  created_at: string | null
  updated_at: string | null
}

export type SessionRoutingRuleListResponse = PaginatedResponse<SessionRoutingRuleListItem>

export type SaveSessionRoutingRulePayload = {
  name: string
  enabled: boolean
  conditions: SessionRoutingCondition[]
  target_group_id: number
}
