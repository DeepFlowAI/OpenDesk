import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { get } from '@/service/base'
import type { SortOrder, TrendType } from '@/models/call-report'
import type {
  CallQueueListResponse,
  CallQueueSortField,
  CallQueueSummaryResponse,
  CallQueueTrendResponse,
  CallQueueType,
  CallQueueTypeFilter,
} from '@/models/call-queue-report'

export const callQueueKeys = {
  all: ['call-reports', 'queues'] as const,
  list: (params: object) => [...callQueueKeys.all, 'list', params] as const,
  summary: (queueType: CallQueueType, queueId: number, start: string, end: string) =>
    [...callQueueKeys.all, 'summary', queueType, queueId, start, end] as const,
  trend: (
    queueType: CallQueueType,
    queueId: number,
    start: string,
    end: string,
    trend: TrendType,
    group: string,
  ) => [...callQueueKeys.all, 'trend', queueType, queueId, start, end, trend, group] as const,
}

export function useCallQueueList(params: {
  start: string
  end: string
  q?: string
  queueType?: CallQueueTypeFilter
  sort?: CallQueueSortField
  order?: SortOrder
  page?: number
  perPage?: number
  enabled?: boolean
}) {
  const {
    start,
    end,
    q,
    queueType = 'employee_group',
    sort = 'queue_entry_count',
    order = 'desc',
    page = 1,
    perPage = 20,
    enabled = true,
  } = params
  const searchParams = {
    start,
    end,
    q: q || undefined,
    queue_type: queueType,
    sort,
    order,
    page: String(page),
    per_page: String(perPage),
  }
  return useQuery({
    queryKey: callQueueKeys.list(searchParams),
    queryFn: () => get<CallQueueListResponse>('v1/reports/calls/queues', { searchParams }),
    enabled: enabled && Boolean(start) && Boolean(end),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

export function useCallQueueSummary(params: {
  queueType: CallQueueType
  queueId: number
  start: string
  end: string
  enabled?: boolean
}) {
  const { queueType, queueId, start, end, enabled = true } = params
  return useQuery({
    queryKey: callQueueKeys.summary(queueType, queueId, start, end),
    queryFn: () =>
      get<CallQueueSummaryResponse>(
        `v1/reports/calls/queues/${queueType}/${queueId}/summary`,
        { searchParams: { start, end } },
      ),
    enabled: enabled && queueId > 0 && Boolean(start) && Boolean(end),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

export function useCallQueueTrend(params: {
  queueType: CallQueueType
  queueId: number
  start: string
  end: string
  trend: TrendType
  group: string
  enabled?: boolean
}) {
  const { queueType, queueId, start, end, trend, group, enabled = true } = params
  return useQuery({
    queryKey: callQueueKeys.trend(queueType, queueId, start, end, trend, group),
    queryFn: () =>
      get<CallQueueTrendResponse>(
        `v1/reports/calls/queues/${queueType}/${queueId}/trend`,
        { searchParams: { start, end, trend, group } },
      ),
    enabled: enabled && queueId > 0 && Boolean(start) && Boolean(end) && Boolean(group),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}
