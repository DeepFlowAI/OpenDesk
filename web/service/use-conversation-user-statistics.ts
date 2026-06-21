import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  ConversationUserStatistics,
  UserStatFieldSettings,
  UserStatFieldSettingsPayload,
} from '@/models/conversation-user-statistics'

const NS = 'conversation-user-statistics'

export const conversationUserStatisticsKeys = {
  all: [NS] as const,
  settings: () => [...conversationUserStatisticsKeys.all, 'settings'] as const,
  details: () => [...conversationUserStatisticsKeys.all, 'detail'] as const,
  detail: (conversationId: number) => [...conversationUserStatisticsKeys.details(), conversationId] as const,
}

export const useUserStatFieldSettings = () =>
  useQuery({
    queryKey: conversationUserStatisticsKeys.settings(),
    queryFn: () => get<UserStatFieldSettings>('v1/conversation-settings/user-stat-fields'),
  })

export const useSaveUserStatFieldSettings = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UserStatFieldSettingsPayload) =>
      put<UserStatFieldSettings>('v1/conversation-settings/user-stat-fields', { json: data }),
    onSuccess: (data) => {
      qc.setQueryData(conversationUserStatisticsKeys.settings(), data)
      qc.invalidateQueries({ queryKey: conversationUserStatisticsKeys.details() })
    },
  })
}

export const useConversationUserStatistics = (
  conversationId: number,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: conversationUserStatisticsKeys.detail(conversationId),
    queryFn: () => get<ConversationUserStatistics>(`v1/conversations/${conversationId}/user-statistics`),
    enabled: !!conversationId && (options?.enabled ?? true),
    staleTime: 30_000,
    retry: 1,
  })
