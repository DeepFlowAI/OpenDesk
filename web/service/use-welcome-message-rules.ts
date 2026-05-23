import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post, put } from './base'
import type {
  SaveWelcomeMessageRulePayload,
  WelcomeMessageRule,
  WelcomeMessageRuleListResponse,
} from '@/models/welcome-message-rule'

const NS = 'welcome-message-rules'

export const welcomeMessageRuleKeys = {
  all: [NS] as const,
  lists: () => [...welcomeMessageRuleKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...welcomeMessageRuleKeys.lists(), params] as const,
  details: () => [...welcomeMessageRuleKeys.all, 'detail'] as const,
  detail: (id: number) => [...welcomeMessageRuleKeys.details(), id] as const,
}

export const useWelcomeMessageRules = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: welcomeMessageRuleKeys.list(params ?? {}),
    queryFn: () =>
      get<WelcomeMessageRuleListResponse>('v1/conversation-settings/welcome-rules', {
        searchParams: params as Record<string, string | number>,
      }),
  })

export const useWelcomeMessageRule = (id: number) =>
  useQuery({
    queryKey: welcomeMessageRuleKeys.detail(id),
    queryFn: () => get<WelcomeMessageRule>(`v1/conversation-settings/welcome-rules/${id}`),
    enabled: !!id,
  })

export const useCreateWelcomeMessageRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SaveWelcomeMessageRulePayload) =>
      post<WelcomeMessageRule>('v1/conversation-settings/welcome-rules', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: welcomeMessageRuleKeys.lists() }),
  })
}

export const useUpdateWelcomeMessageRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: SaveWelcomeMessageRulePayload }) =>
      put<WelcomeMessageRule>(`v1/conversation-settings/welcome-rules/${id}`, { json: data }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: welcomeMessageRuleKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: welcomeMessageRuleKeys.lists() })
    },
  })
}

export const usePatchWelcomeMessageRuleEnabled = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patch<WelcomeMessageRule>(`v1/conversation-settings/welcome-rules/${id}`, { json: { enabled } }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: welcomeMessageRuleKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: welcomeMessageRuleKeys.lists() })
    },
  })
}

export const useDeleteWelcomeMessageRule = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/conversation-settings/welcome-rules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: welcomeMessageRuleKeys.lists() }),
  })
}

export const useReorderWelcomeMessageRules = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ordered_ids: number[]) =>
      put('v1/conversation-settings/welcome-rules/reorder', { json: { ordered_ids } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: welcomeMessageRuleKeys.lists() }),
  })
}
