import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { get, post } from './base'
import { agentKeys, conversationKeys } from '@/service/use-conversations'
import type {
  OfflineMessage,
  OfflineMessageCountResponse,
  OfflineMessageConvertResponse,
  OfflineMessageDetail,
  OfflineMessageListResponse,
} from '@/models/offline-message'

const NS = 'offline-messages'

export type OfflineMessageListStatus = 'pending' | 'converted' | 'all'

export const offlineMessageKeys = {
  all: [NS] as const,
  lists: () => [...offlineMessageKeys.all, 'list'] as const,
  list: (status: OfflineMessageListStatus) => [...offlineMessageKeys.lists(), status] as const,
  counts: () => [...offlineMessageKeys.all, 'count'] as const,
  count: (status: OfflineMessageListStatus) => [...offlineMessageKeys.counts(), status] as const,
  detail: (id: number) => [...offlineMessageKeys.all, 'detail', id] as const,
}

export const getNextPendingOfflineMessageId = (
  items: OfflineMessage[],
  currentId: number,
): number | null => {
  const index = items.findIndex((item) => item.id === currentId)
  if (index < 0) return items[0]?.id ?? null
  if (index + 1 < items.length) return items[index + 1].id
  return null
}

export const removePendingOfflineMessageFromListCache = (
  qc: QueryClient,
  offlineMessageId: number,
) => {
  qc.setQueryData<OfflineMessageListResponse>(offlineMessageKeys.list('pending'), (prev) => {
    if (!prev) return prev
    const items = prev.items.filter((item) => item.id !== offlineMessageId)
    if (items.length === prev.items.length) return prev
    return {
      ...prev,
      items,
      total: typeof prev.total === 'number' ? Math.max(0, prev.total - 1) : prev.total,
    }
  })
}

export const useOfflineMessages = (params?: {
  status?: OfflineMessageListStatus
  enabled?: boolean
}) => {
  const status = params?.status ?? 'pending'
  const enabled = params?.enabled ?? true
  return useQuery({
    queryKey: offlineMessageKeys.list(status),
    queryFn: () =>
      get<OfflineMessageListResponse>('v1/offline-messages', {
        searchParams: { status, limit: 100 },
      }),
    enabled,
    refetchInterval: enabled ? 30000 : false,
  })
}

export const useOfflineMessageCount = (params?: {
  status?: OfflineMessageListStatus
  enabled?: boolean
}) => {
  const status = params?.status ?? 'pending'
  const enabled = params?.enabled ?? true
  return useQuery({
    queryKey: offlineMessageKeys.count(status),
    queryFn: () =>
      get<OfflineMessageCountResponse>('v1/offline-messages/count', {
        searchParams: { status },
      }),
    enabled,
    refetchInterval: enabled ? 30000 : false,
  })
}

export const useOfflineMessage = (id: number | null) =>
  useQuery({
    queryKey: id ? offlineMessageKeys.detail(id) : [...offlineMessageKeys.all, 'detail', null],
    queryFn: () => get<OfflineMessageDetail>(`v1/offline-messages/${id}`),
    enabled: !!id,
  })

export const useCreateConversationFromOfflineMessage = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      post<OfflineMessageConvertResponse>(`v1/offline-messages/${id}/conversation`),
    onSuccess: (_data, id) => {
      removePendingOfflineMessageFromListCache(qc, id)
      qc.invalidateQueries({ queryKey: offlineMessageKeys.lists() })
      qc.invalidateQueries({ queryKey: offlineMessageKeys.detail(id) })
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: agentKeys.stats })
    },
  })
}

export const useAssignOfflineMessageToSelf = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      post<OfflineMessageConvertResponse>(`v1/offline-messages/${id}/assign-self`, {
        json: { reason: reason || undefined },
      }),
    onSuccess: (_data, { id }) => {
      removePendingOfflineMessageFromListCache(qc, id)
      qc.invalidateQueries({ queryKey: offlineMessageKeys.lists() })
      qc.invalidateQueries({ queryKey: offlineMessageKeys.detail(id) })
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: agentKeys.stats })
    },
  })
}

export const useAssignOfflineMessageToAgent = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, agentId, reason }: { id: number; agentId: number; reason?: string }) =>
      post<OfflineMessageConvertResponse>(`v1/offline-messages/${id}/assign`, {
        json: { agent_id: agentId, reason: reason || undefined },
      }),
    onSuccess: (_data, { id }) => {
      removePendingOfflineMessageFromListCache(qc, id)
      qc.invalidateQueries({ queryKey: offlineMessageKeys.lists() })
      qc.invalidateQueries({ queryKey: offlineMessageKeys.detail(id) })
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: agentKeys.stats })
    },
  })
}
