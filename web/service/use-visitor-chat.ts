import { useQuery } from '@tanstack/react-query'
import ky from 'ky'
import type { ChannelPublic } from '@/models/channel'
import type {
  Message,
  VisitorConversationHistoryResponse,
  VisitorUnreadOfflineReplyResponse,
} from '@/models/conversation'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 30000 })

const publicGet = <T>(url: string, options?: Parameters<typeof publicClient.get>[1]) =>
  publicClient.get(url, options).json<T>()

const withVisitorToken = (visitorSessionToken: string) => ({
  Authorization: `Bearer ${visitorSessionToken}`,
})

export type ChannelPublicConfig = ChannelPublic

export type VisitorSessionResponse = {
  visitor_session_token: string
  visitor_external_id: string
  visitor_secret?: string | null
  expires_in: number
  context_warnings?: string[]
}

export type PublicMessage = Omit<Message, 'conversation_id'> & {
  conversation_public_id: string
}

export type PublicMessageListResponse = {
  items: PublicMessage[]
  has_more: boolean
}

export type PublicOfflineMessageResponse = {
  offline_message_public_id: string
  status: 'pending' | 'converted'
  messages: PublicMessage[]
  has_more: boolean
  conversation_public_id?: string | null
}

export type PublicOfflineMessageSendResponse = {
  ok: boolean
  offline_message_public_id?: string
  message?: PublicMessage
  messages?: PublicMessage[]
}

export const visitorChatKeys = {
  channel: (key: string, visitorExternalId?: string | null, currentConversationPublicId?: string | null) =>
    ['public', 'channel', key, visitorExternalId ?? null, currentConversationPublicId ?? null] as const,
  messages: (conversationPublicId: string, beforeId?: number) =>
    ['public', 'messages', conversationPublicId, beforeId] as const,
  offlineMessages: (offlineMessagePublicId: string, beforeId?: number) =>
    ['public', 'offline-messages', offlineMessagePublicId, beforeId] as const,
}

