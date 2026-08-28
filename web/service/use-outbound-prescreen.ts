import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  OutboundPrescreenConfig,
  OutboundPrescreenConfigDraft,
  OutboundPrescreenDecision,
  OutboundPrescreenTestPayload,
} from '@/models/outbound-prescreen'
import { get, post, put } from '@/service/base'

const configKey = ['outbound-prescreen', 'config'] as const

export const useOutboundPrescreenConfig = () =>
  useQuery({
    queryKey: configKey,
    queryFn: () => get<OutboundPrescreenConfig>('v1/call-center/outbound-prescreen-intents'),
  })

export const useSaveOutboundPrescreenConfig = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: OutboundPrescreenConfigDraft) =>
      put<OutboundPrescreenConfig>('v1/call-center/outbound-prescreen-intents', { json: data }),
    onSuccess: (data) => queryClient.setQueryData(configKey, data),
  })
}

export const useTestOutboundPrescreen = () =>
  useMutation({
    mutationFn: (data: OutboundPrescreenTestPayload) =>
      post<OutboundPrescreenDecision>('v1/call-center/outbound-prescreen-intents/test', { json: data }),
  })
