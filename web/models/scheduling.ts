export type ShiftType = 'work' | 'leave'

export type Shift = {
  id: number
  name: string
  /** Missing only while old API containers drain during a blue/green deploy. */
  shift_type?: ShiftType
  /** "HH:MM" */
  start_time: string
  /** "HH:MM"; <= start_time means an overnight shift */
  end_time: string
  /** hex color, e.g. "#4B9CF5" */
  color: string
  sort_order: number
  is_enabled: boolean
  /** True when the shift is referenced by any schedule assignment (blocks delete). */
  has_assignments: boolean
  /** True when assignments, published snapshots, or rules reference this shift. */
  has_references?: boolean
  created_at: string | null
  updated_at: string | null
}

export type ShiftListResponse = {
  items: Shift[]
}

export type ShiftCreatePayload = {
  name: string
  shift_type?: ShiftType
  start_time?: string
  end_time?: string
  color: string
  sort_order: number
  is_enabled?: boolean
}

export type ShiftUpdatePayload = Partial<ShiftCreatePayload>

export type MessageResponse = {
  message: string
}

export type PoolMember = {
  id: number
  name: string
  job_number: string | null
}

export type PoolMemberListResponse = {
  items: PoolMember[]
}

export type AssignmentShift = {
  id: number
  name: string
  shift_type?: ShiftType
  color: string
  start_time: string
  end_time: string
  is_enabled: boolean
}

export type AssignmentEmployee = {
  id: number
  name: string
  job_number: string | null
}

export type Assignment = {
  id: number
  /** YYYY-MM-DD */
  date: string
  shift: AssignmentShift
  employee: AssignmentEmployee
  created_at: string | null
}

export type AssignmentListResponse = {
  items: Assignment[]
}

export type AssignmentWriteItem = {
  employee_id: number
  shift_id: number
  /** YYYY-MM-DD */
  date: string
}

export type AssignmentBulkCreatePayload = {
  group_ids: number[]
  items: AssignmentWriteItem[]
  /** Skip the soft-constraint confirm (user already confirmed). */
  allow_soft?: boolean
  /** User confirmed replacing work with leave (or vice versa). */
  replace_conflicts?: boolean
}

export type AssignmentBulkCreateResponse = {
  created: number
  skipped: number
  replaced: number
}

export type AssignmentBulkDeleteResponse = {
  deleted: number
}

export type CopyWeekPayload = {
  /** Monday of the target week, YYYY-MM-DD */
  week_start: string
  mode: 'skip' | 'overwrite'
  group_ids: number[]
  /** Skip the soft-constraint confirm (user already confirmed). */
  allow_soft?: boolean
}

export type CopyWeekResponse = {
  copied: number
  skipped_cells: number
  skipped_leave_conflicts: number
}

/** Publish lifecycle of one calendar week's schedule. */
export type PublishState = 'unpublished' | 'published' | 'dirty'

export type PublishStatus = {
  /** Monday of the week, YYYY-MM-DD */
  week_start: string
  state: PublishState
  published_at: string | null
  published_by_name: string | null
}

export type PublishResetResult = {
  week_start: string
  deleted: number
  restored: number
}

export type MyScheduleShift = {
  id: number
  name: string
  shift_type?: ShiftType
  start_time: string | null
  end_time: string | null
  color: string
  is_deleted: boolean
}

export type MyScheduleDay = {
  /** YYYY-MM-DD in the tenant timezone. */
  date: string
  shifts: MyScheduleShift[]
}

export type MySchedule = {
  week_start: string
  week_end: string
  /** Current calendar date in the tenant timezone. */
  today: string
  is_published: boolean
  published_at: string | null
  days: MyScheduleDay[]
}
