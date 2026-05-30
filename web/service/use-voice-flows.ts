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
    // The editor seeds local React state from `graph_json` on load; a
    // refetch (e.g. window focus) would otherwise overwrite the user's
    // unsaved canvas edits. Save/rollback mutations explicitly invalidate
    // this query, so a fresh fetch only happens when we actually want it.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
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

export const useValidateVoiceFlowGraph = (id: number) =>
  useMutation({
    mutationFn: async (graph_json: import('@/models/voice-flow-graph').VoiceFlowGraph) =>
      post<import('@/models/voice-flow').GraphValidationResult>(
        `v1/voice-flows/${id}/validate`,
        { json: { graph_json } },
      ),
  })

// ─────────────── Versions ───────────────

export type VoiceFlowVersionItem = {
  id: number
  version_no: number
  comment: string | null
  is_current: boolean
  created_at: string | null
  created_by_actor_name: string | null
}

export type VoiceFlowVersionListResponse = {
  items: VoiceFlowVersionItem[]
  current_version_no: number | null
}

export type VoiceFlowVersionDetail = {
  id: number
  version_no: number
  graph_json: import('@/models/voice-flow-graph').VoiceFlowGraph
  comment: string | null
  created_at: string | null
  created_by_actor_name: string | null
  is_current: boolean
}

export const useVoiceFlowVersions = (flowId: number, enabled = true) =>
  useQuery({
    queryKey: [...voiceFlowKeys.detail(flowId), 'versions'],
    queryFn: () =>
      get<VoiceFlowVersionListResponse>(`v1/voice-flows/${flowId}/versions`),
    enabled: enabled && !!flowId,
  })

export const useVoiceFlowVersion = (flowId: number, versionNo: number | null) =>
  useQuery({
    queryKey: [...voiceFlowKeys.detail(flowId), 'versions', versionNo],
    queryFn: () =>
      get<VoiceFlowVersionDetail>(
        `v1/voice-flows/${flowId}/versions/${versionNo}`,
      ),
    enabled: !!flowId && versionNo != null,
  })

export const useRollbackVoiceFlow = (flowId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (versionNo: number) =>
      post<import('@/models/voice-flow').VoiceFlow>(
        `v1/voice-flows/${flowId}/rollback/${versionNo}`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: voiceFlowKeys.detail(flowId) })
    },
  })
}
