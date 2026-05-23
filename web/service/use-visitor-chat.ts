import { useQuery } from '@tanstack/react-query'
import ky from 'ky'
import type { ChannelPublic } from '@/models/channel'
import type { Message, VisitorConversationHistoryResponse } from '@/models/conversation'

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
}

export type PublicMessage = Omit<Message, 'conversation_id'> & {
  conversation_public_id: string
}

export type PublicMessageListResponse = {
  items: PublicMessage[]
  has_more: boolean
}

export const visitorChatKeys = {
  channel: (key: string, visitorExternalId?: string | null, currentConversationPublicId?: string | null) =>
    ['public', 'channel', key, visitorExternalId ?? null, currentConversationPublicId ?? null] as const,
  messages: (conversationPublicId: string, beforeId?: number) =>
    ['public', 'messages', conversationPublicId, beforeId] as const,
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
}) =>
  publicClient
    .post(`v1/public/channels/${params.channelKey}/visitor-session`, {
      json: {
        ...(params.visitorExternalId ? { visitor_external_id: params.visitorExternalId } : {}),
        ...(params.visitorSecret ? { visitor_secret: params.visitorSecret } : {}),
        ...(params.visitorName ? { visitor_name: params.visitorName } : {}),
        ...(params.metadata ? { metadata: params.metadata } : {}),
      },
    })
    .json<VisitorSessionResponse>()

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
