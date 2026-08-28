export type CourseStatus = 'draft' | 'published' | 'unpublished'
export type CourseVisibility = 'all' | 'assigned'
export type MaterialType = 'video' | 'audio' | 'pdf' | 'document'
export type TranscodeStatus = 'processing' | 'ok' | 'failed'
export type LearnStatus = 'not_started' | 'in_progress' | 'completed'
export type AssignmentTargetType = 'employee' | 'group'

export interface LearningCourse {
  id: number
  name: string
  cover_url: string | null
  intro: string | null
  status: CourseStatus
  visibility: CourseVisibility
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface AdminCourseListItem {
  id: number
  name: string
  cover_url: string | null
  status: CourseStatus
  visibility: CourseVisibility
  section_count: number
  material_count: number
  learner_count: number | null
  completed_count: number
  updated_at: string | null
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type AdminCourseListResponse = Paginated<AdminCourseListItem>

export interface LearningSection {
  id: number
  course_id: number
  name: string
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

export interface LearningMaterial {
  id: number
  course_id: number
  section_id: number
  name: string
  type: MaterialType
  duration_seconds: number | null
  file_size: number | null
  transcode_status: TranscodeStatus | null
  sort_order: number
  created_at: string | null
  updated_at: string | null
}

export interface LearningSectionWithMaterials extends LearningSection {
  materials: LearningMaterial[]
}

export interface LearningCourseDetail extends LearningCourse {
  sections: LearningSectionWithMaterials[]
}

export interface MaterialUploadCredentialRequest {
  filename: string
  file_size: number
  material_type: MaterialType
}

export interface MaterialUploadCredentialResponse {
  channel: 'vod' | 'oss'
  video_id?: string | null
  upload_address?: string | null
  upload_auth?: string | null
  upload_url?: string | null
  file_key?: string | null
}

export interface LearningMaterialCreatePayload {
  name?: string
  type: MaterialType
  vod_video_id?: string
  file_key?: string
  file_size?: number
  duration_seconds?: number
}

export interface AssignmentItem {
  id: number
  target_type: AssignmentTargetType
  target_id: number
  name: string
  detail: string | number | null
}

export interface AssignableGroupItem {
  id: number
  name: string
  active_member_count: number
  added: boolean
}

export interface AssignableEmployeeItem {
  id: number
  name: string
  group_names: string[]
  assigned: boolean
  covered: boolean
}

export type AssignableEmployeeListResponse = Paginated<AssignableEmployeeItem>

export interface LearnerItem {
  employee_id: number
  name: string
  group_names: string[]
  direct_assigned: boolean
  assigned_group_names: string[]
  progress: number
  status: LearnStatus
  last_learn_at: string | null
}

export type LearnerListResponse = Paginated<LearnerItem>

export interface MyCourseListItem {
  id: number
  name: string
  cover_url: string | null
  intro: string | null
  material_count: number
  completed_count: number
  progress: number
  status: LearnStatus
  updated_at: string | null
}

export type MyCourseListResponse = Paginated<MyCourseListItem>

export interface MyMaterialItem {
  id: number
  section_id: number
  name: string
  type: MaterialType
  duration_seconds: number | null
  transcode_status: TranscodeStatus | null
  sort_order: number
  my_status: LearnStatus
  my_position_seconds: number
}

export interface MySectionItem {
  id: number
  name: string
  sort_order: number
  materials: MyMaterialItem[]
}

export interface MyCourseDetail {
  id: number
  name: string
  cover_url: string | null
  intro: string | null
  material_count: number
  completed_count: number
  status: LearnStatus
  sections: MySectionItem[]
}

export interface MaterialOpenResponse {
  material: LearningMaterial
  play_url: string | null
  file_url: string | null
  download_url: string | null
  file_name: string | null
  record_status: LearnStatus
  play_position_seconds: number
}

export interface LearningRecord {
  id: number
  material_id: number
  status: LearnStatus
  play_position_seconds: number
  completed_at: string | null
  last_learn_at: string | null
}

export interface CompleteMaterialResponse {
  record: LearningRecord
  course_completed_count: number
  course_material_count: number
  course_status: LearnStatus
}
