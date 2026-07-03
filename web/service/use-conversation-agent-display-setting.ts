import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  ConversationAgentDisplaySetting,
  ConversationAgentDisplaySettingPayload,
} from '@/models/conversation-agent-display-setting'

const NS = 'conversation-agent-display-setting'

export const conversationAgentDisplaySettingKeys = {
  all: [NS] as const,
  current: () => [...conversationAgentDisplaySettingKeys.all, 'current'] as const,
}

export const useConversationAgentDisplaySetting = () =>
  useQuery({
    queryKey: conversationAgentDisplaySettingKeys.current(),
    queryFn: () =>
      get<ConversationAgentDisplaySetting>('v1/conversation-settings/agent-display-name'),
    retry: false,
  })

export const useSaveConversationAgentDisplaySetting = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConversationAgentDisplaySettingPayload) =>
      put<ConversationAgentDisplaySetting>('v1/conversation-settings/agent-display-name', { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: conversationAgentDisplaySettingKeys.current() })
    },
  })
}
