import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  CreateDashboardPayload,
  DashboardDetail,
  DashboardListResponse,
  DashboardRunRequest,
  DashboardRunResult,
  DashboardSnapshotPayload,
  DashboardStatus,
  WorkspaceDashboardDetail,
  WorkspaceDashboardListResponse,
} from '@/models/custom-dashboard'

const NS = 'custom-dashboards'

export const customDashboardKeys = {
  all: [NS] as const,
  lists: () => [NS, 'list'] as const,
  list: (params: Record<string, unknown>) => [NS, 'list', params] as const,
  detail: (id: number) => [NS, 'detail', id] as const,
}

export const useCustomDashboards = (params: {
  page: number
  per_page: number
  keyword?: string
  status?: DashboardStatus
}) => useQuery({
  queryKey: customDashboardKeys.list(params),
  queryFn: () => get<DashboardListResponse>('v1/custom-dashboards', {
    searchParams: params as Record<string, string | number>,
  }),
})

export const useCustomDashboard = (id: number) => useQuery({
  queryKey: customDashboardKeys.detail(id),
  queryFn: () => get<DashboardDetail>(`v1/custom-dashboards/${id}`),
  enabled: id > 0,
  refetchOnWindowFocus: false,
})

function useLifecycleMutation<TVariables>(
  mutationFn: (variables: TVariables) => Promise<DashboardDetail>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (result) => {
      queryClient.setQueryData(customDashboardKeys.detail(result.id), result)
      queryClient.invalidateQueries({ queryKey: customDashboardKeys.lists() })
    },
  })
}

export const useCreateCustomDashboard = () => useLifecycleMutation(
  (data: CreateDashboardPayload) => post<DashboardDetail>('v1/custom-dashboards', { json: data }),
)

export const useUpdateCustomDashboard = () => useLifecycleMutation(
  ({ id, data }: { id: number; data: DashboardSnapshotPayload }) =>
    put<DashboardDetail>(`v1/custom-dashboards/${id}`, { json: data }),
)

export const usePublishCustomDashboard = () => useLifecycleMutation(
  (id: number) => post<DashboardDetail>(`v1/custom-dashboards/${id}/publish`),
)

export const useDisableCustomDashboard = () => useLifecycleMutation(
  (id: number) => post<DashboardDetail>(`v1/custom-dashboards/${id}/disable`),
)

export const useEnableCustomDashboard = () => useLifecycleMutation(
  (id: number) => post<DashboardDetail>(`v1/custom-dashboards/${id}/enable`),
)

export const useCopyCustomDashboard = () => useLifecycleMutation(
  ({ id, slug, name }: { id: number; slug: string; name?: string }) =>
    post<DashboardDetail>(`v1/custom-dashboards/${id}/copy`, { json: { slug, name } }),
)

export const useDeleteCustomDashboard = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/custom-dashboards/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: customDashboardKeys.lists() }),
  })
}

export const useReorderCustomDashboards = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ids: number[]) => post('v1/custom-dashboards/reorder', { json: { ids } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: customDashboardKeys.lists() }),
  })
}

export const usePreviewCustomDashboard = (id: number) => useMutation({
  mutationFn: (request: DashboardRunRequest) =>
    post<DashboardRunResult>(`v1/custom-dashboards/${id}/preview`, { json: request }),
})

export const cancelCustomDashboardRun = (requestId: string) =>
  post(`v1/custom-dashboard-runs/${requestId}/cancel`)

export const cancelCustomDashboardPageRun = (pageRunId: string) =>
  post(`v1/custom-dashboard-runs/pages/${pageRunId}/cancel`)

export const workspaceCustomDashboardKeys = {
  all: ['workspace-custom-dashboards'] as const,
  list: (keyword: string) => ['workspace-custom-dashboards', 'list', keyword] as const,
  detail: (id: number) => ['workspace-custom-dashboards', 'detail', id] as const,
}

export const useWorkspaceCustomDashboards = (keyword = '') => useQuery({
  queryKey: workspaceCustomDashboardKeys.list(keyword),
  queryFn: () => get<WorkspaceDashboardListResponse>('v1/workspace/custom-dashboards', {
    searchParams: keyword ? { keyword } : undefined,
  }),
})

export const useWorkspaceCustomDashboard = (id: number) => useQuery({
  queryKey: workspaceCustomDashboardKeys.detail(id),
  queryFn: () => get<WorkspaceDashboardDetail>(`v1/workspace/custom-dashboards/${id}`),
  enabled: id > 0,
  refetchOnWindowFocus: false,
})

export const runWorkspaceCustomDashboardComponent = (id: number, request: DashboardRunRequest) =>
  post<DashboardRunResult>(`v1/workspace/custom-dashboards/${id}/run`, { json: request })
