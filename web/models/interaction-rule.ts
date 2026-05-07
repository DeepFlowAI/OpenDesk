// ── Condition ──

export type InteractionRuleCondition = {
  field_source: 'layout' | 'user' | 'organization'
  field_id: number | null
  field_key: string | null
  operator: string
  value: unknown
}

// ── Action ──

export type InteractionRuleAction = {
  target_field_id: number | null
  target_field_key: string | null
  state: 'hidden' | 'required' | 'optional' | 'readonly'
}

// ── Rule ──

export type FdInteractionRule = {
  id: number
  layout_id: number
  name: string | null
  condition_logic: 'and' | 'or'
  conditions: InteractionRuleCondition[]
  actions: InteractionRuleAction[]
  is_enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type CreateFdInteractionRulePayload = {
  name?: string | null
  condition_logic?: 'and' | 'or'
  conditions?: InteractionRuleCondition[]
  actions?: InteractionRuleAction[]
  is_enabled?: boolean
  sort_order?: number
}

export type UpdateFdInteractionRulePayload = {
  name?: string | null
  condition_logic?: 'and' | 'or'
  conditions?: InteractionRuleCondition[]
  actions?: InteractionRuleAction[]
  is_enabled?: boolean
  sort_order?: number
}

export type InteractionRuleSortItem = {
  id: number
  sort_order: number
}

export type InteractionRuleSortPayload = {
  items: InteractionRuleSortItem[]
}
