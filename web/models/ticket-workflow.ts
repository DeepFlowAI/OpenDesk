import type { PaginatedResponse } from '@/models/common'
import type { TicketWorkflowGraph } from '@/models/ticket-workflow-graph'

export type TicketWorkflow = {
  id: number
  name: string
  description: string | null
  enabled: boolean
  sort_order: number
  current_version_no: number | null
  trigger_event_types: string[]
  graph_json: TicketWorkflowGraph | null
  created_at: string | null
  updated_at: string | null
}

export type TicketWorkflowListItem = {
  id: number
  name: string
  description: string | null
  enabled: boolean
  sort_order: number
  current_version_no: number | null
  trigger_event_types: string[]
  updated_at: string | null
}

export type TicketWorkflowListResponse = PaginatedResponse<TicketWorkflowListItem>

export type CreateTicketWorkflowPayload = {
  name: string
  description?: string | null
  enabled?: boolean
}

export type UpdateTicketWorkflowPayload = {
  name?: string
  description?: string | null
  enabled?: boolean
  graph_json?: TicketWorkflowGraph
}

export type GraphError = {
  node_id: string | null
  field: string | null
  code: string
  message: string
}

export type GraphValidationResult = {
  ok: boolean
  errors: GraphError[]
}

export type TicketWorkflowVersionItem = {
  id: number
  version_no: number
  comment: string | null
  is_current: boolean
  created_at: string | null
  created_by_actor_name: string | null
}

export type TicketWorkflowVersionListResponse = {
  items: TicketWorkflowVersionItem[]
  current_version_no: number | null
}

export type TicketWorkflowVersionDetail = {
  id: number
  version_no: number
  graph_json: TicketWorkflowGraph
  comment: string | null
  created_at: string | null
  created_by_actor_name: string | null
  is_current: boolean
}
