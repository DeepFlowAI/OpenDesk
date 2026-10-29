import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { CallAgentListResponse, CallAgentSortField, CallAgentSummaryResponse, CallAgentTrendResponse } from '@/models/call-agent-report'
import type { SortOrder, TrendType } from '@/models/call-report'
import { get } from '@/service/base'

export const callAgentKeys = {
  all: ['call-reports', 'employees'] as const,
  list: (params: object) => [...callAgentKeys.all, 'list', params] as const,
  summary: (employeeId: number, start: string, end: string) =>
    [...callAgentKeys.all, 'summary', employeeId, start, end] as const,
  trend: (employeeId: number, start: string, end: string, trend: TrendType, group: string) =>
    [...callAgentKeys.all, 'trend', employeeId, start, end, trend, group] as const,
}

export function useCallAgentList(params: {
  start: string; end: string; q?: string; groupId?: number; status?: string
  sort?: CallAgentSortField; order?: SortOrder; page?: number; perPage?: number; enabled?: boolean
}) {
  const { start, end, q, groupId, status, sort = 'handled_call_count', order = 'desc', page = 1, perPage = 20, enabled = true } = params
  const searchParams = { start, end, q: q || undefined, group_id: groupId || undefined, status: status || undefined, sort, order, page, per_page: perPage }
  return useQuery({
    queryKey: callAgentKeys.list(searchParams),
    queryFn: () => get<CallAgentListResponse>('v1/reports/calls/employees', { searchParams }),
    enabled: enabled && Boolean(start) && Boolean(end),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

export function useCallAgentSummary(params: { employeeId: number; start: string; end: string; enabled?: boolean }) {
  const { employeeId, start, end, enabled = true } = params
  return useQuery({
    queryKey: callAgentKeys.summary(employeeId, start, end),
    queryFn: () => get<CallAgentSummaryResponse>(`v1/reports/calls/employees/${employeeId}/summary`, { searchParams: { start, end } }),
    enabled: enabled && employeeId > 0 && Boolean(start) && Boolean(end),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

export function useCallAgentTrend(params: { employeeId: number; start: string; end: string; trend: TrendType; group: string; enabled?: boolean }) {
  const { employeeId, start, end, trend, group, enabled = true } = params
  return useQuery({
    queryKey: callAgentKeys.trend(employeeId, start, end, trend, group),
    queryFn: () => get<CallAgentTrendResponse>(`v1/reports/calls/employees/${employeeId}/trend`, { searchParams: { start, end, trend, group } }),
    enabled: enabled && employeeId > 0 && Boolean(start) && Boolean(end) && Boolean(group),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}
