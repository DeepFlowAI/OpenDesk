import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, postForm, put } from './base'
import type {
  CreateSmsBulkTargetPayload,
  CreateSmsBulkTaskPayload,
  SmsBulkImportExecuteResponse,
  SmsBulkImportMappingPayload,
  SmsBulkImportParseResponse,
  SmsBulkImportValidateResponse,
  SmsBulkTarget,
  SmsBulkTargetBulkDeleteResponse,
  SmsBulkTargetDetail,
  SmsBulkTargetListResponse,
  SmsBulkTargetResendResponse,
  SmsBulkTask,
  SmsBulkTaskDetail,
  SmsBulkTaskListResponse,
  SmsBulkTemplateListResponse,
  UpdateSmsBulkTaskPayload,
} from '@/models/sms-bulk-task'

const NS = 'sms-bulk-tasks'

type ListParams = Record<string, string | number | boolean | null | undefined>

function searchParams(params?: ListParams): URLSearchParams {
  const sp = new URLSearchParams()
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    sp.set(key, String(value))
  })
  return sp
}

export const smsBulkTaskKeys = {
  all: [NS] as const,
  tasks: (params?: ListParams) => [...smsBulkTaskKeys.all, 'tasks', params ?? {}] as const,
  task: (id: number) => [...smsBulkTaskKeys.all, 'task', id] as const,
  targets: (taskId: number, params?: ListParams) => [...smsBulkTaskKeys.task(taskId), 'targets', params ?? {}] as const,
  target: (taskId: number, targetId: number) => [...smsBulkTaskKeys.task(taskId), 'target', targetId] as const,
  availableTemplates: () => [...smsBulkTaskKeys.all, 'available-templates'] as const,
}

export const useSmsBulkTasks = (params?: ListParams) =>
  useQuery({
    queryKey: smsBulkTaskKeys.tasks(params),
    queryFn: () => get<SmsBulkTaskListResponse>('v1/engagement/sms-tasks', { searchParams: searchParams(params) }),
    placeholderData: (prev) => prev,
  })

export const useSmsBulkTask = (id: number) =>
  useQuery({
    queryKey: smsBulkTaskKeys.task(id),
    queryFn: () => get<SmsBulkTaskDetail>(`v1/engagement/sms-tasks/${id}`),
    enabled: Number.isFinite(id) && id > 0,
  })

export const useSmsBulkAvailableTemplates = (options?: { enabled?: boolean }) =>
  useQuery({
    queryKey: smsBulkTaskKeys.availableTemplates(),
    queryFn: () => get<SmsBulkTemplateListResponse>('v1/engagement/sms-tasks/available-templates'),
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
  })

export const useCreateSmsBulkTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateSmsBulkTaskPayload) => post<SmsBulkTask>('v1/engagement/sms-tasks', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: smsBulkTaskKeys.all }),
  })
}

export const useUpdateSmsBulkTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateSmsBulkTaskPayload }) =>
      put<SmsBulkTask>(`v1/engagement/sms-tasks/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: smsBulkTaskKeys.task(v.id) })
      qc.invalidateQueries({ queryKey: smsBulkTaskKeys.tasks() })
    },
  })
}

export const useDeleteSmsBulkTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/engagement/sms-tasks/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: smsBulkTaskKeys.all }),
  })
}

export const useTransitionSmsBulkTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'publish' | 'pause' | 'resume' | 'archive' }) =>
      post<SmsBulkTask>(`v1/engagement/sms-tasks/${id}/${action}`),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: smsBulkTaskKeys.task(v.id) })
      qc.invalidateQueries({ queryKey: smsBulkTaskKeys.all })
    },
  })
}

export const useSmsBulkTargets = (taskId: number, params?: ListParams) =>
  useQuery({
    queryKey: smsBulkTaskKeys.targets(taskId, params),
    queryFn: () =>
      get<SmsBulkTargetListResponse>(`v1/engagement/sms-tasks/${taskId}/targets`, { searchParams: searchParams(params) }),
    enabled: Number.isFinite(taskId) && taskId > 0,
    placeholderData: (prev) => prev,
  })

export const useSmsBulkTargetDetail = (taskId: number, targetId: number | null) =>
  useQuery({
    queryKey: smsBulkTaskKeys.target(taskId, targetId ?? 0),
    queryFn: () => get<SmsBulkTargetDetail>(`v1/engagement/sms-tasks/${taskId}/targets/${targetId}`),
    enabled: Number.isFinite(taskId) && taskId > 0 && typeof targetId === 'number' && targetId > 0,
  })

export const useCreateSmsBulkTarget = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateSmsBulkTargetPayload) =>
      post<SmsBulkTarget>(`v1/engagement/sms-tasks/${taskId}/targets`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: smsBulkTaskKeys.task(taskId) }),
  })
}

export const useBulkDeleteSmsBulkTargets = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (targetIds: number[]) =>
      post<SmsBulkTargetBulkDeleteResponse>(`v1/engagement/sms-tasks/${taskId}/targets/bulk-delete`, {
        json: { target_ids: targetIds },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: smsBulkTaskKeys.task(taskId) }),
  })
}

export const useResendFailedSmsBulkTargets = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post<SmsBulkTargetResendResponse>(`v1/engagement/sms-tasks/${taskId}/targets/resend-failed`),
    onSuccess: () => qc.invalidateQueries({ queryKey: smsBulkTaskKeys.task(taskId) }),
  })
}

export const useParseSmsBulkImport = () =>
  useMutation({
    mutationFn: ({ taskId, file }: { taskId: number; file: File }) => {
      const formData = new FormData()
      formData.append('file', file)
      return postForm<SmsBulkImportParseResponse>(`v1/engagement/sms-tasks/${taskId}/targets/import/parse`, formData, 120000)
    },
  })

export const useValidateSmsBulkImport = () =>
  useMutation({
    mutationFn: ({ taskId, data }: { taskId: number; data: SmsBulkImportMappingPayload }) =>
      post<SmsBulkImportValidateResponse>(`v1/engagement/sms-tasks/${taskId}/targets/import/validate`, { json: data }),
  })

export const useExecuteSmsBulkImport = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SmsBulkImportMappingPayload) =>
      post<SmsBulkImportExecuteResponse>(`v1/engagement/sms-tasks/${taskId}/targets/import`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: smsBulkTaskKeys.task(taskId) }),
  })
}
