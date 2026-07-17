import type { PaginatedResponse } from './common'

export type KnowledgeDocumentStatus = 'draft' | 'published'
export type KnowledgeDocumentDisplayStatus = KnowledgeDocumentStatus | 'expired'
export type KnowledgeValidityType = 'permanent' | 'scheduled'

export type KnowledgeActorRef = {
  actor_type: string | null
  actor_id: number | null
  actor_name: string | null
}

export type KnowledgeDirectoryNode = {
  id: number
  tenant_id: number
  parent_id: number | null
  name: string
  sort_order: number
  depth: number
  document_count: number
  created_at: string
  updated_at: string
  created_by: KnowledgeActorRef | null
  updated_by: KnowledgeActorRef | null
  children: KnowledgeDirectoryNode[]
}

export type KnowledgeDirectoryListResponse = {
  items: KnowledgeDirectoryNode[]
}

export type KnowledgeDirectoryPayload = {
  name: string
  parent_id?: number | null
}

export type KnowledgeDirectoryMovePayload = {
  parent_id?: number | null
  sort_order?: number | null
}

export type KnowledgeDirectoryPathItem = {
  id: number
  name: string
}

export type KnowledgeDocumentAttachment = {
  id: number
  document_id: number | null
  name: string
  size: number
  mime_type: string
  sort_order: number
  created_at: string
  updated_at: string
}

export type KnowledgeDocumentAttachmentUrl = {
  url: string
  expires_seconds: number
}

export type KnowledgeDocument = {
  id: number
  tenant_id: number
  directory_id: number
  directory_path: KnowledgeDirectoryPathItem[]
  title: string
  content_html: string
  attachments: KnowledgeDocumentAttachment[]
  status: KnowledgeDocumentStatus
  display_status: KnowledgeDocumentDisplayStatus
  validity_type: KnowledgeValidityType
  valid_from: string | null
  valid_to: string | null
  created_at: string
  updated_at: string
  created_by: KnowledgeActorRef | null
  updated_by: KnowledgeActorRef | null
}

export type KnowledgeDocumentListParams = {
  directory?: number | null
  q?: string
  display_status?: KnowledgeDocumentDisplayStatus
  page?: number
  per_page?: number
}

export type KnowledgeDocumentPayload = {
  title: string
  directory_id: number
  content_html: string
  attachment_ids: number[]
  status: KnowledgeDocumentStatus
  validity_type: KnowledgeValidityType
  valid_from?: string | null
  valid_to?: string | null
}

export type KnowledgeDocumentListResponse = PaginatedResponse<KnowledgeDocument>

export type KnowledgeRecommendationStatus = 'no_conversation' | 'updating' | 'no_vector' | 'ready' | 'failed'

export type KnowledgeRecommendationParams = {
  conversation_id?: number | null
  limit?: number
}

export type KnowledgeRecommendationResponse = {
  status: KnowledgeRecommendationStatus
  items: KnowledgeDocument[]
  limit: number
  vector_updated_at: string | null
  message: string | null
}

export type KnowledgeInspirationStatus = 'pending' | 'archived' | 'document_created'
export type KnowledgeInspirationContentFormat = 'text' | 'rich_text'

export type KnowledgeInspiration = {
  id: number
  tenant_id: number
  content_html: string
  content_plain: string
  source_type: string
  source_conversation_id: number | null
  source_message_id: number | null
  status: KnowledgeInspirationStatus
  created_at: string
  updated_at: string
  created_by: KnowledgeActorRef | null
  updated_by: KnowledgeActorRef | null
}

export type KnowledgeInspirationListParams = {
  q?: string
  status?: KnowledgeInspirationStatus | null
  page?: number
  per_page?: number
}

export type KnowledgeInspirationPayload = {
  content: string
  content_format?: KnowledgeInspirationContentFormat
  source_conversation_id?: number | null
  source_message_id?: number | null
}

export type KnowledgeInspirationListResponse = PaginatedResponse<KnowledgeInspiration>

export type KnowledgeInspirationCountsResponse = {
  total: number
  pending: number
  archived: number
  document_created: number
}

export type KnowledgeImportAction = 'create' | 'update' | 'skip' | 'error'

export type KnowledgeImportSummary = {
  filename: string
  total_rows: number
  create_directories: number
  create_documents: number
  update_documents: number
  skipped_rows: number
  error_rows: number
}

export type KnowledgeImportRowResult = {
  row_number: number
  action: KnowledgeImportAction
  id: number | null
  directory_path: string | null
  title: string | null
  message: string | null
  errors: string[]
  raw_values: string[]
}

export type KnowledgeImportPreviewResponse = {
  preview_token: string
  summary: KnowledgeImportSummary
  file_headers: string[]
  rows: KnowledgeImportRowResult[]
  has_errors: boolean
}

export type KnowledgeImportExecuteResponse = {
  summary: KnowledgeImportSummary
  rows: KnowledgeImportRowResult[]
  has_errors: boolean
}
