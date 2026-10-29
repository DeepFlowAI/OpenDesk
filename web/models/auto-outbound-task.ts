import type { OutboundTaskField } from '@/models/outbound-task'

export type AutoOutboundTaskStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived'
export type AutoOutboundExecutionMode = 'ivr' | 'bot' | 'agent'
export type AutoOutboundPacingMode = 'progressive' | 'ratio' | 'predictive'
export type AutoOutboundTargetStatus = 'pending' | 'calling' | 'redial_pending' | 'completed' | 'invalid'
export type AutoOutboundTerminalState =
  | 'answered'
  | 'no_answer'
  | 'busy'
  | 'power_off'
  | 'invalid_number'
  | 'failed'
export type AutoOutboundReceptionType = 'ivr' | 'bot' | 'agent' | 'none'
export type AutoOutboundAbandonPrompt = 'play_wait' | 'hangup'

export type DailyTimeWindow = {
  start: string
  end: string
}

export type RetryPolicyItem = {
  max_retries: number
  interval_minutes: number
}

export type AutoOutboundRetryPolicy = {
  no_answer: RetryPolicyItem
  busy: RetryPolicyItem
  power_off: RetryPolicyItem
}

export type AutoOutboundTaskStatsOverview = {
  total_targets: number
  finished_targets: number
  call_count: number
  answered_count: number
  answer_rate: number | string | null
  transfer_count: number | null
  abandon_count: number | null
  abandon_rate: number | string | null
  current_concurrency: number | null
}

export type AutoOutboundTaskListItem = {
  id: number
  name: string
  execution_mode: AutoOutboundExecutionMode
  reception_target_name: string | null
  status: AutoOutboundTaskStatus
  out_of_window: boolean
  auto_pause_reason: string | null
  owner_name: string | null
  total_targets: number
  finished_targets: number
  call_count: number
  answered_count: number
  answer_rate: number | null
  updated_at: string | null
}

export type AutoOutboundTask = {
  id: number
  name: string
  template_id: number | null
  template_name: string
  description: string | null
  owner_id: number | null
  owner_name: string | null
  status: AutoOutboundTaskStatus
  out_of_window: boolean
  auto_pause_reason: string | null
  execution_mode: AutoOutboundExecutionMode
  voice_flow_id: number | null
  transfer_queue_id: number | null
  voicespeed_agent_id: string | null
  intent_result_field_key: string | null
  queue_id: number | null
  pacing_mode: AutoOutboundPacingMode | null
  dial_ratio: number | null
  dial_intensity: number | string | null
  abandon_rate_limit: number | string | null
  abandon_prompt: AutoOutboundAbandonPrompt | null
  wrapup_seconds: number
  start_date: string
  end_date: string
  daily_time_windows: DailyTimeWindow[]
  caller_number_id: string
  max_concurrency: number
  retry_policy: AutoOutboundRetryPolicy
  daily_per_number_limit: number
  auto_resume_on_target_append: boolean
  reception_target_name: string | null
  fields: OutboundTaskField[]
  created_by_id: number | null
  updated_at: string | null
  created_at: string | null
  stats: AutoOutboundTaskStatsOverview
}

export type CreateAutoOutboundTaskPayload = {
  name: string
  template_id: number
  description?: string | null
  owner_id?: number | null
  execution_mode: AutoOutboundExecutionMode
  voice_flow_id?: number | null
  transfer_queue_id?: number | null
  voicespeed_agent_id?: string | null
  intent_result_field_key?: string | null
  queue_id?: number | null
  pacing_mode?: AutoOutboundPacingMode | null
  dial_ratio?: number | null
  dial_intensity?: number | string | null
  abandon_rate_limit?: number | string | null
  abandon_prompt?: AutoOutboundAbandonPrompt | null
  wrapup_seconds: number
  start_date: string
  end_date: string
  daily_time_windows: DailyTimeWindow[]
  caller_number_id: string
  max_concurrency: number
  retry_policy: AutoOutboundRetryPolicy
  daily_per_number_limit: number
  auto_resume_on_target_append: boolean
}

export type UpdateAutoOutboundTaskPayload = Partial<
  Omit<CreateAutoOutboundTaskPayload, 'template_id'>
> & {
  template_id?: number | null
}

export type AutoOutboundTaskListResponse = {
  items: AutoOutboundTaskListItem[]
  total: number
  page: number
  page_size: number
}

export type AutoOutboundTarget = {
  id: number
  phone_number: string
  user_id: number | null
  user_name: string | null
  status: AutoOutboundTargetStatus
  field_values: Record<string, unknown>
  call_count: number
  answered_count: number
  remaining_retries: number
  can_delete: boolean
  last_called_at: string | null
  last_call_result: string | null
  next_call_at: string | null
  task_auto_resumed: boolean
}

export type AutoOutboundTargetListResponse = {
  items: AutoOutboundTarget[]
  total: number
  page: number
  page_size: number
}

