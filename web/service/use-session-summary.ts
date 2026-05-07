import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, patch, del } from './base'
import type {
  CsSummaryConfig,
  CsSummaryConfigField,
  CsSummaryConfigFieldListResponse,
  CreateCsSummaryConfigFieldPayload,
  UpdateCsSummaryConfigFieldPayload,
  CsSummaryInteractionRule,
  CsSummaryUsageResponse,
  CsSummaryFieldValue,
  UpdateCsSummaryFieldValuePayload,
  CreateCsSummaryInteractionRulePayload,
  UpdateCsSummaryInteractionRulePayload,
  SortItem,
} from '@/models/session-summary'
import type { PaginatedResponse } from '@/models/common'

const NS = 'session-summary'

export const sessionSummaryKeys = {
  all: [NS] as const,
  config: () => [...sessionSummaryKeys.all, 'config'] as const,
  fields: () => [...sessionSummaryKeys.all, 'fields'] as const,
  rules: () => [...sessionSummaryKeys.all, 'rules'] as const,
  rulesList: (params: Record<string, unknown>) => [...sessionSummaryKeys.rules(), 'list', params] as const,
  rule: (id: number) => [...sessionSummaryKeys.rules(), id] as const,
  usage: (conversationId: number | null | undefined) => [...sessionSummaryKeys.all, 'usage', conversationId] as const,
}

// ── Config ──

export const useSessionSummaryConfig = () =>
  useQuery({
    queryKey: sessionSummaryKeys.config(),
    queryFn: () => get<CsSummaryConfig>('v1/session-summary/config'),
  })

// ── Fields ──

export const useSessionSummaryFields = () =>
  useQuery({
    queryKey: sessionSummaryKeys.fields(),
    queryFn: () => get<CsSummaryConfigFieldListResponse>('v1/session-summary/config/fields'),
  })

export const useAddSessionSummaryField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCsSummaryConfigFieldPayload) =>
      post<CsSummaryConfigField>('v1/session-summary/config/fields', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.fields() }),
  })
}

export const useUpdateSessionSummaryField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateCsSummaryConfigFieldPayload }) =>
      put<CsSummaryConfigField>(`v1/session-summary/config/fields/${id}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.fields() }),
  })
}

export const useDeleteSessionSummaryField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/session-summary/config/fields/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.fields() }),
  })
}

export const useSortSessionSummaryFields = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: SortItem[]) =>
      put<void>('v1/session-summary/config/fields/sort', { json: { items } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.fields() }),
  })
}

// ── Interaction Rules ──

export const useSessionSummaryRules = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: sessionSummaryKeys.rulesList(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<CsSummaryInteractionRule>>('v1/session-summary/config/interaction-rules', {
        searchParams: params,
      }),
  })

export const useCreateSessionSummaryRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCsSummaryInteractionRulePayload) =>
      post<CsSummaryInteractionRule>('v1/session-summary/config/interaction-rules', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.rules() }),
  })
}

export const useUpdateSessionSummaryRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateCsSummaryInteractionRulePayload }) =>
      put<CsSummaryInteractionRule>(`v1/session-summary/config/interaction-rules/${id}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.rules() }),
  })
}

export const useDeleteSessionSummaryRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/session-summary/config/interaction-rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.rules() }),
  })
}

export const useSortSessionSummaryRules = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: SortItem[]) =>
      put<void>('v1/session-summary/config/interaction-rules/sort', { json: { items } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sessionSummaryKeys.rules() }),
  })
}

// ── Usage ──

export const useSessionSummaryUsage = (conversationId: number | null | undefined) =>
  useQuery({
    queryKey: sessionSummaryKeys.usage(conversationId),
    enabled: !!conversationId,
    queryFn: () => get<CsSummaryUsageResponse>(`v1/session-summary/sessions/${conversationId}`),
  })

export const useUpdateSessionSummaryFieldValue = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ conversationId, data }: { conversationId: number; data: UpdateCsSummaryFieldValuePayload }) =>
      patch<CsSummaryFieldValue>(`v1/session-summary/sessions/${conversationId}/fields`, { json: data }),
    onSuccess: (_result, variables) => {
      qc.invalidateQueries({ queryKey: sessionSummaryKeys.usage(variables.conversationId) })
    },
  })
}
