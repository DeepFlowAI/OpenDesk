import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, postForm, put } from './base'
import type {
  AutoOutboundAgentContext,
  AutoOutboundMonitorResponse,
  AutoOutboundRecord,
  AutoOutboundRecordListResponse,
  AutoOutboundTarget,
  AutoOutboundTargetImportResponse,
  AutoOutboundTargetListResponse,
  AutoOutboundTask,
  AutoOutboundTaskListResponse,
  AutoOutboundTaskStatsResponse,
  AutoOutboundWrapupPayload,
  AutoOutboundEventSubscription,
  CreateAutoOutboundTargetPayload,
  CreateAutoOutboundTaskPayload,
  UpdateAutoOutboundTaskPayload,
  SaveAutoOutboundEventSubscriptionPayload,
} from '@/models/auto-outbound-task'

const NS = 'auto-outbound-tasks'

type ListParams = Record<string, string | number | boolean | null | undefined>

function searchParams(params?: ListParams): URLSearchParams {
  const sp = new URLSearchParams()
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    sp.set(key, String(value))
  })
  return sp
}

export const autoOutboundTaskKeys = {
  all: [NS] as const,
  tasks: (params?: ListParams) => [...autoOutboundTaskKeys.all, 'tasks', params ?? {}] as const,
  task: (id: number) => [...autoOutboundTaskKeys.all, 'task', id] as const,
  targets: (taskId: number, params?: ListParams) =>
    [...autoOutboundTaskKeys.task(taskId), 'targets', params ?? {}] as const,
  records: (taskId: number, params?: ListParams) =>
    [...autoOutboundTaskKeys.task(taskId), 'records', params ?? {}] as const,
  agentContext: (taskId: number, params?: ListParams) =>
    [...autoOutboundTaskKeys.task(taskId), 'agent-context', params ?? {}] as const,
  stats: (taskId: number) => [...autoOutboundTaskKeys.task(taskId), 'stats'] as const,
  monitor: (taskId: number) => [...autoOutboundTaskKeys.task(taskId), 'monitor'] as const,
  eventSubscription: (taskId: number) =>
    [...autoOutboundTaskKeys.task(taskId), 'event-subscription'] as const,
}

export const useAutoOutboundTasks = (params?: ListParams) =>
  useQuery({
    queryKey: autoOutboundTaskKeys.tasks(params),
    queryFn: () =>
      get<AutoOutboundTaskListResponse>('v1/engagement/auto-outbound-tasks', {
        searchParams: searchParams(params),
      }),
  })

export const useAutoOutboundTask = (id: number, enabled = true) =>
  useQuery({
    queryKey: autoOutboundTaskKeys.task(id),
    queryFn: () => get<AutoOutboundTask>(`v1/engagement/auto-outbound-tasks/${id}`),
    enabled: enabled && Number.isFinite(id) && id > 0,
  })

export const useAutoOutboundEventSubscription = (taskId: number) =>
  useQuery({
    queryKey: autoOutboundTaskKeys.eventSubscription(taskId),
    queryFn: () =>
      get<AutoOutboundEventSubscription>(
        `v1/engagement/auto-outbound-tasks/${taskId}/event-subscription`,
      ),
    enabled: Number.isFinite(taskId) && taskId > 0,
  })

export const useSaveAutoOutboundEventSubscription = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SaveAutoOutboundEventSubscriptionPayload) =>
      put<AutoOutboundEventSubscription>(
        `v1/engagement/auto-outbound-tasks/${taskId}/event-subscription`,
        { json: data },
      ),
    onSuccess: (data) => {
      qc.setQueryData(autoOutboundTaskKeys.eventSubscription(taskId), data)
    },
  })
}

export const useCreateAutoOutboundTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAutoOutboundTaskPayload) =>
      post<AutoOutboundTask>('v1/engagement/auto-outbound-tasks', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.all }),
  })
}

export const useUpdateAutoOutboundTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateAutoOutboundTaskPayload }) =>
      put<AutoOutboundTask>(`v1/engagement/auto-outbound-tasks/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.task(v.id) })
      qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.all })
    },
  })
}

export const useTransitionAutoOutboundTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: number
      action: 'start' | 'pause' | 'resume' | 'archive'
    }) => post<AutoOutboundTask>(`v1/engagement/auto-outbound-tasks/${id}/${action}`),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.task(v.id) })
      qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.all })
    },
  })
}

export const useDeleteAutoOutboundTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/engagement/auto-outbound-tasks/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.all }),
  })
}

export const useAutoOutboundTargets = (taskId: number, params?: ListParams) =>
  useQuery({
    queryKey: autoOutboundTaskKeys.targets(taskId, params),
    queryFn: () =>
      get<AutoOutboundTargetListResponse>(`v1/engagement/auto-outbound-tasks/${taskId}/targets`, {
        searchParams: searchParams(params),
      }),
    enabled: Number.isFinite(taskId) && taskId > 0,
  })

export const useCreateAutoOutboundTarget = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateAutoOutboundTargetPayload) =>
      post<AutoOutboundTarget>(`v1/engagement/auto-outbound-tasks/${taskId}/targets`, { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.task(taskId) })
      qc.invalidateQueries({ queryKey: [...autoOutboundTaskKeys.task(taskId), 'targets'] })
    },
  })
}

export const useImportAutoOutboundTargets = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return postForm<AutoOutboundTargetImportResponse>(
        `v1/engagement/auto-outbound-tasks/${taskId}/targets/import`,
        formData,
        120000,
      )
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.task(taskId) })
      qc.invalidateQueries({ queryKey: [...autoOutboundTaskKeys.task(taskId), 'targets'] })
    },
  })
}

export const useMarkAutoOutboundTargetInvalid = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      post<AutoOutboundTarget>(`v1/engagement/auto-outbound-targets/${id}/mark-invalid`),
    onSuccess: () => qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.all }),
  })
}

export const useDeleteAutoOutboundTarget = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/engagement/auto-outbound-targets/${id}`),
    onSettled: () => qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.all }),
  })
}

export const useAutoOutboundRecords = (
  taskId: number,
  params?: ListParams,
  enabled = true,
) =>
  useQuery({
    queryKey: autoOutboundTaskKeys.records(taskId, params),
    queryFn: () =>
      get<AutoOutboundRecordListResponse>(`v1/engagement/auto-outbound-tasks/${taskId}/records`, {
        searchParams: searchParams(params),
      }),
    enabled: enabled && Number.isFinite(taskId) && taskId > 0,
  })

/** Sit agent panel: task fields + linked record without manage permission. */
export const useAutoOutboundAgentContext = (
  taskId: number,
  params?: { call_record_id?: number | null; phone_number?: string | null },
  enabled = true,
) => {
  const queryParams: ListParams = {
    call_record_id: params?.call_record_id ?? undefined,
    phone_number: params?.phone_number ?? undefined,
  }
  return useQuery({
    queryKey: autoOutboundTaskKeys.agentContext(taskId, queryParams),
    queryFn: () =>
      get<AutoOutboundAgentContext>(
        `v1/engagement/auto-outbound-tasks/${taskId}/agent-context`,
        { searchParams: searchParams(queryParams) },
      ),
    enabled: enabled && Number.isFinite(taskId) && taskId > 0,
  })
}

export const useAutoOutboundTaskStats = (taskId: number, enabled = true) =>
  useQuery({
    queryKey: autoOutboundTaskKeys.stats(taskId),
    queryFn: () =>
      get<AutoOutboundTaskStatsResponse>(`v1/engagement/auto-outbound-tasks/${taskId}/stats`),
    enabled: enabled && Number.isFinite(taskId) && taskId > 0,
  })

export const useAutoOutboundMonitor = (taskId: number, enabled = true) =>
  useQuery({
    queryKey: autoOutboundTaskKeys.monitor(taskId),
    queryFn: () =>
      get<AutoOutboundMonitorResponse>(`v1/engagement/auto-outbound-tasks/${taskId}/monitor`),
    enabled: enabled && Number.isFinite(taskId) && taskId > 0,
    refetchInterval: enabled ? 5000 : false,
  })

export const useSubmitAutoOutboundWrapup = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      taskId: number
      recordId: number
      data: AutoOutboundWrapupPayload
    }) =>
      post<AutoOutboundRecord>(
        `v1/engagement/auto-outbound-tasks/${vars.taskId}/records/${vars.recordId}/wrapup`,
        { json: vars.data },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: autoOutboundTaskKeys.task(vars.taskId) })
      qc.invalidateQueries({ queryKey: [...autoOutboundTaskKeys.task(vars.taskId), 'records'] })
      qc.invalidateQueries({
        queryKey: [...autoOutboundTaskKeys.task(vars.taskId), 'agent-context'],
      })
    },
  })
}
