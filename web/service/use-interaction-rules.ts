import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type { PaginatedResponse } from '@/models/common'
import type {
  FdInteractionRule,
  CreateFdInteractionRulePayload,
  UpdateFdInteractionRulePayload,
  InteractionRuleSortPayload,
} from '@/models/interaction-rule'

const NS = 'interaction-rules'

export const interactionRuleKeys = {
  all: [NS] as const,
  lists: () => [...interactionRuleKeys.all, 'list'] as const,
  list: (layoutId: number) => [...interactionRuleKeys.lists(), layoutId] as const,
  details: () => [...interactionRuleKeys.all, 'detail'] as const,
  detail: (id: number) => [...interactionRuleKeys.details(), id] as const,
}

export const useInteractionRules = (layoutId: number) =>
  useQuery({
    queryKey: interactionRuleKeys.list(layoutId),
    queryFn: () =>
      get<PaginatedResponse<FdInteractionRule>>(
        `v1/form-layouts/${layoutId}/interaction-rules`,
      ),
    enabled: !!layoutId,
  })

export const useInteractionRule = (layoutId: number, ruleId: number) =>
  useQuery({
    queryKey: interactionRuleKeys.detail(ruleId),
    queryFn: () =>
      get<FdInteractionRule>(`v1/form-layouts/${layoutId}/interaction-rules/${ruleId}`),
    enabled: !!layoutId && !!ruleId,
  })

export const useCreateInteractionRule = (layoutId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateFdInteractionRulePayload) =>
      post<FdInteractionRule>(`v1/form-layouts/${layoutId}/interaction-rules`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: interactionRuleKeys.list(layoutId) }),
  })
}

export const useUpdateInteractionRule = (layoutId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateFdInteractionRulePayload }) =>
      put<FdInteractionRule>(`v1/form-layouts/${layoutId}/interaction-rules/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: interactionRuleKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: interactionRuleKeys.list(layoutId) })
    },
  })
}

export const useDeleteInteractionRule = (layoutId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      del(`v1/form-layouts/${layoutId}/interaction-rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: interactionRuleKeys.list(layoutId) }),
  })
}

export const useSortInteractionRules = (layoutId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: InteractionRuleSortPayload) =>
      put(`v1/form-layouts/${layoutId}/interaction-rules/sort`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: interactionRuleKeys.list(layoutId) }),
  })
}
