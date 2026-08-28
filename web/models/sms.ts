export type SmsTemplateType = 'notify' | 'promo'
export type SmsTemplateStatus = 'available' | 'unavailable'
export type SmsSendStatus = 'pending' | 'submitted' | 'delivered' | 'failed'

export interface SmsVariableDef {
  key: string
  label: string
  required: boolean
  max_length?: number | null
}

export interface SmsTemplateItem {
  id: number
  name: string
  sign_name: string
  type: SmsTemplateType
  variables: SmsVariableDef[]
  status: SmsTemplateStatus
  updated_at: string | null
}

export interface SmsTemplateDetail extends SmsTemplateItem {
  body: string
}

export interface SmsTemplateListResponse {
  items: SmsTemplateItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface SmsWorkspaceTemplateItem {
  id: number
  name: string
  sign_name: string
  type: SmsTemplateType
  variables: SmsVariableDef[]
  body: string
}

export interface SmsWorkspaceTemplateListResponse {
  items: SmsWorkspaceTemplateItem[]
}

export interface SmsSendPayload {
  phone: string
  template_id: number
  variables: Record<string, string>
  call_id?: string | null
  client_request_id?: string
}

export interface SmsSendResult {
  id: number
  status: SmsSendStatus
  fail_reason: string | null
  error_code: string | null
  created_at: string | null
}

export type SmsSendSource = 'single' | 'bulk'

export interface SmsSendRecordItem {
  id: number
  phone: string
  template_name: string
  template_type: SmsTemplateType
  sign_name: string
  status: SmsSendStatus
  employee_name: string
  source: SmsSendSource
  bulk_task_id: number | null
  call_record_id: number | null
  call_record_public_id: string | null
  call_id: string | null
  created_at: string | null
}

export interface SmsSendRecordListResponse {
  items: SmsSendRecordItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface SmsSendRecordDetail extends SmsSendRecordItem {
  body_snapshot: string
  variables_snapshot: Record<string, string>
  fail_reason: string | null
  provider: string
  provider_biz_id: string | null
}
