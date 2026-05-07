import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './base'
import type { EntityChange } from '@/models/entity-change'
import type {
  Organization,
  CreateOrganizationPayload,
  UpdateOrganizationPayload,
  OrganizationQueryPayload,
  OrgViewCountsResponse,
} from '@/models/organization'
import type { OrganizationView } from '@/models/organization-view'
import type { PaginatedResponse } from '@/models/common'
import type { User } from '@/models/user'
import type {
  ViewGroupRequestPayload,
  ViewGroupResponse,
} from '@/models/view-group'

const NS = 'organizations'

export const orgKeys = {
  all: [NS] as const,
  queries: () => [...orgKeys.all, 'query'] as const,
  query: (params: OrganizationQueryPayload) => [...orgKeys.queries(), params] as const,
  details: () => [...orgKeys.all, 'detail'] as const,
  detail: (id: number) => [...orgKeys.details(), id] as const,
  enabledViews: () => [...orgKeys.all, 'enabledViews'] as const,
  viewCounts: () => [...orgKeys.all, 'viewCounts'] as const,
  viewGroupsRoot: () => [...orgKeys.all, 'viewGroups'] as const,
  viewGroups: (viewId: number, payload: ViewGroupRequestPayload) =>
    [...orgKeys.viewGroupsRoot(), viewId, payload] as const,
  users: (orgId: number, params: Record<string, unknown>) =>
    [...orgKeys.all, 'users', orgId, params] as const,
  changes: (id: number, params: Record<string, unknown>) =>
    [...orgKeys.detail(id), 'changes', params] as const,
}

export const useQueryOrganizations = (payload: OrganizationQueryPayload, enabled = true) =>
  useQuery({
    queryKey: orgKeys.query(payload),
    queryFn: () =>
      post<PaginatedResponse<Organization>>('v1/organizations/query', { json: payload }),
    enabled,
  })

export const useOrganization = (id: number, enabled = true) =>
  useQuery({
    queryKey: orgKeys.detail(id),
    queryFn: () => get<Organization>(`v1/organizations/${id}`),
    enabled: enabled && !!id,
  })

export const useOrganizationChanges = (
  id: number,
  params: { page?: number; per_page?: number },
  enabled = true,
) =>
  useQuery({
    queryKey: orgKeys.changes(id, params),
    queryFn: () => {
      const searchParams = new URLSearchParams()
      if (params.page) searchParams.set('page', String(params.page))
      if (params.per_page) searchParams.set('per_page', String(params.per_page))
      const qs = searchParams.toString()
      return get<PaginatedResponse<EntityChange>>(
        `v1/organizations/${id}/changes${qs ? `?${qs}` : ''}`,
      )
    },
    enabled: enabled && !!id,
  })

export const useCreateOrganization = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateOrganizationPayload) =>
      post<Organization>('v1/organizations', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orgKeys.queries() })
      qc.invalidateQueries({ queryKey: orgKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: orgKeys.viewGroupsRoot() })
    },
  })
}

export const useUpdateOrganization = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateOrganizationPayload }) =>
      put<Organization>(`v1/organizations/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: orgKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: [...orgKeys.detail(v.id), 'changes'] })
      qc.invalidateQueries({ queryKey: orgKeys.queries() })
      qc.invalidateQueries({ queryKey: orgKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: orgKeys.viewGroupsRoot() })
    },
  })
}

export const useDeleteOrganization = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const ky = (await import('ky')).default
      const token = localStorage.getItem('auth_token')
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
      await ky.delete(`v1/organizations/${id}`, {
        prefixUrl: baseUrl,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orgKeys.queries() })
      qc.invalidateQueries({ queryKey: orgKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: orgKeys.viewGroupsRoot() })
    },
  })
}

export const useEnabledOrgViews = (enabled = true) =>
  useQuery({
    queryKey: orgKeys.enabledViews(),
    queryFn: () => get<OrganizationView[]>('v1/organizations/views/enabled'),
    enabled,
  })

export const useOrgViewCounts = (enabled = true) =>
  useQuery({
    queryKey: orgKeys.viewCounts(),
    queryFn: () => get<OrgViewCountsResponse>('v1/organizations/views/counts'),
    enabled,
  })

export const useOrgViewGroups = (
  viewId: number | null,
  payload: ViewGroupRequestPayload,
  enabled: boolean,
) =>
  useQuery({
    queryKey: orgKeys.viewGroups(viewId ?? -1, payload),
    queryFn: () =>
      post<ViewGroupResponse>(`v1/organizations/views/${viewId}/groups`, {
        json: payload,
      }),
    enabled: enabled && viewId != null,
    staleTime: 30_000,
  })

export const useOrgUsers = (
  orgId: number,
  params: { page?: number; per_page?: number; search?: string },
) =>
  useQuery({
    queryKey: orgKeys.users(orgId, params),
    queryFn: () => {
      const searchParams = new URLSearchParams()
      if (params.page) searchParams.set('page', String(params.page))
      if (params.per_page) searchParams.set('per_page', String(params.per_page))
      if (params.search) searchParams.set('search', params.search)
      const qs = searchParams.toString()
      return get<PaginatedResponse<User>>(
        `v1/organizations/${orgId}/users${qs ? `?${qs}` : ''}`,
      )
    },
    enabled: !!orgId,
  })
