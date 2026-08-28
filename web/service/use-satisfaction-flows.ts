import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from '@/service/base'
import type {
  SatisfactionFlow,
  SatisfactionFlowDraft,
  SatisfactionFlowListResponse,
  SatisfactionFlowVersionDetail,
  SatisfactionFlowVersionListResponse,
  SatisfactionGraphValidation,
} from '@/models/satisfaction-flow'

const NS = 'satisfaction-flows'

export const satisfactionFlowKeys = {
  all: [NS] as const,
  lists: () => [NS, 'list'] as const,
  list: (params: Record<string, unknown>) => [NS, 'list', params] as const,
  detail: (id: number) => [NS, 'detail', id] as const,
  versions: (id: number) => [NS, 'detail', id, 'versions'] as const,
}

export function useSatisfactionFlows(params: {
  page: number
  per_page: number
  keyword?: string
  enabled?: boolean
}) {
  return useQuery({
    queryKey: satisfactionFlowKeys.list(params),
    queryFn: () => get<SatisfactionFlowListResponse>('v1/satisfaction-flows', {
      searchParams: params as Record<string, string | number | boolean>,
    }),
  })
}

export function useSatisfactionFlow(id: number) {
  return useQuery({
    queryKey: satisfactionFlowKeys.detail(id),
    queryFn: () => get<SatisfactionFlow>(`v1/satisfaction-flows/${id}`),
    enabled: id > 0,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

function useFlowMutation<TInput>(
  mutationFn: (input: TInput) => Promise<SatisfactionFlow>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (flow) => {
      queryClient.invalidateQueries({ queryKey: satisfactionFlowKeys.lists() })
      queryClient.invalidateQueries({ queryKey: satisfactionFlowKeys.detail(flow.id) })
    },
  })
}

export function useCreateSatisfactionFlow() {
  return useFlowMutation((draft: SatisfactionFlowDraft) =>
    post<SatisfactionFlow>('v1/satisfaction-flows', { json: draft }),
  )
}

export function useSaveSatisfactionFlow() {
  return useFlowMutation(({ id, draft }: { id: number; draft: SatisfactionFlowDraft }) =>
    put<SatisfactionFlow>(`v1/satisfaction-flows/${id}`, { json: draft }),
  )
}

export function useCopySatisfactionFlow() {
  return useFlowMutation((id: number) =>
    post<SatisfactionFlow>(`v1/satisfaction-flows/${id}/copy`),
  )
}

export function useEnableSatisfactionFlow() {
  return useFlowMutation(({ id, replaceActive }: { id: number; replaceActive: boolean }) =>
    post<SatisfactionFlow>(`v1/satisfaction-flows/${id}/enable`, {
      json: { replace_active: replaceActive },
    }),
  )
}

export function useDisableSatisfactionFlow() {
  return useFlowMutation((id: number) =>
    post<SatisfactionFlow>(`v1/satisfaction-flows/${id}/disable`),
  )
}

export function useDeleteSatisfactionFlow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/satisfaction-flows/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: satisfactionFlowKeys.lists() }),
  })
}

export function useValidateSatisfactionFlow(id: number) {
  return useMutation({
    mutationFn: (draft: SatisfactionFlowDraft) =>
      post<SatisfactionGraphValidation>(`v1/satisfaction-flows/${id}/validate`, {
        json: { graph_json: draft.graph_json, settings: draft.settings },
      }),
  })
}

export function useSatisfactionFlowVersions(id: number, enabled: boolean) {
  return useQuery({
    queryKey: satisfactionFlowKeys.versions(id),
    queryFn: () => get<SatisfactionFlowVersionListResponse>(`v1/satisfaction-flows/${id}/versions`),
    enabled: enabled && id > 0,
  })
}

export function useSatisfactionFlowVersion(id: number, version: number | null) {
  return useQuery({
    queryKey: [...satisfactionFlowKeys.versions(id), version],
    queryFn: () => get<SatisfactionFlowVersionDetail>(`v1/satisfaction-flows/${id}/versions/${version}`),
    enabled: id > 0 && version !== null,
  })
}

export function useRollbackSatisfactionFlow(id: number) {
  return useFlowMutation((version: number) =>
    post<SatisfactionFlow>(`v1/satisfaction-flows/${id}/rollback/${version}`),
  )
}
