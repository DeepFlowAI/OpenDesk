import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, patch, del } from './base'
import type {
  SessionRoutingRule,
  SessionRoutingRuleListResponse,
  SaveSessionRoutingRulePayload,
} from '@/models/session-routing-rule'

const NS = 'session-routing-rules'

export const sessionRoutingRuleKeys = {
  all: [NS] as const,
  lists: () => [...sessionRoutingRuleKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...sessionRoutingRuleKeys.lists(), params] as const,
  details: () => [...sessionRoutingRuleKeys.all, 'detail'] as const,
  detail: (id: number) => [...sessionRoutingRuleKeys.details(), id] as const,
}

export const useSessionRoutingRules = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: sessionRoutingRuleKeys.list(params ?? {}),
    queryFn: () =>
      get<SessionRoutingRuleListResponse>('v1/session-routing-rules', {
        searchParams: params as Record<string, string | number>,
      }),
  })

export const useSessionRoutingRule = (id: number) =>
  useQuery({
    queryKey: sessionRoutingRuleKeys.detail(id),
    queryFn: () => get<SessionRoutingRule>(`v1/session-routing-rules/${id}`),
    enabled: !!id,
  })

export const useCreateSessionRoutingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SaveSessionRoutingRulePayload) =>
      post<SessionRoutingRule>('v1/session-routing-rules', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionRoutingRuleKeys.lists() }),
  })
}

export const useUpdateSessionRoutingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: SaveSessionRoutingRulePayload }) =>
      put<SessionRoutingRule>(`v1/session-routing-rules/${id}`, { json: data }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: sessionRoutingRuleKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: sessionRoutingRuleKeys.lists() })
    },
  })
}

export const usePatchSessionRoutingRuleEnabled = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patch<SessionRoutingRule>(`v1/session-routing-rules/${id}`, { json: { enabled } }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: sessionRoutingRuleKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: sessionRoutingRuleKeys.lists() })
    },
  })
}

export const useDeleteSessionRoutingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/session-routing-rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionRoutingRuleKeys.lists() }),
  })
}

export const useReorderSessionRoutingRules = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ordered_ids: number[]) =>
      put('v1/session-routing-rules/reorder', { json: { ordered_ids } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionRoutingRuleKeys.lists() }),
  })
}
