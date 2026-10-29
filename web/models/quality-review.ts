export type QualityReviewStatus =
  | 'ai_processing'
  | 'pending_human'
  | 'human_reviewing'
  | 'ai_completed'
  | 'human_completed'
  | 'execution_failed'

export type QualityReviewListItem = {
  id: number
  plan_id: number
  conversation_id: number
  target_agent_id: number
  agent_name?: string | null
  status: QualityReviewStatus
  result_source?: 'ai' | 'ai_pending' | 'human' | null
  score?: number | null
  outcome?: string | null
  issue_count?: number | null
  route_reasons: string[]
  assigned_reviewer_id?: number | null
  created_at: string
  completed_at?: string | null
}

export type QualityReviewListResponse = {
  items: QualityReviewListItem[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type QualityHumanItem = {
  review_item_id: number
  result_type: 'option' | 'not_applicable' | 'unanswered'
  option_id?: number | null
  judgment?: string | null
  change_reason?: string | null
  evidence_message_ids: number[]
}

export type QualityWorkbenchItem = {
  review_item_id: number
  criterion: {
    id: number
    name: string
    rubric: string
    max_points: string
    is_required: boolean
    evidence_policy: string
    options: { id: number; name: string; description: string; points: string; severity: string }[]
  }
  ai: {
    result_type?: string | null
    option_id?: number | null
    reason?: string | null
    evidence_message_ids: number[]
  }
  human: QualityHumanItem
}

export type QualityWorkbench = {
  review: QualityReviewListItem
  conversation_snapshot: Record<string, unknown>
  message_snapshot: Array<Record<string, unknown> & { id: number; content: string; is_recalled: boolean; sender_type: string; created_at: string }>
  draft_version: number
  draft_status: string
  overall_comment?: string | null
  items: QualityWorkbenchItem[]
}

export type QualityReviewDetail = QualityWorkbench & {
  unable_reason?: string | null
  audits: Array<{ action: string; actor_id?: number | null; before: Record<string, unknown>; after: Record<string, unknown>; created_at: string }>
}

export type QualityStatistics = {
  total: number
  ai_completed: number
  pending_human: number
  human_completed: number
  unable: number
  failed: number
  average_score?: number | null
  pass_rate?: number | null
}

export type QualityDraftPayload = {
  version: number
  overall_comment?: string | null
  items: QualityHumanItem[]
}
