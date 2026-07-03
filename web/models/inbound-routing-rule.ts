import type { PaginatedResponse } from '@/models/common'
import type { AssignQueueTarget } from '@/models/voice-flow-graph'

export type RoutingConditionType = 'caller_number' | 'callee_number' | 'call_time'

export type NumberOperator = 'eq' | 'ne'
export type TimeOperator = 'in_schedule' | 'not_in_schedule'

/** A routing rule either targets a voice flow or a VoiceSpeed agent directly. */
export type RoutingTargetType = 'voice_flow' | 'voicespeed_agent'

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
  target_type: RoutingTargetType
  target_voice_flow_id: number | null
  target_flow_name: string
  voicespeed_agent_id: string | null
  voicespeed_agent_name: string | null
  created_at: string | null
  updated_at: string | null
}

export type InboundRoutingRule = {
  id: number
  priority: number
  name: string
  enabled: boolean
  conditions: RoutingCondition[]
  target_type: RoutingTargetType
  target_voice_flow_id: number | null
  target_flow_name: string
  voicespeed_agent_id: string | null
  voicespeed_agent_name: string | null
  transfer_target: AssignQueueTarget | null
  created_at: string | null
  updated_at: string | null
}

export type InboundRoutingRuleListResponse = PaginatedResponse<InboundRoutingRuleListItem>

export type SaveInboundRoutingRulePayload = {
  name: string
  enabled: boolean
  conditions: RoutingCondition[]
  target_type: RoutingTargetType
  target_voice_flow_id?: number | null
  voicespeed_agent_id?: string | null
  voicespeed_agent_name?: string | null
  transfer_target?: AssignQueueTarget | null
}
