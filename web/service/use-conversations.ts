import { useQuery, useInfiniteQuery, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  Conversation,
  ConversationHistoryListResponse,
  ConversationListResponse,
  Message,
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

const visitorWebStatusTimestamp = (value: VisitorWebStatusResponse | undefined) => {
  const timestamp = Date.parse(value?.checked_at ?? '')
  return Number.isNaN(timestamp) ? 0 : timestamp
}

export const setVisitorWebStatusQueryData = (
  qc: QueryClient,
  payload: VisitorWebStatusResponse,
) => {
  qc.setQueryData<VisitorWebStatusResponse>(
    conversationKeys.visitorWebStatus(payload.conversation_id),
    (prev) =>
      visitorWebStatusTimestamp(payload) >= visitorWebStatusTimestamp(prev)
        ? payload
      : prev,
  )
}

const syncConversationCache = (qc: QueryClient, conversation: Conversation) => {
  qc.setQueryData(conversationKeys.detail(conversation.id), conversation)
  patchConversationListCache(qc, conversation.id, {
    is_pinned: conversation.is_pinned,
    pinned_at: conversation.pinned_at,
    is_timeout_locked: conversation.is_timeout_locked,
    timeout_locked_at: conversation.timeout_locked_at,
    timeout_locked_by_id: conversation.timeout_locked_by_id,
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
  options?: { enabled?: boolean; refetchInterval?: number | false },
) =>
  useQuery({
    queryKey: conversationKeys.visitorWebStatus(conversationId),
    queryFn: () =>
      get<VisitorWebStatusResponse>(
        `v1/conversations/${conversationId}/visitor-web-status`,
      ),
    enabled: !!conversationId && (options?.enabled ?? true),
    staleTime: 10_000,
    refetchInterval: options?.refetchInterval ?? false,
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

export const usePinConversation = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<Conversation>(`v1/conversations/${id}/pin`),
    onSuccess: (conversation) => syncConversationCache(qc, conversation),
  })
}

export const useUnpinConversation = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del<Conversation>(`v1/conversations/${id}/pin`),
    onSuccess: (conversation) => syncConversationCache(qc, conversation),
  })
}

export const useLockConversationTimeout = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<Conversation>(`v1/conversations/${id}/timeout-lock`),
    onSuccess: (conversation) => syncConversationCache(qc, conversation),
  })
}

export const useUnlockConversationTimeout = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del<Conversation>(`v1/conversations/${id}/timeout-lock`),
    onSuccess: (conversation) => syncConversationCache(qc, conversation),
  })
}

export const useRecallMessage = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ conversationId, messageId }: { conversationId: number; messageId: number }) =>
      post<Message>(`v1/conversations/${conversationId}/messages/${messageId}/recall`),
    onSuccess: (message) => {
      qc.invalidateQueries({ queryKey: conversationKeys.messages(message.conversation_id) })
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
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
