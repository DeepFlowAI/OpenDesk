import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post } from './base'
import type { ApiKeyRecord, ApiKeySecretResponse, CreateApiKeyPayload } from '@/models/api-key'

const NS = 'api-keys'

export const apiKeyKeys = {
  all: [NS] as const,
  lists: () => [...apiKeyKeys.all, 'list'] as const,
}

export const useApiKeys = () =>
  useQuery({
    queryKey: apiKeyKeys.lists(),
    queryFn: () => get<ApiKeyRecord[]>('v1/api-keys'),
  })

export const useCreateApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateApiKeyPayload) => post<ApiKeySecretResponse>('v1/api-keys', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.lists() }),
  })
}

export const useDisableApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<ApiKeyRecord>(`v1/api-keys/${id}/disable`),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.lists() }),
  })
}

export const useEnableApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<ApiKeyRecord>(`v1/api-keys/${id}/enable`),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.lists() }),
  })
}

export const useRotateApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<ApiKeySecretResponse>(`v1/api-keys/${id}/rotate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.lists() }),
  })
}

export const useDeleteApiKey = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/api-keys/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: apiKeyKeys.lists() }),
  })
}
