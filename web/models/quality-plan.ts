export type QualityPlanStatus = 'draft' | 'running' | 'paused' | 'completed' | 'partial_failed' | 'failed'
export type QualityPlanPayload = {
  name: string; description?: string | null; run_mode: 'continuous' | 'one_time'; deadline_at?: string | null
  range_start_at?: string | null; range_end_at?: string | null; group_ids: number[]; agent_ids: number[]
  coverage_mode: 'all' | 'percentage'; sample_rate: number; scorecard_version_id: number
  execution_strategy: 'ai' | 'human'; manual_route_severity?: 'notice' | 'issue' | 'serious' | 'fatal' | null
  normal_review_rate: number; reviewer_ids: number[]
}
export type QualityPlan = QualityPlanPayload & {
  id: number; tenant_id: number; status: QualityPlanStatus; estimate_result: Record<string, number>
  estimated_at: string | null; activated_at: string | null; created_at: string; updated_at: string
}
export type QualityPlanListResponse = { items: QualityPlan[]; total: number; page: number; per_page: number; pages: number }
export type QualityPlanEstimate = { candidate_count: number; target_agent_count: number; estimated_review_count: number; reference_days?: number; estimated_daily_count?: number }