export type CreateAutoOutboundTargetPayload = {
  phone_number: string
  user_id?: number | null
  field_values?: Record<string, unknown>
}

export type AutoOutboundTargetImportError = {
  row_number: number
  phone_number: string | null
  reason: string
}

export type AutoOutboundTargetImportResponse = {
  total: number
  created: number
  failed: number
  skipped_rate_limited: number
  errors: AutoOutboundTargetImportError[]
  task_auto_resumed: boolean
}

export type AutoOutboundCallVariable = {
  name: string
  value: string
  truncated: boolean
}

/** Variables preset to the voice bot for one call; null when none were sent. */
export type AutoOutboundCallVariables = {
  status: 'passed' | 'failed'
  items: AutoOutboundCallVariable[]
}

export type AutoOutboundRecord = {
  id: number
  phone_number: string
  target_id: number
  started_at: string
  terminal_state: AutoOutboundTerminalState | null
  reception_type: AutoOutboundReceptionType | null
  agent_name: string | null
  duration_ms: number | null
  reception_result: Record<string, unknown> | string | null
  call_variables?: AutoOutboundCallVariables | null
  call_record_id: number | null
  call_record_public_id: string | null
}

export type AutoOutboundWrapupPayload = {
  reception_result?: Record<string, unknown>
  field_values?: Record<string, unknown> | null
}

/** Agent workspace context (call.workspace.use); no manage permission required. */
export type AutoOutboundAgentContextRecord = {
  id: number
  target_id: number
  field_values: Record<string, unknown>
  reception_result: Record<string, unknown> | null
}

export type AutoOutboundAgentContext = {
  task_id: number
  task_name: string
  template_name: string
  fields: OutboundTaskField[]
  wrapup_seconds: number
  record: AutoOutboundAgentContextRecord | null
  opening_script_text?: string | null
  last_utterance?: string | null
  target_name?: string | null
  target_phone?: string | null
  assignment_type?: string | null
}

export type AutoOutboundRecordListResponse = {
  items: AutoOutboundRecord[]
  total: number
  page: number
  page_size: number
}

export type AutoOutboundDailyStat = {
  date: string
  call_count: number
  answered_count: number
  answer_rate: number | null
}

export type AutoOutboundTerminalDistributionItem = {
  terminal_state: AutoOutboundTerminalState
  count: number
}

export type AutoOutboundResultDistribution =
  | { exits: Record<string, number>; collected: Record<string, Record<string, number>> }
  | { intents: Record<string, number>; handoff_count: number; handoff_rate: number | null }
  | { agents: Array<{ agent_id: number; answered: number; avg_duration_ms: number }> }

export type AutoOutboundAbandonStats = {
  answered: number
  abandoned: number
  abandon_rate: number | string | null
  abandon_rate_limit: number | string | null
}

export type AutoOutboundTaskStatsResponse = {
  daily_trend: AutoOutboundDailyStat[]
  terminal_state_distribution: AutoOutboundTerminalDistributionItem[]
  result_distribution?: AutoOutboundResultDistribution
  abandon_stats?: AutoOutboundAbandonStats
  abandon_over_limit?: boolean
}

export type DialCapacitySourceBreakdown = {
  task: number | null
  tenant: number | null
  flowkit: number | null
  trunk: number | null
  batch: number | null
  reception: number | null
}

export type DialCapacityResponse = {
  dialable: number
  sources: DialCapacitySourceBreakdown
}

export type AutoOutboundMonitorResponse = {
  in_progress_calls: number
  ready_agents: number | null
  in_call_agents: number | null
  queued_count: number | null
  abandon_rate: number | string | null
  abandon_over_limit?: boolean
  no_ready_agents?: boolean
  dial_capacity?: DialCapacityResponse | null
}

export type AutoOutboundEventSubscriptionOption = {
  public_id: string
  name: string
  is_active: boolean
}

export type AutoOutboundEventSubscriptionBinding = {
  subscription_public_id: string
  subscription_name: string
  subscription_is_active: boolean
  event_types: string[]
}

export type AutoOutboundEventSubscription = {
  task_id: number
  task_name: string
  enabled: boolean
  binding: AutoOutboundEventSubscriptionBinding | null
  options: AutoOutboundEventSubscriptionOption[]
  can_manage_global: boolean
}

export type SaveAutoOutboundEventSubscriptionPayload = {
  enabled: boolean
  subscription_public_id: string | null
  event_types: string[]
}

export const DEFAULT_DAILY_TIME_WINDOWS: DailyTimeWindow[] = [
  { start: '09:00', end: '12:00' },
  { start: '14:00', end: '20:00' },
]

export const DEFAULT_RETRY_POLICY: AutoOutboundRetryPolicy = {
  no_answer: { max_retries: 2, interval_minutes: 120 },
  busy: { max_retries: 2, interval_minutes: 120 },
  power_off: { max_retries: 2, interval_minutes: 120 },
}
