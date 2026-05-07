import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  EmployeeGroup,
  EmployeeGroupListItem,
  CreateEmployeeGroupPayload,
  UpdateEmployeeGroupPayload,
  UserListItem,
} from '@/models/employee-group'
import type { PaginatedResponse } from '@/models/common'

const NS = 'employee-groups'

export const employeeGroupKeys = {
  all: [NS] as const,
  lists: () => [...employeeGroupKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...employeeGroupKeys.lists(), params] as const,
  details: () => [...employeeGroupKeys.all, 'detail'] as const,
  detail: (id: number) => [...employeeGroupKeys.details(), id] as const,
}

export const employeeSelectKeys = {
  all: ['employee-select'] as const,
  lists: () => [...employeeSelectKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...employeeSelectKeys.lists(), params] as const,
}

export type EmployeeGroupListParams = {
  page?: number
  per_page?: number
  keyword?: string
  q?: string
  member_id?: number
}

export const useEmployeeGroups = (params?: EmployeeGroupListParams) =>
  useQuery({
    queryKey: employeeGroupKeys.list(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<EmployeeGroupListItem>>('v1/employee-groups', {
        searchParams: params as Record<string, string | number>,
      }),
  })

export const useEmployeeGroup = (id: number) =>
  useQuery({
    queryKey: employeeGroupKeys.detail(id),
    queryFn: () => get<EmployeeGroup>(`v1/employee-groups/${id}`),
    enabled: !!id,
  })

export const useCreateEmployeeGroup = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateEmployeeGroupPayload) =>
      post<EmployeeGroup>('v1/employee-groups', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: employeeGroupKeys.lists() }),
  })
}

export const useUpdateEmployeeGroup = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateEmployeeGroupPayload }) =>
      put<EmployeeGroup>(`v1/employee-groups/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: employeeGroupKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: employeeGroupKeys.lists() })
    },
  })
}

export const useDeleteEmployeeGroup = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/employee-groups/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: employeeGroupKeys.lists() }),
  })
}

export const useEmployeeSelect = (params?: { page?: number; per_page?: number; keyword?: string }) =>
  useQuery({
    queryKey: employeeSelectKeys.list(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<UserListItem>>('v1/system-users', {
        searchParams: params as Record<string, string | number>,
      }),
  })
