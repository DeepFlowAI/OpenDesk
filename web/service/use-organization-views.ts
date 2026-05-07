import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  OrganizationView,
  CreateOrganizationViewPayload,
  UpdateOrganizationViewPayload,
  OrganizationViewSortPayload,
  OrganizationViewTogglePayload,
} from '@/models/organization-view'
import type { PaginatedResponse } from '@/models/common'

const NS = 'organizationViews'

export const organizationViewKeys = {
  all: [NS] as const,
  lists: () => [...organizationViewKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...organizationViewKeys.lists(), params] as const,
  details: () => [...organizationViewKeys.all, 'detail'] as const,
  detail: (id: number) => [...organizationViewKeys.details(), id] as const,
}

export const useOrganizationViews = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: organizationViewKeys.list(params ?? {}),
    queryFn: () => get<PaginatedResponse<OrganizationView>>('v1/organization-views', { searchParams: params }),
  })

export const useOrganizationView = (id: number) =>
  useQuery({
    queryKey: organizationViewKeys.detail(id),
    queryFn: () => get<OrganizationView>(`v1/organization-views/${id}`),
    enabled: !!id,
  })

export const useCreateOrganizationView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateOrganizationViewPayload) =>
      post<OrganizationView>('v1/organization-views', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: organizationViewKeys.lists() }),
  })
}

export const useUpdateOrganizationView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateOrganizationViewPayload }) =>
      put<OrganizationView>(`v1/organization-views/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: organizationViewKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: organizationViewKeys.lists() })
    },
  })
}

export const useDeleteOrganizationView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/organization-views/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: organizationViewKeys.lists() }),
  })
}

export const useToggleOrganizationView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: OrganizationViewTogglePayload }) =>
      put<OrganizationView>(`v1/organization-views/${id}/toggle`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: organizationViewKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: organizationViewKeys.lists() })
    },
  })
}

export const useSortOrganizationViews = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: OrganizationViewSortPayload) =>
      put<{ message: string }>('v1/organization-views/sort', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: organizationViewKeys.lists() }),
  })
}
