import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  ConversationTranslationSettings,
  ConversationTranslationSettingsUpdate,
  LingoMasterSettings,
  LingoMasterSettingsUpdate,
} from '@/models/lingomaster'
import { get, patch, put } from '@/service/base'

export const lingomasterKeys = {
  all: ['lingomaster'] as const,
  settings: () => [...lingomasterKeys.all, 'settings'] as const,
  conversations: () => [...lingomasterKeys.all, 'conversation'] as const,
  conversation: (conversationId: number) => [...lingomasterKeys.conversations(), conversationId] as const,
}

export const useLingoMasterSettings = () =>
  useQuery({
    queryKey: lingomasterKeys.settings(),
    queryFn: () => get<LingoMasterSettings>('v1/lingomaster/settings'),
  })

export const useUpdateLingoMasterSettings = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: LingoMasterSettingsUpdate) =>
      put<LingoMasterSettings>('v1/lingomaster/settings', { json: data }),
    onSuccess: (data) => queryClient.setQueryData(lingomasterKeys.settings(), data),
  })
}

export const useConversationTranslationSettings = (conversationId: number) =>
  useQuery({
    queryKey: lingomasterKeys.conversation(conversationId),
    queryFn: () => get<ConversationTranslationSettings>(`v1/conversations/${conversationId}/translation-settings`),
    enabled: conversationId > 0,
  })

export const useUpdateConversationTranslationSettings = (conversationId: number) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: ConversationTranslationSettingsUpdate) =>
      patch<ConversationTranslationSettings>(`v1/conversations/${conversationId}/translation-settings`, { json: data }),
    onSuccess: (data) => queryClient.setQueryData(lingomasterKeys.conversation(conversationId), data),
  })
}
