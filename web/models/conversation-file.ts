export type ConversationFilePayload = {
  schema_version: 1
  file_id: string
  name: string
  size: number
  mime_type: string
  width?: number | null
  height?: number | null
  thumbnail_file_id?: string | null
  hash?: string | null
}

export type ConversationFileUploadResponse = ConversationFilePayload & {
  access_url: string
}

export type ConversationFileAccessResponse = {
  url: string
  expires_seconds: number
}