export const useChannelPublic = (
  channelKey: string,
  visitorExternalId?: string | null,
  currentConversationPublicId?: string | null,
) =>
  useQuery({
    queryKey: visitorChatKeys.channel(channelKey, visitorExternalId, currentConversationPublicId),
    queryFn: () =>
      publicGet<ChannelPublicConfig>(`v1/public/channels/${channelKey}`, {
        searchParams: {
          ...(visitorExternalId ? { visitor_external_id: visitorExternalId } : {}),
          ...(currentConversationPublicId
            ? { current_conversation_public_id: currentConversationPublicId }
            : {}),
        },
      }),
    enabled: !!channelKey,
    placeholderData: (previousData, previousQuery) => {
      const previousKey = previousQuery?.queryKey
      return Array.isArray(previousKey) && previousKey[2] === channelKey
        ? previousData
        : undefined
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

export const createVisitorSession = (params: {
  channelKey: string
  visitorExternalId?: string | null
  visitorSecret?: string | null
  visitorName?: string | null
  metadata?: Record<string, unknown> | null
  contextToken?: string | null
}) =>
  publicClient
    .post(`v1/public/channels/${params.channelKey}/visitor-session`, {
      json: {
        ...(params.visitorExternalId ? { visitor_external_id: params.visitorExternalId } : {}),
        ...(params.visitorSecret ? { visitor_secret: params.visitorSecret } : {}),
        ...(params.visitorName ? { visitor_name: params.visitorName } : {}),
        ...(params.metadata ? { metadata: params.metadata } : {}),
        ...(params.contextToken ? { contextToken: params.contextToken } : {}),
      },
    })
    .json<VisitorSessionResponse>()

export const syncConversationContext = (params: {
  conversationPublicId: string
  visitorSessionToken: string
  contextToken: string
}) =>
  publicClient
    .post(`v1/public/conversations/${params.conversationPublicId}/context`, {
      headers: withVisitorToken(params.visitorSessionToken),
      json: { contextToken: params.contextToken },
    })
    .json<{
      ok: boolean
      warnings: string[]
      customer_synced: boolean
      session_summary_synced: boolean
    }>()

export const fetchPublicMessages = (params: {
  conversationPublicId: string
  visitorSessionToken: string
  beforeId?: number | null
  limit?: number
}) =>
  publicGet<PublicMessageListResponse>(
    `v1/public/conversations/${params.conversationPublicId}/messages`,
    {
      headers: withVisitorToken(params.visitorSessionToken),
      searchParams: {
        ...(params.beforeId ? { before_id: params.beforeId } : {}),
        limit: params.limit ?? 20,
      },
    },
  )

export const createOrContinueOfflineMessage = (params: {
  visitorSessionToken: string
  visitorName?: string | null
  metadata?: Record<string, unknown> | null
}) =>
  publicClient
    .post('v1/public/offline-messages', {
      headers: withVisitorToken(params.visitorSessionToken),
      json: {
        ...(params.visitorName ? { visitor_name: params.visitorName } : {}),
        ...(params.metadata ? { metadata: params.metadata } : {}),
      },
    })
    .json<PublicOfflineMessageResponse>()

export const fetchCurrentOfflineMessage = (params: {
  visitorSessionToken: string
  beforeId?: number | null
  limit?: number
}) =>
  publicGet<PublicOfflineMessageResponse | null>(
    'v1/public/offline-messages/current',
    {
      headers: withVisitorToken(params.visitorSessionToken),
      searchParams: {
        ...(params.beforeId ? { before_id: params.beforeId } : {}),
        limit: params.limit ?? 50,
      },
    },
  )

export const fetchOfflineMessages = (params: {
  offlineMessagePublicId: string
  visitorSessionToken: string
  beforeId?: number | null
  limit?: number
}) =>
  publicGet<PublicOfflineMessageResponse>(
    `v1/public/offline-messages/${params.offlineMessagePublicId}/messages`,
    {
      headers: withVisitorToken(params.visitorSessionToken),
      searchParams: {
        ...(params.beforeId ? { before_id: params.beforeId } : {}),
        limit: params.limit ?? 50,
      },
    },
  )

export const createOfflineMessageWithMessage = (params: {
  visitorSessionToken: string
  contentType: 'text' | 'image' | 'file'
  content: string
}) =>
  publicClient
    .post('v1/public/offline-messages/messages', {
      headers: withVisitorToken(params.visitorSessionToken),
      json: {
        content_type: params.contentType,
        content: params.content,
      },
    })
    .json<PublicOfflineMessageSendResponse>()

export const sendOfflineMessage = (params: {
  offlineMessagePublicId: string
  visitorSessionToken: string
  contentType: 'text' | 'image' | 'file'
  content: string
}) =>
  publicClient
    .post(`v1/public/offline-messages/${params.offlineMessagePublicId}/messages`, {
      headers: withVisitorToken(params.visitorSessionToken),
      json: {
        content_type: params.contentType,
        content: params.content,
      },
    })
    .json<PublicOfflineMessageSendResponse>()

export const fetchVisitorConversationHistory = (params: {
  visitorSessionToken: string
  currentConversationPublicId?: string | null
  beforePublicId?: string | null
  limit?: number
}) =>
  publicGet<VisitorConversationHistoryResponse>(
    'v1/public/conversations/history',
    {
      headers: withVisitorToken(params.visitorSessionToken),
      searchParams: {
        ...(params.currentConversationPublicId
          ? { current_conversation_public_id: params.currentConversationPublicId }
          : {}),
        ...(params.beforePublicId ? { before_public_id: params.beforePublicId } : {}),
        limit: params.limit ?? 10,
      },
    },
  )

export const fetchUnreadOfflineReplies = (params: {
  visitorSessionToken: string
  limit?: number
}) =>
  publicGet<VisitorUnreadOfflineReplyResponse>(
    'v1/public/conversations/unread-offline-replies',
    {
      headers: withVisitorToken(params.visitorSessionToken),
      searchParams: {
        limit: params.limit ?? 3,
      },
    },
  )

export const markConversationCustomerRead = (params: {
  conversationPublicId: string
  visitorSessionToken: string
}) =>
  publicClient
    .post(`v1/public/conversations/${params.conversationPublicId}/customer-read`, {
      headers: withVisitorToken(params.visitorSessionToken),
    })
    .json<{ ok: boolean }>()
