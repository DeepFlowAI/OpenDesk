import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './base'
import type {
  QueueAssignableAgentListResponse,
  QueueAssignmentWorkspaceResponse,
  QueueWorkspaceCountResponse,
  QueueWorkspaceTask,
  QueueWorkspaceTaskDetail,
  QueueWorkspaceTaskListResponse,
} from '@/models/queue-workspace'
import { agentKeys, conversationKeys } from '@/service/use-conversations'

const NS = 'workspace-queue'

export const queueWorkspaceKeys = {
  all: [NS] as const,
  lists: () => [...queueWorkspaceKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...queueWorkspaceKeys.lists(), params] as const,
  counts: () => [...queueWorkspaceKeys.all, 'count'] as const,
  count: (params: Record<string, unknown>) => [...queueWorkspaceKeys.counts(), params] as const,
  detail: (id: number | null) => [...queueWorkspaceKeys.all, 'detail', id] as const,
  assignableAgents: (q: string) => [...queueWorkspaceKeys.all, 'assignable-agents', q] as const,
}

export const getNextQueueTaskId = (
  items: QueueWorkspaceTask[],
  currentId: number,
): number | null => {
  const index = items.findIndex((item) => item.id === currentId)
  if (index < 0) return items[0]?.id ?? null
  if (index + 1 < items.length) return items[index + 1].id
  return null
}

export const useQueueTasks = (
  options?: {
    enabled?: boolean
    queueType?: string | null
    queueId?: number | null
  },
) => {
  const params = {
    ...(options?.queueType && options.queueId ? { queue_type: options.queueType, queue_id: options.queueId } : {}),
  }
  return useQuery({
    queryKey: queueWorkspaceKeys.list(params),
    queryFn: () => get<QueueWorkspaceTaskListResponse>('v1/workspace/queue/tasks', { searchParams: params }),
    enabled: options?.enabled,
    refetchInterval: options?.enabled ? 30000 : false,
  })
}

export const useQueueTaskCount = (
  options?: {
    enabled?: boolean
    queueType?: string | null
    queueId?: number | null
  },
) => {
  const enabled = options?.enabled ?? true
  const params = {
    ...(options?.queueType && options.queueId ? { queue_type: options.queueType, queue_id: options.queueId } : {}),
  }
  return useQuery({
    queryKey: queueWorkspaceKeys.count(params),
    queryFn: () => get<QueueWorkspaceCountResponse>('v1/workspace/queue/tasks/count', { searchParams: params }),
    enabled,
    refetchInterval: enabled ? 30000 : false,
  })
}

export const useQueueTask = (taskId: number | null, enabled = true) =>
  useQuery({
    queryKey: queueWorkspaceKeys.detail(taskId),
    queryFn: () => get<QueueWorkspaceTaskDetail>(`v1/workspace/queue/tasks/${taskId}`),
    enabled: enabled && taskId !== null,
  })

export const useAssignableAgents = (q: string, enabled: boolean) =>
  useQuery({
    queryKey: queueWorkspaceKeys.assignableAgents(q),
    queryFn: () =>
      get<QueueAssignableAgentListResponse>('v1/workspace/queue/assignable-agents', {
        searchParams: q ? { q } : undefined,
      }),
    enabled,
  })

export const useAssignQueueTaskToSelf = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, reason }: { taskId: number; reason?: string }) =>
      post<QueueAssignmentWorkspaceResponse>(`v1/workspace/queue/tasks/${taskId}/assign-self`, {
        json: { reason: reason || undefined },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: agentKeys.stats })
    },
  })
}

export const useAssignQueueTaskToAgent = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, agentId, reason }: { taskId: number; agentId: number; reason?: string }) =>
      post<QueueAssignmentWorkspaceResponse>(`v1/workspace/queue/tasks/${taskId}/assign`, {
        json: { agent_id: agentId, reason: reason || undefined },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
      qc.invalidateQueries({ queryKey: conversationKeys.lists() })
      qc.invalidateQueries({ queryKey: agentKeys.stats })
    },
  })
}
