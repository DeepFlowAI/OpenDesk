import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type { MessageResponse } from '@/models/scheduling'
import {
  normalizeTargets,
  type RuleSet,
  type RuleSetListResponse,
  type RuleSetPayload,
} from '@/models/scheduling-rule'

const NS = 'scheduling-rules'

export const schedulingRuleKeys = {
  all: [NS] as const,
  lists: () => [...schedulingRuleKeys.all, 'list'] as const,
  details: () => [...schedulingRuleKeys.all, 'detail'] as const,
  detail: (id: number) => [...schedulingRuleKeys.details(), id] as const,
}

function normalizeRuleSet(ruleSet: RuleSet): RuleSet {
  return {
    ...ruleSet,
    targets_enabled: ruleSet.targets_enabled !== false,
    targets: normalizeTargets(ruleSet.targets as unknown as Record<string, unknown>),
  }
}

export function useRuleSets(enabled = true) {
  return useQuery({
    queryKey: schedulingRuleKeys.lists(),
    queryFn: async () => {
      const data = await get<RuleSetListResponse>('v1/scheduling/rule-sets')
      return { items: data.items.map(normalizeRuleSet) }
    },
    enabled,
  })
}

export function useRuleSet(id: number) {
  return useQuery({
    queryKey: schedulingRuleKeys.detail(id),
    queryFn: async () => normalizeRuleSet(await get<RuleSet>(`v1/scheduling/rule-sets/${id}`)),
    enabled: Number.isFinite(id) && id > 0,
  })
}

function useInvalidateRuleSets() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: schedulingRuleKeys.all })
}

export function useCreateRuleSet() {
  const invalidate = useInvalidateRuleSets()
  return useMutation({
    mutationFn: async (payload: RuleSetPayload) =>
      normalizeRuleSet(await post<RuleSet>('v1/scheduling/rule-sets', { json: payload })),
    onSuccess: invalidate,
  })
}

export function useUpdateRuleSet() {
  const invalidate = useInvalidateRuleSets()
  return useMutation({
    mutationFn: async ({ id, ...payload }: RuleSetPayload & { id: number }) =>
      normalizeRuleSet(await put<RuleSet>(`v1/scheduling/rule-sets/${id}`, { json: payload })),
    onSuccess: invalidate,
  })
}

export function useDeleteRuleSet() {
  const invalidate = useInvalidateRuleSets()
  return useMutation({
    mutationFn: (id: number) => del<MessageResponse>(`v1/scheduling/rule-sets/${id}`),
    onSuccess: invalidate,
  })
}

export function useCopyRuleSet() {
  const invalidate = useInvalidateRuleSets()
  return useMutation({
    mutationFn: async (id: number) =>
      normalizeRuleSet(await post<RuleSet>(`v1/scheduling/rule-sets/${id}/copy`)),
    onSuccess: invalidate,
  })
}

export function useSetDefaultRuleSet() {
  const invalidate = useInvalidateRuleSets()
  return useMutation({
    mutationFn: async (id: number) =>
      normalizeRuleSet(await post<RuleSet>(`v1/scheduling/rule-sets/${id}/set-default`)),
    onSuccess: invalidate,
  })
}
