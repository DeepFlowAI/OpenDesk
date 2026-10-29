export type CallEventType =
  | 'call.created'
  | 'call.customer.connected'
  | 'call.ended'
  | 'call.queue.entered'
  | 'call.agent.connected'
  | 'call.agent.disconnected'
  | 'call.transfer.completed'
  | 'call.recording.completed'
  | 'call.recording.failed'
  | 'call.satisfaction.completed'

export type CallEventDirection = 'inbound' | 'outbound'

export type CallEventSource =
  | 'inbound'
  | 'agent_dial'
  | 'embedded_call'
  | 'personal_auto_outbound'
  | 'manual_outbound_task'
  | 'auto_outbound'

export type CallEventRuleSubscription = {
  public_id: string
  name: string
  is_active: boolean
}

export type CallEventRule = {
  public_id: string
  name: string
  subscription: CallEventRuleSubscription
  event_types: CallEventType[]
  directions: CallEventDirection[]
  call_sources: CallEventSource[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export type CallEventRuleList = {
  items: CallEventRule[]
  total: number
  page: number
  per_page: number
  pages: number
  tenant_rule_count: number
  max_rules: number
}

export type CallEventRuleListParams = {
  page: number
  per_page: number
  q?: string
  status?: 'active' | 'inactive'
}

export type CallEventRulePayload = {
  name: string
  subscription_public_id: string
  event_types: CallEventType[]
  directions: CallEventDirection[]
  call_sources: CallEventSource[]
}

export type CallEventRuleOption = {
  public_id: string
  name: string
  is_active: boolean
  used_by_rule_name: string | null
}

export type CallEventRuleOptions = {
  options: CallEventRuleOption[]
  can_manage_global: boolean
}
