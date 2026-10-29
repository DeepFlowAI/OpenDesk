export type ExportTask = {
  id: string
  kind: string
  name: Record<string, string>
  business_type: Record<string, string>
  summary: Record<string, string>
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'expired'
  error_code: string | null
  error_field?: string | null
  row_count: number | null
  file_name: string | null
  file_size: number | null
  created_at: string
  expires_at: string | null
  scope_reduced: boolean
  can_download: boolean
  viewed: boolean
}

export type ExportTaskList = {
  items: ExportTask[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type ExportStatus = { visible: boolean; unread: number; server_time: string }
export type ExportSubmission = {
  idempotency_key: string
  kind: string
  config: Record<string, unknown>
  language: 'zh' | 'en'
  timezone: string
}
