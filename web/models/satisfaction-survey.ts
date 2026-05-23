import type { PaginatedResponse } from '@/models/common'

export type SatisfactionRatingMode = 'stars' | 'text' | 'emoji'
export type SatisfactionRemarkRequirement = 'hidden' | 'optional' | 'required'
export type SatisfactionTagSelectionMode = 'single' | 'multiple'
export type SatisfactionSurveyType = 'service' | 'product'
export type SatisfactionTriggerMode = 'agent_invite' | 'user_initiated' | 'session_end_invite'

export const SATISFACTION_TRIGGER_MODES: SatisfactionTriggerMode[] = [
  'agent_invite',
  'user_initiated',
  'session_end_invite',
]

export type SatisfactionRatingOption = {
  key: string
  enabled: boolean
  name: string
  is_default: boolean
  score: number
  labels: string[]
  remark_requirement: SatisfactionRemarkRequirement
}

export type SatisfactionTypeSettings = {
  enabled: boolean
  section_title: string
  popup_title: string
  rating_mode: SatisfactionRatingMode
  rating_options: SatisfactionRatingOption[]
  tag_selection_mode: SatisfactionTagSelectionMode
  remark_enabled: boolean
  remark_placeholder: string
}

export type ServiceSatisfactionSettings = SatisfactionTypeSettings & {
  show_resolution: boolean
}

export type ProductSatisfactionSettings = SatisfactionTypeSettings

export type SatisfactionTriggerSettings = {
  agent_invite: boolean
  user_initiated: boolean
  session_end_invite: boolean
  limit_one_response_per_type: boolean
}

export type SaveSatisfactionSurveyPayload = {
  name: string
  enabled: boolean
  triggers: SatisfactionTriggerSettings
  service: ServiceSatisfactionSettings
  product: ProductSatisfactionSettings
}

export type SatisfactionSurveyConfig = SaveSatisfactionSurveyPayload & {
  id: number | null
  tenant_id: number | null
  configured: boolean
  current_version: number | null
  updated_by_id: number | null
  updated_by_name: string | null
  updated_at: string | null
}

export type SatisfactionSurveyVersionListItem = {
  id: number
  version: number
  is_current: boolean
  survey_types: SatisfactionSurveyType[]
  rating_modes: Partial<Record<SatisfactionSurveyType, SatisfactionRatingMode>>
  trigger_modes: SatisfactionTriggerMode[]
  updated_by_id: number | null
  updated_by_name: string | null
  published_at: string | null
}

export type SatisfactionSurveyVersionListResponse =
  PaginatedResponse<SatisfactionSurveyVersionListItem> & {
    current_version: number | null
  }

export type SatisfactionSurveyVersionDetail = {
  id: number
  version: number
  is_current: boolean
  snapshot: SaveSatisfactionSurveyPayload
  updated_by_id: number | null
  updated_by_name: string | null
  published_at: string | null
}

export type SatisfactionSurveyResult = {
  type: SatisfactionSurveyType
  rating_mode: SatisfactionRatingMode | string
  section_title: string | null
  option_key: string
  option_name: string
  labels: string[]
  remark: string | null
  resolved: boolean | null
  submitted_at: string | null
}

export type SatisfactionSurveyRecord = {
  id: number
  conversation_id: number
  config_version: number
  config_snapshot: SaveSatisfactionSurveyPayload
  invitation_source: string
  invited_by_id: number | null
  invited_by_name: string | null
  invited_at: string | null
  status: 'invited' | 'submitted' | 'closed' | 'expired'
  survey_types: SatisfactionSurveyType[]
  service_result: SatisfactionSurveyResult | null
  product_result: SatisfactionSurveyResult | null
  submitted_at: string | null
}

export type SatisfactionSurveyEvent = {
  id: number
  conversation_id: number
  record_id: number
  event_type: 'invitation_sent' | 'feedback_submitted'
  actor_type: string
  actor_id: number | null
  actor_name: string | null
  summary: string
  config_version: number
  occurred_at: string
  metadata: Record<string, unknown>
}

export type SatisfactionSummary = {
  status: 'none' | 'invited' | 'submitted' | 'closed' | 'expired'
  labels: string[]
  invited_at: string | null
  submitted_at: string | null
  config_version: number | null
}

export type SatisfactionConversationState = {
  can_invite: boolean
  disabled_reason: string | null
  needs_confirmation: boolean
  record: SatisfactionSurveyRecord | null
  summary: SatisfactionSummary
  latest_event?: SatisfactionSurveyEvent | null
}

export type SatisfactionSubmissionTypePayload = {
  rating_option_key: string
  labels?: string[]
  remark?: string | null
  resolved?: boolean | null
}

export type SatisfactionSubmissionPayload = {
  service?: SatisfactionSubmissionTypePayload | null
  product?: SatisfactionSubmissionTypePayload | null
}

export type PublicSatisfactionInvitation = {
  invitation: SatisfactionSurveyRecord | null
  can_initiate: boolean
  disabled_reason: string | null
}

export type PublicSatisfactionSubmitResponse = {
  record: SatisfactionSurveyRecord
  latest_event: SatisfactionSurveyEvent
}

export type SessionRecordSatisfactionResponse = {
  record: SatisfactionSurveyRecord | null
  events: SatisfactionSurveyEvent[]
}

export type SatisfactionFilterOption = {
  key: string
  label: string
}

export type SatisfactionFilterOptionsResponse = {
  configured: boolean
  current_version: number | null
  survey_types: SatisfactionSurveyType[]
  show_resolution: boolean
  service_options: SatisfactionFilterOption[]
  service_labels: SatisfactionFilterOption[]
  product_options: SatisfactionFilterOption[]
  product_labels: SatisfactionFilterOption[]
}

export function getActiveTriggerModes(triggers: SatisfactionTriggerSettings): SatisfactionTriggerMode[] {
  return SATISFACTION_TRIGGER_MODES.filter((mode) => triggers[mode])
}
