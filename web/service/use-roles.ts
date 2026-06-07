import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type { PaginatedResponse } from '@/models/common'
import type { PermissionTreeResponse, Role, RoleOption, RolePayload } from '@/models/role'

const NS = 'roles'

export type RoleListParams = {
  page?: number
  per_page?: number
  keyword?: string
  type?: string
}

function roleSearchParams(params: RoleListParams): URLSearchParams {
  const sp = new URLSearchParams()
  if (params.page != null) sp.set('page', String(params.page))
  if (params.per_page != null) sp.set('per_page', String(params.per_page))
  if (params.keyword) sp.set('keyword', params.keyword)
  if (params.type) sp.set('type', params.type)
  return sp
}

export const roleKeys = {
  all: [NS] as const,
  lists: () => [...roleKeys.all, 'list'] as const,
  list: (params: RoleListParams) => [...roleKeys.lists(), params] as const,
  details: () => [...roleKeys.all, 'detail'] as const,
  detail: (id: number) => [...roleKeys.details(), id] as const,
  options: () => [...roleKeys.all, 'options'] as const,
  permissionTree: () => [...roleKeys.all, 'permission-tree'] as const,
}

export const useRoles = (params?: RoleListParams) =>
  useQuery({
    queryKey: roleKeys.list(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<Role>>('v1/roles', {
        searchParams: roleSearchParams(params ?? {}),
      }),
  })

export const useRole = (id: number, enabled = true) =>
  useQuery({
    queryKey: roleKeys.detail(id),
    queryFn: () => get<Role>(`v1/roles/${id}`),
    enabled: enabled && !!id,
  })

export const useRoleOptions = () =>
  useQuery({
    queryKey: roleKeys.options(),
    queryFn: () => get<{ items: RoleOption[] }>('v1/roles/options'),
  })

export const usePermissionTree = () =>
  useQuery({
    queryKey: roleKeys.permissionTree(),
    queryFn: () => get<PermissionTreeResponse>('v1/roles/permission-tree'),
  })

export const useCreateRole = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: RolePayload) => post<Role>('v1/roles', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: roleKeys.lists() })
      qc.invalidateQueries({ queryKey: roleKeys.options() })
    },
  })
}

export const useUpdateRole = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: RolePayload }) =>
      put<Role>(`v1/roles/${id}`, { json: data }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: roleKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: roleKeys.lists() })
      qc.invalidateQueries({ queryKey: roleKeys.options() })
    },
  })
}

export const useDeleteRole = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/roles/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: roleKeys.lists() })
      qc.invalidateQueries({ queryKey: roleKeys.options() })
    },
  })
}
