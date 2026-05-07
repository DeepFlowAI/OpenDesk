import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  VoiceFlow,
  VoiceFlowListResponse,
  VoiceFlowSelectResponse,
  CreateVoiceFlowPayload,
  UpdateVoiceFlowPayload,
} from '@/models/voice-flow'

const NS = 'voice-flows'

export const voiceFlowKeys = {
  all: [NS] as const,
  lists: () => [...voiceFlowKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...voiceFlowKeys.lists(), params] as const,
  select: () => [...voiceFlowKeys.all, 'select'] as const,
  details: () => [...voiceFlowKeys.all, 'detail'] as const,
  detail: (id: number) => [...voiceFlowKeys.details(), id] as const,
}

export const useVoiceFlows = (params?: {
  page?: number
  per_page?: number
  keyword?: string
  include_deleted?: boolean
}) =>
  useQuery({
    queryKey: voiceFlowKeys.list(params ?? {}),
    queryFn: () =>
      get<VoiceFlowListResponse>('v1/voice-flows', {
        searchParams: params as Record<string, string | number | boolean>,
      }),
  })

export const useVoiceFlowsSelect = () =>
  useQuery({
    queryKey: voiceFlowKeys.select(),
    queryFn: () => get<VoiceFlowSelectResponse>('v1/voice-flows/select'),
  })

export const useVoiceFlow = (id: number) =>
  useQuery({
    queryKey: voiceFlowKeys.detail(id),
    queryFn: () => get<VoiceFlow>(`v1/voice-flows/${id}`),
    enabled: !!id,
  })

export const useCreateVoiceFlow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateVoiceFlowPayload) =>
      post<VoiceFlow>('v1/voice-flows', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceFlowKeys.lists() })
      qc.invalidateQueries({ queryKey: voiceFlowKeys.select() })
    },
  })
}

export const useUpdateVoiceFlow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateVoiceFlowPayload }) =>
      put<VoiceFlow>(`v1/voice-flows/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: voiceFlowKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: voiceFlowKeys.lists() })
      qc.invalidateQueries({ queryKey: voiceFlowKeys.select() })
    },
  })
}

export const useDeleteVoiceFlow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/voice-flows/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceFlowKeys.lists() })
      qc.invalidateQueries({ queryKey: voiceFlowKeys.select() })
    },
  })
}
