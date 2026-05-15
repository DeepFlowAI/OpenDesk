import { useQuery, useMutation, useQueryClient, type UseQueryOptions } from '@tanstack/react-query'
import { get, post, put, del, patch } from './base'
import { employeeGroupKeys } from './use-employee-groups'
import type {
  Employee,
  CreateEmployeePayload,
  UpdateEmployeePayload,
  EmployeeStatusPayload,
} from '@/models/employee'
import type { PaginatedResponse } from '@/models/common'

const NS = 'employees'

export type EmployeeListParams = {
  page?: number
  per_page?: number
  keyword?: string
  q?: string
  role?: string | string[]
  status?: string
  group_id?: number
}

export function employeeListSearchParams(params: EmployeeListParams): URLSearchParams {
  const sp = new URLSearchParams()
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  if (params.keyword != null && params.keyword !== '') sp.set('keyword', params.keyword)
  if (params.q != null && params.q !== '') sp.set('q', params.q)
  if (params.status != null && params.status !== '') sp.set('status', params.status)
  if (params.group_id != null) sp.set('group_id', String(params.group_id))
  const r = params.role
  if (r != null && r !== '') {
    const roles = Array.isArray(r) ? r : [r]
    for (const role of roles) {
      if (role) sp.append('role', role)
    }
  }
  return sp
}

export const employeeKeys = {
  all: [NS] as const,
  lists: () => [...employeeKeys.all, 'list'] as const,
  list: (params: EmployeeListParams) => [...employeeKeys.lists(), params] as const,
  details: () => [...employeeKeys.all, 'detail'] as const,
  detail: (id: number) => [...employeeKeys.details(), id] as const,
}

type UseEmployeesQueryOptions = Pick<UseQueryOptions<PaginatedResponse<Employee>>, 'enabled'>

export const useEmployees = (
  params?: EmployeeListParams,
  options?: UseEmployeesQueryOptions
) =>
  useQuery({
    queryKey: employeeKeys.list(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<Employee>>('v1/employees', {
        searchParams: employeeListSearchParams(params ?? {}),
      }),
    enabled: options?.enabled ?? true,
  })

export const useEmployee = (id: number) =>
  useQuery({
    queryKey: employeeKeys.detail(id),
    queryFn: () => get<Employee>(`v1/employees/${id}`),
    enabled: !!id,
  })

export const useCreateEmployee = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateEmployeePayload) =>
      post<Employee>('v1/employees', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeeKeys.lists() })
      qc.invalidateQueries({ queryKey: employeeGroupKeys.all })
    },
  })
}

export const useUpdateEmployee = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateEmployeePayload }) =>
      put<Employee>(`v1/employees/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: employeeKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: employeeKeys.lists() })
      qc.invalidateQueries({ queryKey: employeeGroupKeys.all })
    },
  })
}

export const useDeleteEmployee = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/employees/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: employeeKeys.lists() })
      qc.invalidateQueries({ queryKey: employeeGroupKeys.all })
    },
  })
}

export const useUpdateEmployeeStatus = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: EmployeeStatusPayload }) =>
      patch<Employee>(`v1/employees/${id}/status`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: employeeKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: employeeKeys.lists() })
    },
  })
}
