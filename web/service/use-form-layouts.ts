import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type { PaginatedResponse } from '@/models/common'
import type {
  FdFormLayout,
  FdFormLayoutSummary,
  CreateFdFormLayoutPayload,
  UpdateFdFormLayoutPayload,
} from '@/models/form-layout'

const NS = 'form-layouts'

export const formLayoutKeys = {
  all: [NS] as const,
  lists: () => [...formLayoutKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...formLayoutKeys.lists(), params] as const,
  details: () => [...formLayoutKeys.all, 'detail'] as const,
  detail: (id: number) => [...formLayoutKeys.details(), id] as const,
}

export const useFormLayouts = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: formLayoutKeys.list(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<FdFormLayoutSummary>>('v1/form-layouts', { searchParams: params }),
  })

export const useFormLayout = (id: number) =>
  useQuery({
    queryKey: formLayoutKeys.detail(id),
    queryFn: () => get<FdFormLayout>(`v1/form-layouts/${id}`),
    enabled: !!id,
  })

export const useCreateFormLayout = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateFdFormLayoutPayload) =>
      post<FdFormLayout>('v1/form-layouts', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: formLayoutKeys.lists() }),
  })
}

export const useUpdateFormLayout = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateFdFormLayoutPayload }) =>
      put<FdFormLayout>(`v1/form-layouts/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: formLayoutKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: formLayoutKeys.lists() })
    },
  })
}

export const useDeleteFormLayout = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/form-layouts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: formLayoutKeys.lists() }),
  })
}
