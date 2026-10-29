import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from '@/service/base'
import type {
  CallEventRule,
  CallEventRuleList,
  CallEventRuleListParams,
  CallEventRuleOptions,
  CallEventRulePayload,
} from '@/models/call-event-subscription'

const NS = 'call-event-subscription-rules'
const BASE = 'v1/call-center/event-subscription-rules'

export const callEventRuleKeys = {
  all: [NS] as const,
  lists: () => [NS, 'list'] as const,
  list: (params: CallEventRuleListParams) => [NS, 'list', params] as const,
  detail: (id: string) => [NS, 'detail', id] as const,
  options: (ruleId: string | null) => [NS, 'options', ruleId ?? ''] as const,
}

export function useCallEventRules(params: CallEventRuleListParams) {
  return useQuery({
    queryKey: callEventRuleKeys.list(params),
    queryFn: () => get<CallEventRuleList>(BASE, { searchParams: params }),
    placeholderData: keepPreviousData,
  })
}

export function useCallEventRule(id: string | null) {
  return useQuery({
    queryKey: callEventRuleKeys.detail(id ?? ''),
    queryFn: () => get<CallEventRule>(`${BASE}/${id}`),
    enabled: Boolean(id),
    retry: false,
  })
}

export function useCallEventRuleOptions(ruleId: string | null) {
  return useQuery({
    queryKey: callEventRuleKeys.options(ruleId),
    queryFn: () =>
      get<CallEventRuleOptions>(`${BASE}/options`, {
        searchParams: ruleId ? { rule_id: ruleId } : {},
      }),
  })
}

function useInvalidateCallEventRules() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: callEventRuleKeys.all })
}

export function useCreateCallEventRule() {
  const invalidate = useInvalidateCallEventRules()
  return useMutation({
    mutationFn: (data: CallEventRulePayload) => post<CallEventRule>(BASE, { json: data }),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateCallEventRule() {
  const invalidate = useInvalidateCallEventRules()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CallEventRulePayload }) =>
      put<CallEventRule>(`${BASE}/${id}`, { json: data }),
    onSuccess: () => invalidate(),
  })
}

export function useToggleCallEventRule() {
  const invalidate = useInvalidateCallEventRules()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      post<CallEventRule>(`${BASE}/${id}/${enabled ? 'enable' : 'disable'}`),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteCallEventRule() {
  const invalidate = useInvalidateCallEventRules()
  return useMutation({
    mutationFn: (id: string) => del(`${BASE}/${id}`),
    onSuccess: () => invalidate(),
  })
}
