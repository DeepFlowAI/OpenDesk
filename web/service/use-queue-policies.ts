import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  QueuePolicy,
  QueuePolicyListParams,
  QueuePolicyListResponse,
  QueuePolicyUpsertPayload,
} from '@/models/queue-policy'

const NS = 'queue-policies'

export const queuePolicyKeys = {
  all: [NS] as const,
  lists: () => [...queuePolicyKeys.all, 'list'] as const,
  list: (params: QueuePolicyListParams) => [...queuePolicyKeys.lists(), params] as const,
}

function queuePolicySearchParams(params: QueuePolicyListParams): URLSearchParams {
  const sp = new URLSearchParams()
  if (params.channel) sp.set('channel', params.channel)
  if (params.scope_type) sp.set('scope_type', params.scope_type)
  if (params.scope_id != null) sp.set('scope_id', String(params.scope_id))
  return sp
}

type UseQueuePoliciesOptions = Pick<UseQueryOptions<QueuePolicyListResponse>, 'enabled'>

export const useQueuePolicies = (
  params: QueuePolicyListParams = {},
  options?: UseQueuePoliciesOptions
) =>
  useQuery({
    queryKey: queuePolicyKeys.list(params),
    queryFn: () =>
      get<QueuePolicyListResponse>('v1/queue/policies', {
        searchParams: queuePolicySearchParams(params),
      }),
    enabled: options?.enabled ?? true,
  })

export const useUpsertQueuePolicy = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: QueuePolicyUpsertPayload) =>
      put<QueuePolicy>('v1/queue/policies', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queuePolicyKeys.all })
    },
  })
}
