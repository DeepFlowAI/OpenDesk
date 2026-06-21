export type OrgImportColumnMapping = {
  file_header: string
  field_key: string | null
  field_id: number | null
  field_name: string | null
  field_type: string | null
  status: string
  message?: string | null
}

export type OrgImportRowError = {
  row_number: number
  identifier?: string | null
  field: string
  reason: string
  raw_values: string[]
}

export type OrgImportPreviewSummary = {
  filename: string
  total_rows: number
  importable_rows: number
  blocked_rows: number
  unsupported_columns: number
}

export type OrgImportPreviewResponse = {
  preview_token: string
  summary: OrgImportPreviewSummary
  file_headers: string[]
  column_mappings: OrgImportColumnMapping[]
  errors: OrgImportRowError[]
  has_more_errors: boolean
}

export type OrgImportExecuteSummary = {
  total_rows: number
  created: number
  failed: number
  skipped: number
}

export type OrgImportExecuteResponse = {
  summary: OrgImportExecuteSummary
  errors: OrgImportRowError[]
}

export type OrgImportErrorReportRow = {
  row_number: number
  values: string[]
  error_reason: string
}

export type OrgImportErrorReportPayload = {
  headers: string[]
  rows: OrgImportErrorReportRow[]
}
