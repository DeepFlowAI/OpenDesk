import type { PaginatedResponse } from '@/models/common'

export type DashboardStatus = 'draft' | 'published' | 'disabled'
export type DashboardFilterType = 'date_range' | 'field_option'
export type DashboardPreviewStatus = 'idle' | 'running' | 'success' | 'failed' | 'cancelled' | 'cooldown'

export type DashboardFilter = {
  id: string
  type: DashboardFilterType
  name: string
  field_keys?: string[]
  field_key?: string
  multiple?: boolean
  default_value?: unknown
}

export type DashboardComponent = {
  id: string
  title: string
  code: string
  x: number
  y: number
  w: number
  h: number
}

export type DashboardSnapshot = {
  revision: number
  name: string
  description: string | null
  icon: string
  filters: DashboardFilter[]
  components: DashboardComponent[]
  updated_at: string | null
}

export type DashboardListItem = {
  id: number
  name: string
  slug: string
  description: string | null
  icon: string
  status: DashboardStatus
  sort_order: number
  component_count: number
  published_at: string | null
  updated_at: string | null
}

export type DashboardDetail = DashboardListItem & {
  draft: DashboardSnapshot
  published_revision: number | null
}

export type DashboardListResponse = PaginatedResponse<DashboardListItem>

export type DashboardSnapshotPayload = {
  name: string
  description: string | null
  icon: string
  filters: DashboardFilter[]
  components: DashboardComponent[]
}

export type CreateDashboardPayload = DashboardSnapshotPayload & { slug: string }

export type DashboardRunRequest = {
  request_id: string
  page_run_id: string
  component_id: string
  filter_values: Record<string, unknown>
  bypass_cache?: boolean
  component_override?: DashboardComponent
  filter_config_override?: DashboardFilter[]
}

export type DashboardRunResult = {
  request_id: string
  status: Exclude<DashboardPreviewStatus, 'idle' | 'running'>
  result: Record<string, unknown> | null
  cached: boolean
  error_code: string | null
  message: string | null
  error_line: number | null
  logs: string | null
  logs_truncated: boolean
  query_count: number
  completed_at: string
}

export type ComponentPreview = {
  status: DashboardPreviewStatus
  response?: DashboardRunResult
}

export type WorkspaceDashboardListItem = {
  id: number
  name: string
  slug: string
  description: string | null
  icon: string
  sort_order: number
  component_count: number
  published_at: string
}

export type WorkspaceDashboardListResponse = {
  items: WorkspaceDashboardListItem[]
  total: number
}

export type WorkspaceDashboardComponent = Omit<DashboardComponent, 'code'>

export type WorkspaceDashboardDetail = WorkspaceDashboardListItem & {
  revision: number
  timezone: string
  filters: DashboardFilter[]
  components: WorkspaceDashboardComponent[]
}
