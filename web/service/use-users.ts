import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { filenameFromContentDisposition, get, getBlob, post, postBlob, postForm, put, del } from './base'
import type { EntityChange } from '@/models/entity-change'
import type {
  User,
  CreateUserPayload,
  UpdateUserPayload,
  UserQueryPayload,
  UserExportPayload,
  ViewCountsResponse,
} from '@/models/user'
import type { UserView } from '@/models/user-view'
import type { PaginatedResponse } from '@/models/common'
import type {
  ViewGroupRequestPayload,
  ViewGroupResponse,
} from '@/models/view-group'
import type {
  UserImportErrorReportPayload,
  UserImportExecuteResponse,
  UserImportPreviewResponse,
} from '@/models/user-import'

const NS = 'users'

const normalizeUserRef = (ref: string | number) => String(ref)

export const userKeys = {
  all: [NS] as const,
  queries: () => [...userKeys.all, 'query'] as const,
  query: (params: UserQueryPayload) => [...userKeys.queries(), params] as const,
  details: () => [...userKeys.all, 'detail'] as const,
  detail: (ref: string | number) => [...userKeys.details(), normalizeUserRef(ref)] as const,
  changes: (id: number, params: Record<string, unknown>) =>
    [...userKeys.detail(id), 'changes', params] as const,
  enabledViews: () => [...userKeys.all, 'enabledViews'] as const,
  viewCounts: () => [...userKeys.all, 'viewCounts'] as const,
  viewGroupsRoot: () => [...userKeys.all, 'viewGroups'] as const,
  viewGroups: (viewId: number, payload: ViewGroupRequestPayload) =>
    [...userKeys.viewGroupsRoot(), viewId, payload] as const,
}

export const useQueryUsers = (payload: UserQueryPayload) =>
  useQuery({
    queryKey: userKeys.query(payload),
    queryFn: () => post<PaginatedResponse<User>>('v1/users/query', { json: payload }),
  })

export const exportUsers = async (payload: UserExportPayload) => {
  const { blob, headers } = await postBlob('v1/users/export', {
    json: payload,
    timeout: 120000,
  })
  return {
    blob,
    filename: filenameFromContentDisposition(
      headers.get('content-disposition'),
      'users-export.xlsx',
    ),
  }
}

export const useExportUsers = () =>
  useMutation({
    mutationFn: exportUsers,
  })

export const downloadUserImportTemplate = async (locale: string) => {
  const { blob, headers } = await getBlob(`v1/users/import/template?locale=${encodeURIComponent(locale)}`)
  return {
    blob,
    filename: filenameFromContentDisposition(
      headers.get('content-disposition'),
      'users-import-template.xlsx',
    ),
  }
}

export const previewUserImport = async (file: File, locale: string) => {
  const formData = new FormData()
  formData.append('file', file)
  return postForm<UserImportPreviewResponse>(
    `v1/users/import/preview?locale=${encodeURIComponent(locale)}`,
    formData,
    120000,
  )
}

export const executeUserImport = async (previewToken: string) =>
  post<UserImportExecuteResponse>('v1/users/import/execute', {
    json: { preview_token: previewToken },
    timeout: 120000,
  })

export const downloadUserImportErrorReport = async (
  payload: UserImportErrorReportPayload,
  locale: string,
) => {
  const { blob, headers } = await postBlob(`v1/users/import/error-report?locale=${encodeURIComponent(locale)}`, {
    json: payload,
    timeout: 120000,
  })
  return {
    blob,
    filename: filenameFromContentDisposition(
      headers.get('content-disposition'),
      'users-import-errors.xlsx',
    ),
  }
}

export const useDownloadUserImportTemplate = () =>
  useMutation({ mutationFn: downloadUserImportTemplate })

export const useExecuteUserImport = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: executeUserImport,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.queries() })
      qc.invalidateQueries({ queryKey: userKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: userKeys.viewGroupsRoot() })
    },
  })
}

export const useUser = (ref: string | number | null | undefined) => {
  const userRef = String(ref ?? '')
  return useQuery({
    queryKey: userKeys.detail(userRef),
    queryFn: () => get<User>(`v1/users/${encodeURIComponent(userRef)}`),
    enabled: userRef.length > 0 && userRef !== '0',
  })
}

export const useUserChanges = (
  id: number,
  params: { page?: number; per_page?: number },
  enabled = true,
) =>
  useQuery({
    queryKey: userKeys.changes(id, params),
    queryFn: () => {
      const searchParams = new URLSearchParams()
      if (params.page) searchParams.set('page', String(params.page))
      if (params.per_page) searchParams.set('per_page', String(params.per_page))
      const qs = searchParams.toString()
      return get<PaginatedResponse<EntityChange>>(
        `v1/users/${id}/changes${qs ? `?${qs}` : ''}`,
      )
    },
    enabled: enabled && !!id,
  })

export const useCreateUser = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateUserPayload) => post<User>('v1/users', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.queries() })
      qc.invalidateQueries({ queryKey: userKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: userKeys.viewGroupsRoot() })
    },
  })
}

export const useUpdateUser = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateUserPayload }) =>
      put<User>(`v1/users/${id}`, { json: data }),
    onSuccess: (updated, v) => {
      qc.setQueryData(userKeys.detail(v.id), updated)
      qc.setQueryData(userKeys.detail(updated.public_id), updated)
      qc.invalidateQueries({ queryKey: [...userKeys.detail(v.id), 'changes'] })
      qc.invalidateQueries({ queryKey: userKeys.queries() })
      qc.invalidateQueries({ queryKey: userKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: userKeys.viewGroupsRoot() })
    },
  })
}

export const useDeleteUser = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/users/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.details() })
      qc.invalidateQueries({ queryKey: userKeys.queries() })
      qc.invalidateQueries({ queryKey: userKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: userKeys.viewGroupsRoot() })
    },
  })
}

export const useEnabledUserViews = () =>
  useQuery({
    queryKey: userKeys.enabledViews(),
    queryFn: () => get<UserView[]>('v1/users/views/enabled'),
  })

export const useUserViewCounts = () =>
  useQuery({
    queryKey: userKeys.viewCounts(),
    queryFn: () => get<ViewCountsResponse>('v1/users/views/counts'),
  })

export const useUserViewGroups = (
  viewId: number | null,
  payload: ViewGroupRequestPayload,
  enabled: boolean,
) =>
  useQuery({
    queryKey: userKeys.viewGroups(viewId ?? -1, payload),
    queryFn: () =>
      post<ViewGroupResponse>(`v1/users/views/${viewId}/groups`, {
        json: payload,
      }),
    enabled: enabled && viewId != null,
    staleTime: 30_000,
  })
