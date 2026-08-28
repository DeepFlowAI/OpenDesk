import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  EmbeddedCallIntegration,
  EmbeddedCallIntegrationList,
  EmbeddedCallIntegrationPayload,
  EmbeddedCallIntegrationSecretResult,
} from '@/models/embedded-call'
import { del, get, patch, post } from '@/service/base'


const NS = 'embedded-call-integrations'

export const embeddedCallIntegrationKeys = {
  all: [NS] as const,
  list: () => [NS, 'list'] as const,
  detail: (id: string) => [NS, 'detail', id] as const,
}

export const useEmbeddedCallIntegrations = () =>
  useQuery({
    queryKey: embeddedCallIntegrationKeys.list(),
    queryFn: () =>
      get<EmbeddedCallIntegrationList>('v1/call-center/embedded-call-integrations'),
  })

export const useEmbeddedCallIntegration = (id: string | null) =>
  useQuery({
    queryKey: embeddedCallIntegrationKeys.detail(id ?? ''),
    queryFn: () =>
      get<EmbeddedCallIntegration>(`v1/call-center/embedded-call-integrations/${id}`),
    enabled: Boolean(id),
  })

export const useCreateEmbeddedCallIntegration = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: EmbeddedCallIntegrationPayload) =>
      post<EmbeddedCallIntegrationSecretResult>('v1/call-center/embedded-call-integrations', {
        json: data,
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(
        embeddedCallIntegrationKeys.detail(result.integration.public_id),
        result.integration,
      )
      void queryClient.invalidateQueries({ queryKey: embeddedCallIntegrationKeys.list() })
    },
  })
}

export const useUpdateEmbeddedCallIntegration = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<EmbeddedCallIntegrationPayload> }) =>
      patch<EmbeddedCallIntegration>(`v1/call-center/embedded-call-integrations/${id}`, {
        json: data,
      }),
    onSuccess: (integration) => {
      queryClient.setQueryData(
        embeddedCallIntegrationKeys.detail(integration.public_id),
        integration,
      )
      void queryClient.invalidateQueries({ queryKey: embeddedCallIntegrationKeys.list() })
    },
  })
}

export const useRotateEmbeddedCallSecret = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, gracePeriodHours = 24 }: { id: string; gracePeriodHours?: number }) =>
      post<EmbeddedCallIntegrationSecretResult>(
        `v1/call-center/embedded-call-integrations/${id}/rotate-secret`,
        { json: { grace_period_hours: gracePeriodHours } },
      ),
    onSuccess: (result) => {
      queryClient.setQueryData(
        embeddedCallIntegrationKeys.detail(result.integration.public_id),
        result.integration,
      )
      void queryClient.invalidateQueries({ queryKey: embeddedCallIntegrationKeys.list() })
    },
  })
}

export const useRevokePreviousEmbeddedCallSecret = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      del<EmbeddedCallIntegration>(
        `v1/call-center/embedded-call-integrations/${id}/previous-secret`,
      ),
    onSuccess: (integration) => {
      queryClient.setQueryData(
        embeddedCallIntegrationKeys.detail(integration.public_id),
        integration,
      )
    },
  })
}

export const useDeleteEmbeddedCallIntegration = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del(`v1/call-center/embedded-call-integrations/${id}`),
    onSuccess: (_result, id) => {
      queryClient.removeQueries({ queryKey: embeddedCallIntegrationKeys.detail(id) })
      void queryClient.invalidateQueries({ queryKey: embeddedCallIntegrationKeys.list() })
    },
  })
}
