import type { PaginatedResponse } from '@/models/common'
import type { SmsVariableDef } from '@/models/sms'

export type SmsBulkTaskStatus = 'draft' | 'scheduled' | 'sending' | 'paused' | 'completed' | 'archived'
export type SmsBulkTargetStatus = 'pending' | 'sending' | 'submitted' | 'delivered' | 'failed'
export type SmsBulkSendType = 'immediate' | 'scheduled'

export interface SmsBulkTemplateItem {
  id: number
  name: string
  sign_name: string
  type: string
  variables: SmsVariableDef[]
  body: string
}

export interface SmsBulkTemplateListResponse {
  items: SmsBulkTemplateItem[]
}

export interface SmsBulkTaskStats {
  total: number
  pending: number
  submitted: number
  delivered: number
  failed: number
}

export interface SmsBulkTask {
  id: number
  name: string
  description: string | null
  status: SmsBulkTaskStatus
  send_type: SmsBulkSendType
  scheduled_at: string | null
  template_id: number | null
  template_name: string
  template_type: string
  sign_name: string
  body: string
  variables: SmsVariableDef[]
  pause_reason: 'manual' | 'channel_error' | null
  published_at: string | null
  started_at: string | null
  completed_at: string | null
  created_by_id: number | null
  created_by_name: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SmsBulkTaskListItem extends SmsBulkTask {
  stats: SmsBulkTaskStats
}

export interface SmsBulkTaskDetail extends SmsBulkTask {
  stats: SmsBulkTaskStats
}

export type SmsBulkTaskListResponse = PaginatedResponse<SmsBulkTaskListItem>

export interface CreateSmsBulkTaskPayload {
  name: string
  description?: string | null
  template_id: number
  send_type?: SmsBulkSendType
  scheduled_at?: string | null
}

export interface UpdateSmsBulkTaskPayload {
  name?: string
  description?: string | null
  template_id?: number
  send_type?: SmsBulkSendType
  scheduled_at?: string | null
}

export interface SmsBulkTarget {
  id: number
  phone: string
  variable_values: Record<string, string>
  status: SmsBulkTargetStatus
  fail_reason: string | null
  submitted_at: string | null
  delivered_at: string | null
  created_at: string | null
}

export interface SmsBulkTargetDetail extends SmsBulkTarget {
  body_rendered: string
  send_record_id: number | null
  provider_biz_id: string | null
}

export type SmsBulkTargetListResponse = PaginatedResponse<SmsBulkTarget>

export interface CreateSmsBulkTargetPayload {
  phone: string
  variable_values: Record<string, string>
}

export interface SmsBulkTargetBulkDeleteResponse {
  deleted: number
  skipped: number
}

export interface SmsBulkTargetResendResponse {
  reset: number
}

export interface SmsBulkImportParseResponse {
  token: string
  headers: string[]
  sample_rows: string[][]
}

export interface SmsBulkImportMappingPayload {
  token: string
  phone_column: string
  variable_columns: Record<string, string>
}

export interface SmsBulkImportRowError {
  row_number: number
  phone: string | null
  reason: string
}

export interface SmsBulkImportValidateResponse {
  total: number
  valid: number
  duplicate: number
  invalid: number
  errors: SmsBulkImportRowError[]
}

export interface SmsBulkImportExecuteResponse {
  success: number
  duplicate: number
  failed: number
}

export const SMS_BULK_TASK_STATUS_LABELS: Record<SmsBulkTaskStatus, string> = {
  draft: '草稿',
  scheduled: '待发送',
  sending: '发送中',
  paused: '已暂停',
  completed: '已完成',
  archived: '已归档',
}

export const SMS_BULK_TARGET_STATUS_LABELS: Record<SmsBulkTargetStatus, string> = {
  pending: '待发送',
  sending: '发送中',
  submitted: '已提交',
  delivered: '送达成功',
  failed: '发送失败',
}
