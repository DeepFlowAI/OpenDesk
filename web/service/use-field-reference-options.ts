import { useQuery } from '@tanstack/react-query'
import { get } from './base'
import type { PaginatedResponse } from '@/models/common'

const NS = 'field-reference-options'

export type FieldReferenceEmployeeGroupOption = {
  id: number
  name: string
  description: string | null
  member_count: number
  created_at: string | null
  updated_at: string | null
}

export type FieldReferenceEmployeeOption = {
  id: number
  name: string
  nickname: string | null
  job_number: string | null
  username: string
  email: string | null
  phone: string | null
}

export type FieldReferenceEmployeeGroupParams = {
  page?: number
  per_page?: number
  keyword?: string
  q?: string
  member_id?: number
}

export type FieldReferenceEmployeeParams = {
  page?: number
  per_page?: number
  keyword?: string
  q?: string
  group_id?: number
}

export const fieldReferenceOptionKeys = {
  all: [NS] as const,
  employeeGroups: (params: FieldReferenceEmployeeGroupParams) =>
    [...fieldReferenceOptionKeys.all, 'employee-groups', params] as const,
  employeeGroup: (id: number) => [...fieldReferenceOptionKeys.all, 'employee-groups', id] as const,
  employees: (params: FieldReferenceEmployeeParams) =>
    [...fieldReferenceOptionKeys.all, 'employees', params] as const,
  employee: (id: number) => [...fieldReferenceOptionKeys.all, 'employees', id] as const,
}

function searchParams(params: Record<string, string | number | undefined>): URLSearchParams {
  const sp = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    sp.set(key, String(value))
  }
  return sp
}

export const useFieldReferenceEmployeeGroups = (params?: FieldReferenceEmployeeGroupParams) =>
  useQuery({
    queryKey: fieldReferenceOptionKeys.employeeGroups(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<FieldReferenceEmployeeGroupOption>>(
        'v1/field-definitions/reference-options/employee-groups',
        { searchParams: searchParams(params ?? {}) },
      ),
  })

export const useFieldReferenceEmployeeGroup = (id: number) =>
  useQuery({
    queryKey: fieldReferenceOptionKeys.employeeGroup(id),
    queryFn: () =>
      get<FieldReferenceEmployeeGroupOption>(
        `v1/field-definitions/reference-options/employee-groups/${id}`,
      ),
    enabled: !!id,
  })

export const useFieldReferenceEmployees = (params?: FieldReferenceEmployeeParams) =>
  useQuery({
    queryKey: fieldReferenceOptionKeys.employees(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<FieldReferenceEmployeeOption>>(
        'v1/field-definitions/reference-options/employees',
        { searchParams: searchParams(params ?? {}) },
      ),
  })

export const useFieldReferenceEmployee = (id: number) =>
  useQuery({
    queryKey: fieldReferenceOptionKeys.employee(id),
    queryFn: () =>
      get<FieldReferenceEmployeeOption>(
        `v1/field-definitions/reference-options/employees/${id}`,
      ),
    enabled: !!id,
  })
