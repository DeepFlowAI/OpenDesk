import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  VisitorTimeoutCloseConfig,
  VisitorTimeoutClosePayload,
} from '@/models/visitor-timeout-close'

const NS = 'visitor-timeout-close'

export const visitorTimeoutCloseKeys = {
  all: [NS] as const,
  current: () => [...visitorTimeoutCloseKeys.all, 'current'] as const,
}

export const useVisitorTimeoutCloseSettings = () =>
  useQuery({
    queryKey: visitorTimeoutCloseKeys.current(),
    queryFn: () => get<VisitorTimeoutCloseConfig>('v1/conversation-settings/visitor-timeout-close'),
    retry: false,
  })

export const useSaveVisitorTimeoutCloseSettings = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: VisitorTimeoutClosePayload) =>
      put<VisitorTimeoutCloseConfig>('v1/conversation-settings/visitor-timeout-close', { json: payload }),
    onSuccess: (data) => {
      qc.setQueryData(visitorTimeoutCloseKeys.current(), data)
    },
  })
}
