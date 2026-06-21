import { useQuery, useInfiniteQuery, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { get, post, put } from './base'
import type {
  Conversation,
  ConversationHistoryListResponse,
  ConversationListResponse,
  MessageListResponse,
  StartConversationFromHistoryResponse,
  WorkspaceConversationHistoryResponse,
  WorkspaceMessageSearchResponse,
  AgentStatus,
  AgentStats,
  VisitorWebStatusResponse,
} from '@/models/conversation'

const NS = 'conversations'
export type ConversationListScope = 'my' | 'peers'

export const conversationKeys = {
  all: [NS] as const,
  lists: () => [...conversationKeys.all, 'list'] as const,
  list: (scope: ConversationListScope) => [...conversationKeys.lists(), scope] as const,
  historyLists: () => [...conversationKeys.all, 'history-list'] as const,
  historyList: () => [...conversationKeys.historyLists()] as const,
  detail: (id: number) => [...conversationKeys.all, 'detail', id] as const,
  messages: (id: number) => [...conversationKeys.all, 'messages', id] as const,
  history: (id: number) => [...conversationKeys.all, 'history', id] as const,
  visitorHistory: (id: number, q: string) => [...conversationKeys.all, 'visitor-history', id, q] as const,
  messageSearch: (id: number, q: string) => [...conversationKeys.all, 'message-search', id, q] as const,
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
  qc.setQueriesData<ConversationListResponse>({ queryKey: conversationKeys.lists() }, (prev) => {
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

export const useConversations = (
  options?: {
    enabled?: boolean
    scope?: ConversationListScope
  },
) => {
  const scope = options?.scope ?? 'my'
  return useQuery({
    queryKey: conversationKeys.list(scope),
    queryFn: () => get<ConversationListResponse>('v1/conversations', { searchParams: { scope } }),
    refetchInterval: 30000,
    enabled: options?.enabled,
  })
}

export const useConversation = (id: number) =>
  useQuery({
    queryKey: conversationKeys.detail(id),
    queryFn: () => get<Conversation>(`v1/conversations/${id}`),
    enabled: !!id,
  })

export const fetchConversationHistoryList = (params?: {
  beforeId?: number
  limit?: number
}) =>
  get<ConversationHistoryListResponse>('v1/conversations/history', {
    searchParams: {
      limit: params?.limit ?? 20,
      ...(params?.beforeId ? { before_id: params.beforeId } : {}),
    },
  })

export const useConversationHistory = (options?: { enabled?: boolean }) =>
  useInfiniteQuery({
    queryKey: conversationKeys.historyList(),
    queryFn: ({ pageParam }: { pageParam: number | undefined }) =>
      fetchConversationHistoryList({ beforeId: pageParam, limit: 20 }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.items.at(-1)?.id : undefined,
    refetchInterval: 30000,
    enabled: options?.enabled,
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

export const fetchConversationMessageSearch = (params: {
  conversationId: number
  q?: string
  beforeId?: number
  limit?: number
}) =>
  get<WorkspaceMessageSearchResponse>(
    `v1/conversations/${params.conversationId}/message-search`,
    {
      searchParams: {
        limit: params.limit ?? 30,
        ...(params.q?.trim() ? { q: params.q.trim() } : {}),
        ...(params.beforeId ? { before_id: params.beforeId } : {}),
      },
    },
  )

export const useConversationMessageSearch = (
  conversationId: number,
  q: string,
  options?: { enabled?: boolean },
) =>
  useInfiniteQuery({
    queryKey: conversationKeys.messageSearch(conversationId, q.trim()),
    queryFn: ({ pageParam }: { pageParam: number | undefined }) =>
      fetchConversationMessageSearch({
        conversationId,
        q,
        beforeId: pageParam,
        limit: 30,
      }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.items.at(-1)?.id : undefined,
    enabled: !!conversationId && (options?.enabled ?? true),
  })

export const fetchConversationHistory = (params: {
  conversationId: number
  q?: string
  beforeId?: number
  limit?: number
}) =>
  get<WorkspaceConversationHistoryResponse>(
    `v1/conversations/${params.conversationId}/history`,
    {
      searchParams: {
        ...(params.q?.trim() ? { q: params.q.trim() } : {}),
        ...(params.beforeId ? { before_id: params.beforeId } : {}),
        limit: params.limit ?? 10,
      },
    },
  )

export const useWorkspaceConversationHistory = (
  conversationId: number,
  q: string,
  options?: { enabled?: boolean },
) =>
  useInfiniteQuery({
    queryKey: conversationKeys.visitorHistory(conversationId, q.trim()),
    queryFn: ({ pageParam }: { pageParam: number | undefined }) =>
      fetchConversationHistory({
        conversationId,
        q,
        beforeId: pageParam,
        limit: 10,
      }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.items.at(-1)?.id : undefined,
    enabled: !!conversationId && (options?.enabled ?? true),
  })

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

export const useStartConversationFromHistory = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      post<StartConversationFromHistoryResponse>(`v1/conversations/history/${id}/start`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: conversationKeys.historyLists() })
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

export const useUpdateAgentMaxConcurrent = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (maxConcurrent: number) =>
      put<AgentStats>('v1/agent/max-concurrent', { json: { max_concurrent: maxConcurrent } }),
    onSuccess: (data) => {
      qc.setQueryData(agentKeys.stats, data)
    },
  })
}
