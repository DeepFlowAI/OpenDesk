import { useQuery, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { get, post, put } from './base'
import type {
  Conversation,
  ConversationListResponse,
  MessageListResponse,
  WorkspaceConversationHistoryResponse,
  AgentStatus,
  AgentStats,
  VisitorWebStatusResponse,
} from '@/models/conversation'

const NS = 'conversations'

export const conversationKeys = {
  all: [NS] as const,
  lists: () => [...conversationKeys.all, 'list'] as const,
  detail: (id: number) => [...conversationKeys.all, 'detail', id] as const,
  messages: (id: number) => [...conversationKeys.all, 'messages', id] as const,
  history: (id: number) => [...conversationKeys.all, 'history', id] as const,
  visitorWebStatus: (id: number) => [...conversationKeys.all, 'visitor-web-status', id] as const,
}

// Patch the cached conversation list so the snapshot a remounted hook
// returns immediately stays in sync with socket pushes (unread_count and
// last message preview). Without this, switching pages can momentarily flash
// a stale unread state harvested from the previous GET response.
export const patchConversationListCache = (
  qc: QueryClient,
  conversationId: number,
  updates: Partial<Conversation>,
) => {
  qc.setQueryData<ConversationListResponse>(conversationKeys.lists(), (prev) => {
    if (!prev) return prev
    let touched = false
    const items = prev.items.map((item) => {
      if (item.id !== conversationId) return item
      touched = true
      return { ...item, ...updates }
    })
    return touched ? { ...prev, items } : prev
  })
}

export const agentKeys = {
  status: ['agent', 'status'] as const,
  stats: ['agent', 'stats'] as const,
}

export const useConversations = (options?: { enabled?: boolean }) =>
  useQuery({
    queryKey: conversationKeys.lists(),
    queryFn: () => get<ConversationListResponse>('v1/conversations'),
    refetchInterval: 30000,
    enabled: options?.enabled,
  })

export const useConversation = (id: number) =>
  useQuery({
    queryKey: conversationKeys.detail(id),
    queryFn: () => get<Conversation>(`v1/conversations/${id}`),
    enabled: !!id,
  })

export const useMessages = (conversationId: number, beforeId?: number) =>
  useQuery({
    queryKey: [...conversationKeys.messages(conversationId), beforeId],
    queryFn: () =>
      get<MessageListResponse>(`v1/conversations/${conversationId}/messages`, {
        searchParams: beforeId ? { before_id: beforeId, limit: 20 } : { limit: 20 },
      }),
    enabled: !!conversationId,
  })

export const useVisitorWebStatus = (
  conversationId: number,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: conversationKeys.visitorWebStatus(conversationId),
    queryFn: () =>
      get<VisitorWebStatusResponse>(
        `v1/conversations/${conversationId}/visitor-web-status`,
      ),
    enabled: !!conversationId && (options?.enabled ?? true),
    staleTime: 10_000,
    retry: 1,
  })

export const fetchConversationHistory = (params: {
  conversationId: number
  beforeId?: number
  limit?: number
}) =>
  get<WorkspaceConversationHistoryResponse>(
    `v1/conversations/${params.conversationId}/history`,
    {
      searchParams: {
        ...(params.beforeId ? { before_id: params.beforeId } : {}),
        limit: params.limit ?? 10,
      },
    },
  )

export const useEndConversation = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<Conversation>(`v1/conversations/${id}/end`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: agentKeys.stats })
    },
  })
}

export const useAgentStatus = () =>
  useQuery({
    queryKey: agentKeys.status,
    queryFn: () => get<AgentStatus>('v1/agent/status'),
  })

export const useUpdateAgentStatus = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (status: string) => put<AgentStatus>('v1/agent/status', { json: { status } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentKeys.status }),
  })
}

export const useAgentStats = () =>
  useQuery({
    queryKey: agentKeys.stats,
    queryFn: () => get<AgentStats>('v1/agent/stats'),
    refetchInterval: 10000,
  })
