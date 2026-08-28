import type { Paginated } from './learning'

export type ExamStatus = 'draft' | 'published' | 'unpublished'
export type QuestionType = 'single' | 'multiple' | 'judge'
export type ExamResultStatus = 'not_started' | 'passed' | 'failed'
export type AttemptStatus = 'in_progress' | 'submitted' | 'abandoned'

export interface LearningExam {
  id: number
  name: string
  intro: string | null
  status: ExamStatus
  visibility: 'all' | 'assigned'
  pass_percent: number
  time_limit_minutes: number | null
  max_attempts: number
  shuffle_questions: boolean
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface AdminExamListItem {
  id: number
  name: string
  status: ExamStatus
  visibility: 'all' | 'assigned'
  question_count: number
  total_score: number
  pass_score: number
  learner_count: number | null
  passed_count: number
  updated_at: string | null
}

export type AdminExamListResponse = Paginated<AdminExamListItem>

export interface ExamQuestionOption {
  key: string
  text: string | null
  is_correct: boolean
}

export interface LearningExamQuestion {
  id: number
  exam_id: number
  type: QuestionType
  stem: string
  score: number
  options: ExamQuestionOption[]
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

export interface LearningExamDetail extends LearningExam {
  questions: LearningExamQuestion[]
}

export interface ExamQuestionPayload {
  type: QuestionType
  stem: string
  score: number
  options: ExamQuestionOption[]
}

export interface ExamResultItem {
  employee_id: number
  name: string
  group_names: string[]
  direct_assigned: boolean
  assigned_group_names: string[]
  best_score: number | null
  status: ExamResultStatus
  submitted_count: number
  last_submitted_at: string | null
}

export type ExamResultListResponse = Paginated<ExamResultItem>

// ---------------------------------------------------------------------------
// Employee side
// ---------------------------------------------------------------------------

export interface MyExamItem {
  id: number
  name: string
  intro: string | null
  question_count: number
  total_score: number
  pass_score: number
  pass_percent: number
  time_limit_minutes: number | null
  max_attempts: number
  best_score: number | null
  status: ExamResultStatus
  remaining_attempts: number
  updated_at: string | null
}

export type MyExamListResponse = Paginated<MyExamItem>

export interface MyExamAttemptHistoryItem {
  id: number
  attempt_index: number
  score: number
  passed: boolean
  submitted_at: string | null
}

export interface MyExamSummary {
  id: number
  name: string
  intro: string | null
  question_count: number
  total_score: number
  pass_score: number
  pass_percent: number
  time_limit_minutes: number | null
  max_attempts: number
  shuffle_questions: boolean
  best_score: number | null
  status: ExamResultStatus
  remaining_attempts: number
  best_attempt_id: number | null
  attempts: MyExamAttemptHistoryItem[]
}

export interface AttemptQuestionOption {
  key: string
  text: string | null
  is_correct?: boolean | null
}

export interface AttemptQuestion {
  question_id: number
  type: QuestionType
  stem: string
  score: number
  options: AttemptQuestionOption[]
  selected_keys?: string[] | null
  correct_keys?: string[] | null
  gained_score?: number | null
  is_correct?: boolean | null
}

export interface AttemptStartResponse {
  attempt_id: number
  exam_id: number
  started_at: string
  time_limit_minutes: number | null
  questions: AttemptQuestion[]
}

export interface AttemptDetailResponse {
  attempt_id: number
  exam_id: number
  status: AttemptStatus
  attempt_index: number | null
  score: number | null
  passed: boolean | null
  started_at: string
  submitted_at: string | null
  time_limit_minutes: number | null
  questions: AttemptQuestion[]
}

export interface AttemptSubmitResponse {
  attempt_id: number
  exam_id: number
  attempt_index: number
  score: number
  total_score: number
  pass_score: number
  passed: boolean
  submitted_at: string
}
