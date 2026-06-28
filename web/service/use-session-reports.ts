import { useMutation, useQuery } from '@tanstack/react-query'
import { get, getBlob } from '@/service/base'
import type {
  EmployeeDetailResponse,
  EmployeeSortField,
  EmployeesListResponse,
  OverviewResponse,
  QueueDetailResponse,
  QueueListResponse,
  QueueMetricGroup,
  QueueReportExportParams,
  QueueSortField,
  QueueTrendResponse,
  QueueType,
  SessionReportExportParams,
  SortOrder,
  TrendResponse,
  TrendType,
} from '@/models/session-report'

type CommonParams = {
  start: string
  end: string
  employee_id?: number
  enabled?: boolean
}

export const useSessionReportsOverview = (params: CommonParams) => {
  const { start, end, employee_id, enabled } = params
  const searchParams: Record<string, string> = { start, end }
  if (employee_id !== undefined) searchParams.employee_id = String(employee_id)

  return useQuery({
    queryKey: ['session-reports', 'overview', start, end, employee_id ?? null],
    queryFn: () =>
      get<OverviewResponse>('v1/reports/sessions/overview', { searchParams }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useSessionReportsEmployees = (params: {
  start: string
  end: string
  q?: string
  sort?: EmployeeSortField
  order?: SortOrder
  page?: number
  per_page?: number
  enabled?: boolean
}) => {
  const { start, end, q, sort, order, page, per_page, enabled } = params
  const searchParams: Record<string, string> = { start, end }
  if (q) searchParams.q = q
  if (sort) searchParams.sort = sort
  if (order) searchParams.order = order
  if (page) searchParams.page = String(page)
  if (per_page) searchParams.per_page = String(per_page)

  return useQuery({
    queryKey: ['session-reports', 'employees', start, end, q ?? '', sort ?? 'session_count', order ?? 'desc', page ?? 1, per_page ?? 20],
    queryFn: () =>
      get<EmployeesListResponse>('v1/reports/sessions/employees', { searchParams }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useSessionReportEmployeeDetail = (
  params: CommonParams & { employee_id: number }
) => {
  const { start, end, employee_id, enabled } = params
  return useQuery({
    queryKey: ['session-reports', 'employees', 'detail', start, end, employee_id],
    queryFn: () =>
      get<EmployeeDetailResponse>(`v1/reports/sessions/employees/${employee_id}`, {
        searchParams: { start, end },
      }),
    enabled: !!start && !!end && Number.isFinite(employee_id) && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useSessionReportEmployeeTrend = (
  params: CommonParams & { employee_id: number; trend: TrendType }
) => {
  const { start, end, trend, employee_id, enabled } = params
  return useQuery({
    queryKey: ['session-reports', 'employees', 'trend', start, end, trend, employee_id],
    queryFn: () =>
      get<TrendResponse>(`v1/reports/sessions/employees/${employee_id}/trend`, {
        searchParams: { start, end, trend },
      }),
    enabled: !!start && !!end && Number.isFinite(employee_id) && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useSessionReportsTrend = (
  params: CommonParams & { trend: TrendType }
) => {
  const { start, end, trend, employee_id, enabled } = params
  const searchParams: Record<string, string> = { start, end, trend }
  if (employee_id !== undefined) searchParams.employee_id = String(employee_id)

  return useQuery({
    queryKey: ['session-reports', 'trend', start, end, trend, employee_id ?? null],
    queryFn: () =>
      get<TrendResponse>('v1/reports/sessions/trend', { searchParams }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useSessionReportsQueues = (params: {
  start: string
  end: string
  q?: string
  queue_type?: QueueType
  sort?: QueueSortField
  order?: SortOrder
  page?: number
  per_page?: number
  enabled?: boolean
}) => {
  const { start, end, q, queue_type, sort, order, page, per_page, enabled } = params
  const searchParams: Record<string, string> = { start, end }
  if (q) searchParams.q = q
  if (queue_type) searchParams.queue_type = queue_type
  if (sort) searchParams.sort = sort
  if (order) searchParams.order = order
  if (page) searchParams.page = String(page)
  if (per_page) searchParams.per_page = String(per_page)

  return useQuery({
    queryKey: [
      'session-reports',
      'queues',
      start,
      end,
      q ?? '',
      queue_type ?? 'all',
      sort ?? 'queued_session_count',
      order ?? 'desc',
      page ?? 1,
      per_page ?? 20,
    ],
    queryFn: () =>
      get<QueueListResponse>('v1/reports/sessions/queues', { searchParams }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useSessionReportQueueDetail = (params: {
  start: string
  end: string
  queue_type: QueueType
  queue_id: number
  enabled?: boolean
}) => {
  const { start, end, queue_type, queue_id, enabled } = params
  return useQuery({
    queryKey: ['session-reports', 'queues', 'detail', start, end, queue_type, queue_id],
    queryFn: () =>
      get<QueueDetailResponse>(`v1/reports/sessions/queues/${queue_type}/${queue_id}`, {
        searchParams: { start, end },
      }),
    enabled: !!start && !!end && Number.isFinite(queue_id) && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useSessionReportQueueTrend = (params: {
  start: string
  end: string
  trend: TrendType
  group: QueueMetricGroup
  queue_type: QueueType
  queue_id: number
  enabled?: boolean
}) => {
  const { start, end, trend, group, queue_type, queue_id, enabled } = params
  return useQuery({
    queryKey: ['session-reports', 'queues', 'trend', start, end, trend, group, queue_type, queue_id],
    queryFn: () =>
      get<QueueTrendResponse>(`v1/reports/sessions/queues/${queue_type}/${queue_id}/trend`, {
        searchParams: { start, end, trend, group },
      }),
    enabled: !!start && !!end && Number.isFinite(queue_id) && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const downloadSessionReportExport = async (params: SessionReportExportParams) => {
  const searchParams: Record<string, string> = {
    scope: params.scope,
    start: params.start,
    end: params.end,
  }
  if (params.trend) searchParams.trend = params.trend
  if (params.employee_id !== undefined) searchParams.employee_id = String(params.employee_id)
  if (params.q) searchParams.q = params.q
  if (params.sort) searchParams.sort = params.sort
  if (params.order) searchParams.order = params.order

  const { blob, headers } = await getBlob('v1/reports/sessions/export', { searchParams })
  return {
    blob,
    filename: filenameFromContentDisposition(headers.get('content-disposition')),
  }
}

export const useSessionReportExport = () =>
  useMutation({
    mutationFn: downloadSessionReportExport,
  })

export const downloadSessionQueueReportExport = async (params: QueueReportExportParams) => {
  const searchParams: Record<string, string> = {
    scope: params.scope,
    start: params.start,
    end: params.end,
  }
  if (params.trend) searchParams.trend = params.trend
  if (params.group) searchParams.group = params.group
  if (params.queue_type) searchParams.queue_type = params.queue_type
  if (params.queue_id !== undefined) searchParams.queue_id = String(params.queue_id)
  if (params.q) searchParams.q = params.q
  if (params.sort) searchParams.sort = params.sort
  if (params.order) searchParams.order = params.order

  const { blob, headers } = await getBlob('v1/reports/sessions/queues/export', { searchParams })
  return {
    blob,
    filename: filenameFromContentDisposition(headers.get('content-disposition')),
  }
}

export const useSessionQueueReportExport = () =>
  useMutation({
    mutationFn: downloadSessionQueueReportExport,
  })

function filenameFromContentDisposition(value: string | null): string {
  if (!value) return 'session-report.xlsx'

  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(value)
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1])
    } catch {
      return encoded[1]
    }
  }

  const quoted = /filename="([^"]+)"/i.exec(value)
  if (quoted?.[1]) return quoted[1]
  return 'session-report.xlsx'
}
