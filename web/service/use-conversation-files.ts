import ky from 'ky'
import type {
  ConversationFileAccessResponse,
  ConversationFileUploadResponse,
} from '@/models/conversation-file'
import { postForm } from './base'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 60000 })

export async function uploadVisitorConversationFile(params: {
  conversationId: number
  tenantId: number
  visitorExternalId: string
  file: File
}): Promise<ConversationFileUploadResponse> {
  const formData = new FormData()
  formData.append('file', params.file)

  return publicClient
    .post(`v1/public/conversations/${params.conversationId}/files`, {
      searchParams: {
        tenant_id: String(params.tenantId),
        visitor_external_id: params.visitorExternalId,
      },
      body: formData,
    })
    .json<ConversationFileUploadResponse>()
}

export async function uploadAgentConversationFile(params: {
  conversationId: number
  file: File
}): Promise<ConversationFileUploadResponse> {
  const formData = new FormData()
  formData.append('file', params.file)

  return postForm<ConversationFileUploadResponse>(
    `v1/conversations/${params.conversationId}/files`,
    formData,
  )
}

export async function getConversationFileUrl(params: {
  conversationId: number
  fileId: string
  downloadName?: string
  download?: boolean
}): Promise<ConversationFileAccessResponse> {
  return publicClient
    .get(`v1/public/conversation-files/${params.fileId}/url`, {
      searchParams: {
        conversation_id: String(params.conversationId),
        ...(params.downloadName ? { download_name: params.downloadName } : {}),
        ...(params.download ? { download: 'true' } : {}),
      },
    })
    .json<ConversationFileAccessResponse>()
}
