import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from '@/service/base'
import type {
  EventSubscription,
  EventSubscriptionList,
  EventSubscriptionListParams,
  EventSubscriptionPayload,
  EventSubscriptionSecretResponse,
  EventSubscriptionTestResult,
} from '@/models/event-subscription'

const NS = 'event-subscriptions'

export const eventSubscriptionKeys = {
  all: [NS] as const,
  lists: () => [NS, 'list'] as const,
  list: (params: EventSubscriptionListParams) => [NS, 'list', params] as const,
  details: () => [NS, 'detail'] as const,
  detail: (id: string) => [NS, 'detail', id] as const,
}

export function useEventSubscriptions(params: EventSubscriptionListParams) {
  return useQuery({
    queryKey: eventSubscriptionKeys.list(params),
    queryFn: () => get<EventSubscriptionList>('v1/event-subscriptions', { searchParams: params }),
  })
}

export function useEventSubscription(id: string | null) {
  return useQuery({
    queryKey: eventSubscriptionKeys.detail(id ?? ''),
    queryFn: () => get<EventSubscription>(`v1/event-subscriptions/${id}`),
    enabled: Boolean(id),
  })
}

function useInvalidateEventSubscriptions() {
  const queryClient = useQueryClient()
  return async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: eventSubscriptionKeys.lists() })
    if (id) await queryClient.invalidateQueries({ queryKey: eventSubscriptionKeys.detail(id) })
  }
}

export function useCreateEventSubscription() {
  const invalidate = useInvalidateEventSubscriptions()
  return useMutation({
    mutationFn: (data: EventSubscriptionPayload) =>
      post<EventSubscriptionSecretResponse>('v1/event-subscriptions', { json: data }),
    onSuccess: (result) => invalidate(result.record.public_id),
  })
}

export function useUpdateEventSubscription() {
  const invalidate = useInvalidateEventSubscriptions()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: EventSubscriptionPayload }) =>
      put<EventSubscription>(`v1/event-subscriptions/${id}`, { json: data }),
    onSuccess: (result) => invalidate(result.public_id),
  })
}

function useSubscriptionAction(path: 'enable' | 'disable') {
  const invalidate = useInvalidateEventSubscriptions()
  return useMutation({
    mutationFn: (id: string) => post<EventSubscription>(`v1/event-subscriptions/${id}/${path}`),
    onSuccess: (result) => invalidate(result.public_id),
  })
}

export const useEnableEventSubscription = () => useSubscriptionAction('enable')
export const useDisableEventSubscription = () => useSubscriptionAction('disable')

export function useRotateEventSubscriptionSecret() {
  const invalidate = useInvalidateEventSubscriptions()
  return useMutation({
    mutationFn: (id: string) =>
      post<EventSubscriptionSecretResponse>(`v1/event-subscriptions/${id}/rotate-secret`),
    onSuccess: (result) => invalidate(result.record.public_id),
  })
}

export function useDeleteEventSubscription() {
  const invalidate = useInvalidateEventSubscriptions()
  return useMutation({
    mutationFn: (id: string) => del(`v1/event-subscriptions/${id}`),
    onSuccess: () => invalidate(),
  })
}

export function useTestEventSubscription() {
  const invalidate = useInvalidateEventSubscriptions()
  return useMutation({
    mutationFn: (id: string) =>
      post<EventSubscriptionTestResult>(`v1/event-subscriptions/${id}/test`, { timeout: 10000 }),
    onSuccess: (_result, id) => invalidate(id),
  })
}
