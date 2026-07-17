import ky from 'ky'
import type {
  ConversationFileAccessResponse,
  ConversationFileUploadResponse,
} from '@/models/conversation-file'
import type {
  OfflineMessageSource,
  OfflineMessageQueueType,
  PublicOfflineMessageSendResponse,
  VisitorEnvironmentPayload,
} from '@/service/use-visitor-chat'
import { get, post, postForm } from './base'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''
const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 60000 })
export const CONVERSATION_IMAGE_DISPLAY_PROCESS = 'image/resize,w_720/quality,q_80'

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
  visitorEnvironment?: VisitorEnvironmentPayload | null
  source?: OfflineMessageSource | null
  queueType?: OfflineMessageQueueType | null
  queueId?: number | null
}): Promise<PublicOfflineMessageSendResponse> {
  const formData = new FormData()
  formData.append('file', params.file)
  if (params.source) {
    formData.append('source', params.source)
  }
  if (params.queueType) {
    formData.append('queue_type', params.queueType)
  }
  if (params.queueId) {
    formData.append('queue_id', String(params.queueId))
  }
  if (params.visitorEnvironment?.system) {
    formData.append('system', params.visitorEnvironment.system)
  }
  if (params.visitorEnvironment?.browser) {
    formData.append('browser', params.visitorEnvironment.browser)
  }

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

export async function prepareKnowledgeAttachmentForConversation(params: {
  conversationId: number
  attachmentId: number
}): Promise<ConversationFileUploadResponse> {
  return post<ConversationFileUploadResponse>(
    `v1/conversations/${params.conversationId}/knowledge-attachments/${params.attachmentId}/prepare`,
  )
}

export async function uploadAgentQueueTaskFile(params: {
  taskId: number
  file: File
}): Promise<ConversationFileUploadResponse> {
  const formData = new FormData()
  formData.append('file', params.file)

  return postForm<ConversationFileUploadResponse>(
    `v1/workspace/queue/tasks/${params.taskId}/files`,
    formData,
  )
}

export async function uploadAgentOfflineMessageFile(params: {
  offlineMessageId: number
  file: File
}): Promise<ConversationFileUploadResponse> {
  const formData = new FormData()
  formData.append('file', params.file)

  return postForm<ConversationFileUploadResponse>(
    `v1/offline-messages/${params.offlineMessageId}/files`,
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
  imageProcess?: string
}): Promise<ConversationFileAccessResponse> {
  if (params.offlineMessagePublicId && params.visitorSessionToken) {
    return publicClient
      .get(`v1/public/offline-message-files/${params.fileId}/url`, {
        headers: authHeaders(params.visitorSessionToken),
        searchParams: {
          offline_message_public_id: params.offlineMessagePublicId,
          ...(params.downloadName ? { download_name: params.downloadName } : {}),
          ...(params.download ? { download: 'true' } : {}),
          ...(params.imageProcess ? { image_process: params.imageProcess } : {}),
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
          ...(params.imageProcess ? { image_process: params.imageProcess } : {}),
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
          ...(params.imageProcess ? { image_process: params.imageProcess } : {}),
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
        ...(params.imageProcess ? { image_process: params.imageProcess } : {}),
      },
    },
  )
}
