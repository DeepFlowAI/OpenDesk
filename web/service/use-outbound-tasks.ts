import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post, postForm, put } from './base'
import type {
  BulkAssignPayload,
  BulkAssignResponse,
  BulkDeletePayload,
  BulkDeleteResponse,
  CreateOutboundRecordPayload,
  CreateOutboundTargetPayload,
  CreateOutboundTaskPayload,
  CreateOutboundTemplatePayload,
  MyOutboundTargetRecordsResponse,
  MyOutboundTaskListResponse,
  OutboundRecord,
  OutboundRecordListResponse,
  OutboundScript,
  OutboundTarget,
  OutboundTargetImportResponse,
  OutboundTargetListResponse,
  OutboundTask,
  OutboundTaskListResponse,
  OutboundTaskTemplate,
  OutboundTemplateListResponse,
  UpdateOutboundTargetPayload,
  UpdateMyOutboundTargetPayload,
  UpdateOutboundTaskPayload,
  UpdateOutboundTemplatePayload,
} from '@/models/outbound-task'

const NS = 'outbound-tasks'

type ListParams = Record<string, string | number | boolean | null | undefined>

function searchParams(params?: ListParams): URLSearchParams {
  const sp = new URLSearchParams()
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    sp.set(key, String(value))
  })
  return sp
}

export const outboundTaskKeys = {
  all: [NS] as const,
  templates: (params?: ListParams) => [...outboundTaskKeys.all, 'templates', params ?? {}] as const,
  template: (id: number) => [...outboundTaskKeys.all, 'template', id] as const,
  tasks: (params?: ListParams) => [...outboundTaskKeys.all, 'tasks', params ?? {}] as const,
  task: (id: number) => [...outboundTaskKeys.all, 'task', id] as const,
  targets: (taskId: number, params?: ListParams) => [...outboundTaskKeys.task(taskId), 'targets', params ?? {}] as const,
  records: (taskId: number, params?: ListParams) => [...outboundTaskKeys.task(taskId), 'records', params ?? {}] as const,
  myTargets: (params?: ListParams) => [...outboundTaskKeys.all, 'my-targets', params ?? {}] as const,
}

export const useOutboundTaskTemplates = (params?: ListParams) =>
  useQuery({
    queryKey: outboundTaskKeys.templates(params),
    queryFn: () => get<OutboundTemplateListResponse>('v1/engagement/outbound-task-templates', { searchParams: searchParams(params) }),
  })

export const useOutboundTaskTemplate = (id: number) =>
  useQuery({
    queryKey: outboundTaskKeys.template(id),
    queryFn: () => get<OutboundTaskTemplate>(`v1/engagement/outbound-task-templates/${id}`),
    enabled: Number.isFinite(id) && id > 0,
  })

export const useCreateOutboundTaskTemplate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateOutboundTemplatePayload) =>
      post<OutboundTaskTemplate>('v1/engagement/outbound-task-templates', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.all }),
  })
}

export const useUpdateOutboundTaskTemplate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateOutboundTemplatePayload }) =>
      put<OutboundTaskTemplate>(`v1/engagement/outbound-task-templates/${id}`, { json: data }),
    onSuccess: (updated, v) => {
      qc.setQueryData(outboundTaskKeys.template(v.id), updated)
      qc.invalidateQueries({ queryKey: outboundTaskKeys.template(v.id) })
      qc.invalidateQueries({ queryKey: [...outboundTaskKeys.all, 'templates'] })
    },
  })
}

export const useDeleteOutboundTaskTemplate = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/engagement/outbound-task-templates/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.all }),
  })
}

export const useOutboundTasks = (params?: ListParams) =>
  useQuery({
    queryKey: outboundTaskKeys.tasks(params),
    queryFn: () => get<OutboundTaskListResponse>('v1/engagement/outbound-tasks', { searchParams: searchParams(params) }),
  })

export const useOutboundTask = (id: number) =>
  useQuery({
    queryKey: outboundTaskKeys.task(id),
    queryFn: () => get<OutboundTask>(`v1/engagement/outbound-tasks/${id}`),
    enabled: Number.isFinite(id) && id > 0,
  })

export const useCreateOutboundTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateOutboundTaskPayload) => post<OutboundTask>('v1/engagement/outbound-tasks', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.all }),
  })
}

