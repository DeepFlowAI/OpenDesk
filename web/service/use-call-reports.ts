import { useQuery } from '@tanstack/react-query'
import { get } from '@/service/base'
import type {
  CallEmployeeSortField,
  CallEmployeesListResponse,
  CallOverviewResponse,
  CallTrendResponse,
  SortOrder,
  TrendType,
} from '@/models/call-report'

type CommonParams = {
  start: string
  end: string
  employee_id?: number
  enabled?: boolean
}

export const useCallReportsOverview = (params: CommonParams) => {
  const { start, end, employee_id, enabled } = params
  const searchParams: Record<string, string> = { start, end }
  if (employee_id !== undefined) searchParams.employee_id = String(employee_id)

  return useQuery({
    queryKey: ['call-reports', 'overview', start, end, employee_id ?? null],
    queryFn: () =>
      get<CallOverviewResponse>('v1/reports/calls/overview', { searchParams }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useCallReportsTrend = (params: CommonParams & { trend: TrendType }) => {
  const { start, end, trend, employee_id, enabled } = params
  const searchParams: Record<string, string> = { start, end, trend }
  if (employee_id !== undefined) searchParams.employee_id = String(employee_id)

  return useQuery({
    queryKey: ['call-reports', 'trend', start, end, trend, employee_id ?? null],
    queryFn: () =>
      get<CallTrendResponse>('v1/reports/calls/trend', { searchParams }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useCallReportsEmployees = (params: {
  start: string
  end: string
  q?: string
  sort?: CallEmployeeSortField
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
    queryKey: [
      'call-reports',
      'employees',
      start,
      end,
      q ?? '',
      sort ?? 'total_calls',
      order ?? 'desc',
      page ?? 1,
      per_page ?? 20,
    ],
    queryFn: () =>
      get<CallEmployeesListResponse>('v1/reports/calls/employees', { searchParams }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}
