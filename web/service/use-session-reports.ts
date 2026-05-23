import { useMutation, useQuery } from '@tanstack/react-query'
import { get, getBlob } from '@/service/base'
import type {
  EmployeeSortField,
  EmployeesListResponse,
  OverviewResponse,
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
