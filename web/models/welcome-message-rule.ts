import type { PaginatedResponse } from '@/models/common'

export type WelcomeMessageConditionType = 'channel' | 'web_sdk'
export type WelcomeChannelOperator = 'eq' | 'ne'
export type WelcomeWebSdkOperator = 'eq' | 'ne' | 'any_eq' | 'any_ne'

export type WelcomeMessageCondition = {
  condition_type: WelcomeMessageConditionType
  operator: string
  value: string | string[]
}

export type WelcomeMessageRuleListItem = {
  id: number
  priority: number
  name: string
  enabled: boolean
  conditions: WelcomeMessageCondition[]
  created_at: string | null
  updated_at: string | null
}

export type WelcomeMessageRule = WelcomeMessageRuleListItem & {
  content: string
}

export type WelcomeMessagePublic = {
  id: number
  name: string
  content: string
}

export type WelcomeMessageRuleListResponse = PaginatedResponse<WelcomeMessageRuleListItem>

export type SaveWelcomeMessageRulePayload = {
  name: string
  enabled: boolean
  conditions: WelcomeMessageCondition[]
  content: string
}
