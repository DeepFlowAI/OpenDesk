import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, patch, del } from './base'
import type {
  InboundRoutingRule,
  InboundRoutingRuleListResponse,
  SaveInboundRoutingRulePayload,
} from '@/models/inbound-routing-rule'

const NS = 'inbound-routing-rules'

export const inboundRoutingRuleKeys = {
  all: [NS] as const,
  lists: () => [...inboundRoutingRuleKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...inboundRoutingRuleKeys.lists(), params] as const,
  details: () => [...inboundRoutingRuleKeys.all, 'detail'] as const,
  detail: (id: number) => [...inboundRoutingRuleKeys.details(), id] as const,
}

export const useInboundRoutingRules = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: inboundRoutingRuleKeys.list(params ?? {}),
    queryFn: () =>
      get<InboundRoutingRuleListResponse>('v1/inbound-routing-rules', {
        searchParams: params as Record<string, string | number>,
      }),
  })

export const useInboundRoutingRule = (id: number) =>
  useQuery({
    queryKey: inboundRoutingRuleKeys.detail(id),
    queryFn: () => get<InboundRoutingRule>(`v1/inbound-routing-rules/${id}`),
    enabled: !!id,
  })

export const useCreateInboundRoutingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SaveInboundRoutingRulePayload) =>
      post<InboundRoutingRule>('v1/inbound-routing-rules', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: inboundRoutingRuleKeys.lists() }),
  })
}

export const useUpdateInboundRoutingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: SaveInboundRoutingRulePayload }) =>
      put<InboundRoutingRule>(`v1/inbound-routing-rules/${id}`, { json: data }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: inboundRoutingRuleKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: inboundRoutingRuleKeys.lists() })
    },
  })
}

export const usePatchInboundRoutingRuleEnabled = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patch<InboundRoutingRule>(`v1/inbound-routing-rules/${id}`, { json: { enabled } }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: inboundRoutingRuleKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: inboundRoutingRuleKeys.lists() })
    },
  })
}

export const useDeleteInboundRoutingRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/inbound-routing-rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: inboundRoutingRuleKeys.lists() }),
  })
}

export const useReorderInboundRoutingRules = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ordered_ids: number[]) =>
      put('v1/inbound-routing-rules/reorder', { json: { ordered_ids } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: inboundRoutingRuleKeys.lists() }),
  })
}
