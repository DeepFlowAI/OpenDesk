export type QualitySeverity = 'normal' | 'notice' | 'issue' | 'serious' | 'fatal'
export type EvidencePolicy = 'none' | 'issue_only' | 'always'
export type QualityScorecardStatus = 'draft' | 'published' | 'disabled'

export type QualityScorecardOptionInput = {
  name: string
  description: string
  points: number
  severity: QualitySeverity
}

export type QualityScorecardCriterionInput = {
  stable_key?: string
  name: string
  rubric: string
  max_points: number
  is_required: boolean
  evidence_policy: EvidencePolicy
  options: QualityScorecardOptionInput[]
}

export type QualityScorecardSectionInput = {
  name: string
  criteria: QualityScorecardCriterionInput[]
}

export type QualityScorecardPayload = {
  name: string
  description?: string | null
  pass_score?: number | null
  sections?: QualityScorecardSectionInput[]
}

export type QualityScorecardCreatePayload = Pick<QualityScorecardPayload, 'name'>

export type QualityScorecardOption = QualityScorecardOptionInput & { id: number; sort_order: number }
export type QualityScorecardCriterion = Omit<QualityScorecardCriterionInput, 'stable_key' | 'options'> & {
  id: number
  stable_key: string
  sort_order: number
  options: QualityScorecardOption[]
}
export type QualityScorecardSection = Omit<QualityScorecardSectionInput, 'criteria'> & {
  id: number
  sort_order: number
  criteria: QualityScorecardCriterion[]
}

export type QualityScorecardVersion = {
  id: number
  version_number: number
  status: QualityScorecardStatus
  pass_score: number | null
  published_at: string | null
  created_at: string
  updated_at: string
  sections: QualityScorecardSection[]
}

export type QualityScorecard = {
  id: number
  name: string
  description: string | null
  status: QualityScorecardStatus
  current_version_number: number
  created_at: string
  updated_at: string
  versions: QualityScorecardVersion[]
}

export type QualityScorecardListItem = {
  id: number
  name: string
  description: string | null
  status: QualityScorecardStatus
  current_version_number: number
  current_version_id: number
  criterion_count: number
  scored_count: number
  observation_count: number
  pass_score: number | null
  updated_at: string
}

export type QualityScorecardListResponse = {
  items: QualityScorecardListItem[]
  total: number
  page: number
  per_page: number
  pages: number
}
