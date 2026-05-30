import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, patch, del } from './base'
import type {
  CallSummaryConfig,
  CallSummaryConfigField,
  CallSummaryConfigFieldListResponse,
  CreateCallSummaryConfigFieldPayload,
  UpdateCallSummaryConfigFieldPayload,
  CallSummaryInteractionRule,
  CallSummaryUsageResponse,
  CallSummaryFieldValue,
  UpdateCallSummaryFieldValuePayload,
  CreateCallSummaryInteractionRulePayload,
  UpdateCallSummaryInteractionRulePayload,
  SortItem,
} from '@/models/call-summary'
import type { PaginatedResponse } from '@/models/common'

const NS = 'call-summary'

export const callSummaryKeys = {
  all: [NS] as const,
  config: () => [...callSummaryKeys.all, 'config'] as const,
  fields: () => [...callSummaryKeys.all, 'fields'] as const,
  rules: () => [...callSummaryKeys.all, 'rules'] as const,
  rulesList: (params: Record<string, unknown>) => [...callSummaryKeys.rules(), 'list', params] as const,
  rule: (id: number) => [...callSummaryKeys.rules(), id] as const,
  usage: (callRecordId: number | null | undefined) => [...callSummaryKeys.all, 'usage', callRecordId] as const,
}

// ── Config ──

export const useCallSummaryConfig = () =>
  useQuery({
    queryKey: callSummaryKeys.config(),
    queryFn: () => get<CallSummaryConfig>('v1/call-summary/config'),
  })

// ── Fields ──

export const useCallSummaryFields = () =>
  useQuery({
    queryKey: callSummaryKeys.fields(),
    queryFn: () => get<CallSummaryConfigFieldListResponse>('v1/call-summary/config/fields'),
  })

export const useAddCallSummaryField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCallSummaryConfigFieldPayload) =>
      post<CallSummaryConfigField>('v1/call-summary/config/fields', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.fields() }),
  })
}

export const useUpdateCallSummaryField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateCallSummaryConfigFieldPayload }) =>
      put<CallSummaryConfigField>(`v1/call-summary/config/fields/${id}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.fields() }),
  })
}

export const useDeleteCallSummaryField = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/call-summary/config/fields/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.fields() }),
  })
}

export const useSortCallSummaryFields = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: SortItem[]) =>
      put<void>('v1/call-summary/config/fields/sort', { json: { items } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.fields() }),
  })
}

// ── Usage ──

export const useCallSummaryUsage = (callRecordId: number | null | undefined) =>
  useQuery({
    queryKey: callSummaryKeys.usage(callRecordId),
    queryFn: () => get<CallSummaryUsageResponse>(`v1/call-summary/call-records/${callRecordId}`),
    enabled: typeof callRecordId === 'number',
  })

export const useUpdateCallSummaryFieldValue = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ callRecordId, data }: { callRecordId: number; data: UpdateCallSummaryFieldValuePayload }) =>
      patch<CallSummaryFieldValue>(`v1/call-summary/call-records/${callRecordId}/fields`, { json: data }),
    onSuccess: (_data, variables) =>
      qc.invalidateQueries({ queryKey: callSummaryKeys.usage(variables.callRecordId) }),
  })
}

// ── Interaction Rules ──

export const useCallSummaryRules = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: callSummaryKeys.rulesList(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<CallSummaryInteractionRule>>('v1/call-summary/config/interaction-rules', {
        searchParams: params,
      }),
  })

export const useCreateCallSummaryRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCallSummaryInteractionRulePayload) =>
      post<CallSummaryInteractionRule>('v1/call-summary/config/interaction-rules', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.rules() }),
  })
}

export const useUpdateCallSummaryRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateCallSummaryInteractionRulePayload }) =>
      put<CallSummaryInteractionRule>(`v1/call-summary/config/interaction-rules/${id}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.rules() }),
  })
}

export const useDeleteCallSummaryRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/call-summary/config/interaction-rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.rules() }),
  })
}

export const useSortCallSummaryRules = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (items: SortItem[]) =>
      put<void>('v1/call-summary/config/interaction-rules/sort', { json: { items } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: callSummaryKeys.rules() }),
  })
}
