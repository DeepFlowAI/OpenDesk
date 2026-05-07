import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  ServiceHours,
  CreateServiceHoursPayload,
  UpdateServiceHoursPayload,
} from '@/models/service-hours'

const NS = 'service-hours'

export const serviceHoursKeys = {
  all: [NS] as const,
  lists: () => [...serviceHoursKeys.all, 'list'] as const,
  details: () => [...serviceHoursKeys.all, 'detail'] as const,
  detail: (id: number) => [...serviceHoursKeys.details(), id] as const,
}

export const useServiceHours = () =>
  useQuery({
    queryKey: serviceHoursKeys.lists(),
    queryFn: () => get<ServiceHours[]>('v1/service-hours'),
  })

export const useServiceHoursDetail = (id: number) =>
  useQuery({
    queryKey: serviceHoursKeys.detail(id),
    queryFn: () => get<ServiceHours>(`v1/service-hours/${id}`),
    enabled: !!id,
  })

export const useCreateServiceHours = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateServiceHoursPayload) =>
      post<ServiceHours>('v1/service-hours', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: serviceHoursKeys.lists() }),
  })
}

export const useUpdateServiceHours = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateServiceHoursPayload }) =>
      put<ServiceHours>(`v1/service-hours/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: serviceHoursKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: serviceHoursKeys.lists() })
    },
  })
}

export const useDeleteServiceHours = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/service-hours/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: serviceHoursKeys.lists() }),
  })
}
