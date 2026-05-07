import { useQuery } from '@tanstack/react-query'
import ky from 'ky'
import type { ChannelPublic } from '@/models/channel'
import type { Message, VisitorConversationHistoryResponse } from '@/models/conversation'

// API base URL must be supplied via NEXT_PUBLIC_API_URL (see web/.env.example).
// We intentionally avoid a hard-coded localhost fallback so production builds
// never silently target an internal/dev address.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 30000 })

const publicGet = <T>(url: string, options?: Parameters<typeof publicClient.get>[1]) =>
  publicClient.get(url, options).json<T>()

export type ChannelPublicConfig = ChannelPublic

export type MessageListResponse = {
  items: Message[]
  has_more: boolean
}

export const visitorChatKeys = {
  channel: (id: number, visitorExternalId?: string | null, currentConversationId?: number | null) =>
    ['public', 'channel', id, visitorExternalId ?? null, currentConversationId ?? null] as const,
  messages: (convId: number, beforeId?: number) => ['public', 'messages', convId, beforeId] as const,
}

export const useChannelPublic = (
  channelId: number,
  visitorExternalId?: string | null,
  currentConversationId?: number | null,
) =>
  useQuery({
    queryKey: visitorChatKeys.channel(channelId, visitorExternalId, currentConversationId),
    queryFn: () =>
      publicGet<ChannelPublicConfig>(`v1/public/channels/${channelId}`, {
        searchParams: {
          ...(visitorExternalId ? { visitor_external_id: visitorExternalId } : {}),
          ...(currentConversationId ? { current_conversation_id: currentConversationId } : {}),
        },
      }),
    enabled: !!channelId && !!visitorExternalId,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

export const fetchVisitorConversationHistory = (params: {
  channelId: number
  visitorExternalId: string
  currentConversationId?: number | null
  beforeId?: number | null
  limit?: number
}) =>
  publicGet<VisitorConversationHistoryResponse>(
    `v1/public/channels/${params.channelId}/conversation-history`,
    {
      searchParams: {
        visitor_external_id: params.visitorExternalId,
        ...(params.currentConversationId ? { current_conversation_id: params.currentConversationId } : {}),
        ...(params.beforeId ? { before_id: params.beforeId } : {}),
        limit: params.limit ?? 10,
      },
    },
  )
