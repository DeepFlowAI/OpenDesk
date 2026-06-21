export type UserImportColumnMapping = {
  file_header: string
  field_key: string | null
  field_id: number | null
  field_name: string | null
  field_type: string | null
  status: string
  message?: string | null
}

export type UserImportRowError = {
  row_number: number
  identifier?: string | null
  field: string
  reason: string
  raw_values: string[]
}

export type UserImportPreviewSummary = {
  filename: string
  total_rows: number
  importable_rows: number
  blocked_rows: number
  unsupported_columns: number
}

export type UserImportPreviewResponse = {
  preview_token: string
  summary: UserImportPreviewSummary
  file_headers: string[]
  column_mappings: UserImportColumnMapping[]
  errors: UserImportRowError[]
  has_more_errors: boolean
}

export type UserImportExecuteSummary = {
  total_rows: number
  created: number
  failed: number
  skipped: number
}

export type UserImportExecuteResponse = {
  summary: UserImportExecuteSummary
  errors: UserImportRowError[]
}

export type UserImportErrorReportRow = {
  row_number: number
  values: string[]
  error_reason: string
}

export type UserImportErrorReportPayload = {
  headers: string[]
  rows: UserImportErrorReportRow[]
}