export const useUpdateOutboundTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateOutboundTaskPayload }) =>
      put<OutboundTask>(`v1/engagement/outbound-tasks/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: outboundTaskKeys.task(v.id) })
      qc.invalidateQueries({ queryKey: outboundTaskKeys.tasks() })
    },
  })
}

export const useTransitionOutboundTask = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'publish' | 'pause' | 'resume' | 'archive' }) =>
      post<OutboundTask>(`v1/engagement/outbound-tasks/${id}/${action}`),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: outboundTaskKeys.task(v.id) })
      qc.invalidateQueries({ queryKey: outboundTaskKeys.all })
    },
  })
}

export const useOutboundTargets = (taskId: number, params?: ListParams) =>
  useQuery({
    queryKey: outboundTaskKeys.targets(taskId, params),
    queryFn: () =>
      get<OutboundTargetListResponse>(`v1/engagement/outbound-tasks/${taskId}/targets`, { searchParams: searchParams(params) }),
    enabled: Number.isFinite(taskId) && taskId > 0,
  })

export const useCreateOutboundTarget = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateOutboundTargetPayload) =>
      post<OutboundTarget>(`v1/engagement/outbound-tasks/${taskId}/targets`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.task(taskId) }),
  })
}

export const useImportOutboundTargets = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return postForm<OutboundTargetImportResponse>(`v1/engagement/outbound-tasks/${taskId}/targets/import`, formData, 120000)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.task(taskId) }),
  })
}

export const useUpdateOutboundTarget = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateOutboundTargetPayload }) =>
      put<OutboundTarget>(`v1/engagement/outbound-targets/${id}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.all }),
  })
}

export const useBulkAssignOutboundTargets = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BulkAssignPayload) =>
      post<BulkAssignResponse>(`v1/engagement/outbound-tasks/${taskId}/targets/bulk-assign`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.task(taskId) }),
  })
}

export const useBulkDeleteOutboundTargets = (taskId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BulkDeletePayload) =>
      post<BulkDeleteResponse>(`v1/engagement/outbound-tasks/${taskId}/targets/bulk-delete`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.task(taskId) }),
  })
}

export const useOutboundRecords = (taskId: number, params?: ListParams) =>
  useQuery({
    queryKey: outboundTaskKeys.records(taskId, params),
    queryFn: () =>
      get<OutboundRecordListResponse>(`v1/engagement/outbound-tasks/${taskId}/records`, { searchParams: searchParams(params) }),
    enabled: Number.isFinite(taskId) && taskId > 0,
  })

export const useMyOutboundTargets = (params?: ListParams) =>
  useQuery({
    queryKey: outboundTaskKeys.myTargets(params),
    queryFn: () => get<OutboundTargetListResponse>('v1/engagement/my-outbound-targets', { searchParams: searchParams(params) }),
  })

export const useMyOutboundTasks = () =>
  useQuery({
    queryKey: [...outboundTaskKeys.all, 'my-tasks'] as const,
    queryFn: () => get<MyOutboundTaskListResponse>('v1/engagement/my-outbound-tasks'),
  })

export const useMyOutboundTargetRecords = (targetId: number, enabled = true) =>
  useQuery({
    queryKey: [...outboundTaskKeys.all, 'my-target-records', targetId] as const,
    queryFn: () => get<MyOutboundTargetRecordsResponse>(`v1/engagement/my-outbound-targets/${targetId}/records`),
    enabled: enabled && Number.isFinite(targetId) && targetId > 0,
  })

export const useMyOutboundTargetScript = (targetId: number, enabled: boolean) =>
  useQuery({
    queryKey: [...outboundTaskKeys.all, 'my-target-script', targetId] as const,
    queryFn: () => get<OutboundScript>(`v1/engagement/my-outbound-targets/${targetId}/script`),
    enabled: enabled && Number.isFinite(targetId) && targetId > 0,
    staleTime: Infinity,
  })

export const useUpdateMyOutboundTarget = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ targetId, data }: { targetId: number; data: UpdateMyOutboundTargetPayload }) =>
      patch<OutboundTarget>(`v1/engagement/my-outbound-targets/${targetId}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...outboundTaskKeys.all, 'my-targets'] }),
  })
}

export const useCreateOutboundRecord = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ targetId, data }: { targetId: number; data: CreateOutboundRecordPayload }) =>
      post<OutboundRecord>(`v1/engagement/outbound-targets/${targetId}/records`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: outboundTaskKeys.all }),
  })
}
