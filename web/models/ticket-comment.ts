/**
 * Ticket comment models — mirrors the FastAPI `TicketComment*` schemas.
 */

export type TicketCommentAttachment = {
  url: string
  name: string
  size?: number | null
  content_type?: string | null
}

export type TicketCommentBodyFormat = 'html' | 'markdown'

export type TicketComment = {
  id: number
  tenant_id: number
  ticket_id: number
  author_id: number | null
  author_name: string | null
  /** Present when the author is an employee with an uploaded profile photo. */
  author_avatar?: string | null
  body: string | null
  body_format: TicketCommentBodyFormat
  attachments: TicketCommentAttachment[] | null
  created_at: string
  updated_at: string
}

export type CreateTicketCommentPayload = {
  body?: string | null
  body_format?: TicketCommentBodyFormat
  attachments?: TicketCommentAttachment[] | null
}
