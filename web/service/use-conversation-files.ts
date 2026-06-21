import ky from 'ky'
import type {
  ConversationFileAccessResponse,
  ConversationFileUploadResponse,
} from '@/models/conversation-file'
import type { PublicOfflineMessageSendResponse } from '@/service/use-visitor-chat'
import { get, postForm } from './base'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''
const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 60000 })

const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` })

export async function uploadVisitorConversationFile(params: {
  conversationPublicId: string
  visitorSessionToken: string
  file: File
}): Promise<ConversationFileUploadResponse> {
  const formData = new FormData()
  formData.append('file', params.file)

  return publicClient
    .post(`v1/public/conversations/${params.conversationPublicId}/files`, {
      headers: authHeaders(params.visitorSessionToken),
      body: formData,
    })
    .json<ConversationFileUploadResponse>()
}

export async function uploadVisitorOfflineMessageFile(params: {
  offlineMessagePublicId: string
  visitorSessionToken: string
  file: File
}): Promise<ConversationFileUploadResponse> {
  const formData = new FormData()
  formData.append('file', params.file)

  return publicClient
    .post(`v1/public/offline-messages/${params.offlineMessagePublicId}/files`, {
      headers: authHeaders(params.visitorSessionToken),
      body: formData,
    })
    .json<ConversationFileUploadResponse>()
}

export async function sendVisitorOfflineMessageFile(params: {
  visitorSessionToken: string
  file: File
}): Promise<PublicOfflineMessageSendResponse> {
  const formData = new FormData()
  formData.append('file', params.file)

  return publicClient
    .post('v1/public/offline-messages/files', {
      headers: authHeaders(params.visitorSessionToken),
      body: formData,
    })
    .json<PublicOfflineMessageSendResponse>()
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
  conversationId?: number
  conversationPublicId?: string
  offlineMessageId?: number
  offlineMessagePublicId?: string
  visitorSessionToken?: string
  fileId: string
  downloadName?: string
  download?: boolean
}): Promise<ConversationFileAccessResponse> {
  if (params.offlineMessagePublicId && params.visitorSessionToken) {
    return publicClient
      .get(`v1/public/offline-message-files/${params.fileId}/url`, {
        headers: authHeaders(params.visitorSessionToken),
        searchParams: {
          offline_message_public_id: params.offlineMessagePublicId,
          ...(params.downloadName ? { download_name: params.downloadName } : {}),
          ...(params.download ? { download: 'true' } : {}),
        },
      })
      .json<ConversationFileAccessResponse>()
  }

  if (params.conversationPublicId && params.visitorSessionToken) {
    return publicClient
      .get(`v1/public/conversation-files/${params.fileId}/url`, {
        headers: authHeaders(params.visitorSessionToken),
        searchParams: {
          conversation_public_id: params.conversationPublicId,
          ...(params.downloadName ? { download_name: params.downloadName } : {}),
          ...(params.download ? { download: 'true' } : {}),
        },
      })
      .json<ConversationFileAccessResponse>()
  }

  if (params.offlineMessageId) {
    return get<ConversationFileAccessResponse>(
      `v1/offline-messages/${params.offlineMessageId}/files/${params.fileId}/url`,
      {
        searchParams: {
          ...(params.downloadName ? { download_name: params.downloadName } : {}),
          ...(params.download ? { download: 'true' } : {}),
        },
      },
    )
  }

  if (!params.conversationId) {
    throw new Error('conversationId is required for agent file access')
  }

  return get<ConversationFileAccessResponse>(
    `v1/conversations/${params.conversationId}/files/${params.fileId}/url`,
    {
      searchParams: {
        ...(params.downloadName ? { download_name: params.downloadName } : {}),
        ...(params.download ? { download: 'true' } : {}),
      },
    },
  )
}
