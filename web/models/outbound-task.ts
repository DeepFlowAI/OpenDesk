import type { PaginatedResponse } from '@/models/common'
import type { FieldType } from '@/types/field-enums'

export type OutboundTaskStatus = 'draft' | 'active' | 'paused' | 'completed' | 'archived'
export type OutboundTargetStatus = 'pending' | 'calling' | 'redial' | 'completed' | 'do_not_call' | 'invalid_number'
export type OutboundScriptNodeType = 'start' | 'script' | 'branch' | 'end'

export type OutboundScriptBranch = {
  id: string
  label: string
  next_node_id: string
}

export type OutboundScriptNode = {
  id: string
  type: OutboundScriptNodeType
  title: string
  content?: string | null
  agent_tip?: string | null
  next_node_id?: string | null
  branches: OutboundScriptBranch[]
  position: { x: number; y: number }
}

export type OutboundScript = {
  version: 1
  nodes: OutboundScriptNode[]
}

export type OutboundTaskField = {
  key: string
  name: string
  field_type: FieldType
  required: boolean
  agent_editable: boolean
  show_in_list: boolean
  enabled: boolean
  type_config: Record<string, unknown>
  sort_order: number
}

export type OutboundTaskTemplate = {
  id: number
  tenant_id: number
  name: string
  description: string | null
  fields: OutboundTaskField[]
  script?: OutboundScript | null
  has_script?: boolean
  created_by_id: number | null
  updated_by_id: number | null
  created_at: string | null
  updated_at: string | null
}

export type OutboundTaskStats = {
  total_targets: number
  pending_targets: number
  completed_targets: number
  call_count: number
  answered_count: number
}

export type OutboundTask = {
  id: number
  tenant_id: number
  template_id: number | null
  template_name: string
  name: string
  description: string | null
  status: OutboundTaskStatus
  owner_id: number | null
  starts_at: string | null
  due_at: string | null
  allow_self_claim: boolean
  default_redial_interval_minutes: number | null
  assignment_mode: string
  assignee_scope_ids: number[]
  fields: OutboundTaskField[]
  script_snapshot?: OutboundScript | null
  has_script?: boolean
  created_by_id: number | null
  updated_by_id: number | null
  created_at: string | null
  updated_at: string | null
  stats: OutboundTaskStats
}

export type OutboundTargetTaskContext = {
  id: number
  name: string
  fields: OutboundTaskField[]
  has_script: boolean
}

export type OutboundTarget = {
  id: number
  tenant_id: number
  task_id: number
  phone_number: string
  user_id: number | null
  user_name: string | null
  assignee_id: number | null
  status: OutboundTargetStatus
  field_values: Record<string, unknown>
  call_count: number
  answered_count: number
  last_called_at: string | null
  last_call_result: string | null
  next_follow_up_at: string | null
  total_talk_duration_ms: number
  created_at: string | null
  updated_at: string | null
  task?: OutboundTargetTaskContext | null
}

export type OutboundRecord = {
  id: number
  tenant_id: number
  task_id: number
  target_id: number
  call_record_id: number | null
  agent_id: number | null
  phone_number: string
  started_at: string
  duration_ms: number | null
  answered: boolean
  result: string | null
  notes: string | null
  field_values: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
}

export type CreateOutboundTemplatePayload = {
  name: string
  description?: string | null
  fields?: OutboundTaskField[]
  script?: OutboundScript | null
}

export type UpdateOutboundTemplatePayload = CreateOutboundTemplatePayload & {
  expected_updated_at?: string | null
}

export type CreateOutboundTaskPayload = {
  template_id: number
  name: string
  description?: string | null
  owner_id?: number | null
  starts_at?: string | null
  due_at?: string | null
  allow_self_claim?: boolean
  default_redial_interval_minutes?: number | null
  assignment_mode?: string
  assignee_scope_ids?: number[]
  fields?: OutboundTaskField[]
  publish?: boolean
}

export type UpdateOutboundTaskPayload = Partial<Omit<CreateOutboundTaskPayload, 'template_id' | 'publish'>>

export type CreateOutboundTargetPayload = {
  phone_number: string
  user_id?: number | null
  assignee_id?: number | null
  field_values?: Record<string, unknown>
}

export type UpdateOutboundTargetPayload = Partial<CreateOutboundTargetPayload> & {
  status?: OutboundTargetStatus
  next_follow_up_at?: string | null
}

export type UpdateMyOutboundTargetPayload = {
  status?: Exclude<OutboundTargetStatus, 'calling'>
  field_values?: Record<string, unknown>
}

export type CreateOutboundRecordPayload = {
  call_record_id?: number | null
  started_at?: string | null
  duration_ms?: number | null
  answered?: boolean
  result?: string | null
  notes?: string | null
  target_status: OutboundTargetStatus
  next_follow_up_at?: string | null
  field_values?: Record<string, unknown>
}

export type BulkAssignPayload = {
  target_ids: number[]
  assignee_id: number | null
  overwrite?: boolean
}

export type BulkAssignResponse = {
  updated: number
}

export type BulkDeletePayload = {
  target_ids: number[]
}

export type BulkDeleteResponse = {
  deleted: number
}

export type OutboundTargetImportError = {
  row_number: number
  phone_number: string | null
  reason: string
}

export type OutboundTargetImportResponse = {
  total: number
  created: number
  failed: number
  errors: OutboundTargetImportError[]
}

export type OutboundTemplateListResponse = PaginatedResponse<OutboundTaskTemplate>
export type OutboundTaskListResponse = PaginatedResponse<OutboundTask>
export type OutboundTargetListResponse = PaginatedResponse<OutboundTarget>
export type OutboundRecordListResponse = PaginatedResponse<OutboundRecord>

export type MyOutboundTaskItem = {
  id: number
  name: string
  status: OutboundTaskStatus
  due_at: string | null
  my_total: number
  my_completed: number
}

export type MyOutboundTaskListResponse = {
  items: MyOutboundTaskItem[]
}

export type MyOutboundTargetRecordItem = {
  id: number
  source: 'manual' | 'personal_auto'
  started_at: string
  answered: boolean
  result: string | null
  duration_ms: number | null
  agent_id: number | null
  agent_name: string | null
  call_record_id: number | null
  call_record_public_id: string | null
  can_view_detail: boolean
}

export type MyOutboundTargetRecordsResponse = {
  items: MyOutboundTargetRecordItem[]
}

export const OUTBOUND_TASK_STATUS_LABELS: Record<OutboundTaskStatus, string> = {
  draft: '草稿',
  active: '进行中',
  paused: '暂停',
  completed: '已完成',
  archived: '已归档',
}

export const OUTBOUND_TARGET_STATUS_LABELS: Record<OutboundTargetStatus, string> = {
  pending: '待呼叫',
  calling: '呼叫中',
  redial: '需重拨',
  completed: '已完成',
  do_not_call: '勿扰',
  invalid_number: '无效号码',
}
