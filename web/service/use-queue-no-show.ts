import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type { QueueNoShowSetting } from '@/models/queue-no-show'

const NS = 'queue-no-show'

export const queueNoShowKeys = {
  all: [NS] as const,
  current: () => [...queueNoShowKeys.all, 'current'] as const,
}

export const useQueueNoShowSetting = () =>
  useQuery({
    queryKey: queueNoShowKeys.current(),
    queryFn: () => get<QueueNoShowSetting>('v1/conversation-settings/queue-no-show'),
    retry: false,
  })

export const useSaveQueueNoShowSetting = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) =>
      put<QueueNoShowSetting>('v1/conversation-settings/queue-no-show', { json: { enabled } }),
    onSuccess: (data) => {
      qc.setQueryData(queueNoShowKeys.current(), data)
    },
  })
}
