import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './base'
import type {
  OpenAgentAgentListResponse,
  OpenAgentSettings,
  TestOpenAgentConnectionPayload,
  TestOpenAgentConnectionResponse,
  UpdateOpenAgentSettingsPayload,
} from '@/models/open-agent-settings'

const NS = 'open-agent-settings'

export const openAgentSettingsKeys = {
  all: [NS] as const,
  detail: () => [...openAgentSettingsKeys.all, 'detail'] as const,
  agents: () => [...openAgentSettingsKeys.all, 'agents'] as const,
}

export const useOpenAgentSettings = () =>
  useQuery({
    queryKey: openAgentSettingsKeys.detail(),
    queryFn: () => get<OpenAgentSettings>('v1/open-agent-settings'),
  })

export const useUpdateOpenAgentSettings = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UpdateOpenAgentSettingsPayload) =>
      put<OpenAgentSettings>('v1/open-agent-settings', { json: data }),
    onSuccess: (data) => {
      qc.setQueryData(openAgentSettingsKeys.detail(), data)
    },
  })
}

export const useTestOpenAgentConnection = () =>
  useMutation({
    mutationFn: (data: TestOpenAgentConnectionPayload) =>
      post<TestOpenAgentConnectionResponse>('v1/open-agent-settings/test', { json: data }),
  })

export const useOpenAgentAgents = (enabled = true) =>
  useQuery({
    queryKey: openAgentSettingsKeys.agents(),
    queryFn: () => get<OpenAgentAgentListResponse>('v1/open-agent-settings/agents'),
    enabled,
    retry: false,
  })
