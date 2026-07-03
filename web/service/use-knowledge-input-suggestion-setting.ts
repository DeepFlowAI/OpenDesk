import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  KnowledgeInputSuggestionSetting,
  KnowledgeInputSuggestionSettingPayload,
} from '@/models/knowledge-input-suggestion-setting'

const NS = 'knowledge-input-suggestion-setting'

export const knowledgeInputSuggestionSettingKeys = {
  all: [NS] as const,
  current: () => [...knowledgeInputSuggestionSettingKeys.all, 'current'] as const,
  agent: () => [...knowledgeInputSuggestionSettingKeys.all, 'agent'] as const,
}

export const useKnowledgeInputSuggestionSetting = () =>
  useQuery({
    queryKey: knowledgeInputSuggestionSettingKeys.current(),
    queryFn: () =>
      get<KnowledgeInputSuggestionSetting>('v1/conversation-settings/knowledge-input-suggestions'),
    retry: false,
  })

export const useAgentKnowledgeInputSuggestionSetting = (enabled = true) =>
  useQuery({
    queryKey: knowledgeInputSuggestionSettingKeys.agent(),
    queryFn: () =>
      get<KnowledgeInputSuggestionSetting>('v1/conversation-settings/knowledge-input-suggestions/agent'),
    enabled,
    retry: false,
    staleTime: 0,
  })

export const useSaveKnowledgeInputSuggestionSetting = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: KnowledgeInputSuggestionSettingPayload) =>
      put<KnowledgeInputSuggestionSetting>('v1/conversation-settings/knowledge-input-suggestions', { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: knowledgeInputSuggestionSettingKeys.current() })
      qc.invalidateQueries({ queryKey: knowledgeInputSuggestionSettingKeys.agent() })
    },
  })
}
