import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  ConversationReadStatusConfig,
  ConversationReadStatusPayload,
  ConversationReadStatusTargetConfig,
} from '@/models/conversation-read-status'

const NS = 'conversation-read-status'

export const conversationReadStatusKeys = {
  all: [NS] as const,
  current: () => [...conversationReadStatusKeys.all, 'current'] as const,
  agent: () => [...conversationReadStatusKeys.all, 'agent'] as const,
}

export const useReadStatusSettings = () =>
  useQuery({
    queryKey: conversationReadStatusKeys.current(),
    queryFn: () => get<ConversationReadStatusConfig>('v1/conversation-settings/read-status'),
    retry: false,
  })

export const useSaveReadStatusSettings = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConversationReadStatusPayload) =>
      put<ConversationReadStatusConfig>('v1/conversation-settings/read-status', { json: payload }),
    onSuccess: (data) => {
      qc.setQueryData(conversationReadStatusKeys.current(), data)
      qc.setQueryData(conversationReadStatusKeys.agent(), {
        target: 'agent_workspace',
        configured: data.configured,
        enabled: data.agent_workspace_enabled,
        updated_at: data.updated_at,
      } satisfies ConversationReadStatusTargetConfig)
    },
  })
}

export const useAgentReadStatusSettings = (enabled = true) =>
  useQuery({
    queryKey: conversationReadStatusKeys.agent(),
    queryFn: () => get<ConversationReadStatusTargetConfig>('v1/conversation-settings/read-status/agent'),
    enabled,
    retry: false,
  })
