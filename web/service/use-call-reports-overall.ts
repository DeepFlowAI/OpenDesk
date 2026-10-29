import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { get } from '@/service/base'
import type { TrendType } from '@/models/call-report'
import type {
  CallOverallSummaryResponse,
  CallOverallTrendResponse,
} from '@/models/call-report-overall'

export const callOverallKeys = {
  all: ['call-reports', 'overall'] as const,
  summary: (start: string, end: string) =>
    [...callOverallKeys.all, 'summary', start, end] as const,
  trend: (start: string, end: string, trend: TrendType, group: string) =>
    [...callOverallKeys.all, 'trend', start, end, trend, group] as const,
}

export function useCallOverallSummary(params: {
  start: string
  end: string
  enabled?: boolean
}) {
  const { start, end, enabled = true } = params
  return useQuery({
    queryKey: callOverallKeys.summary(start, end),
    queryFn: () =>
      get<CallOverallSummaryResponse>('v1/reports/calls/overall/summary', {
        searchParams: { start, end },
      }),
    enabled: enabled && Boolean(start) && Boolean(end),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

export function useCallOverallTrend(params: {
  start: string
  end: string
  trend: TrendType
  group: string
  enabled?: boolean
}) {
  const { start, end, trend, group, enabled = true } = params
  return useQuery({
    queryKey: callOverallKeys.trend(start, end, trend, group),
    queryFn: () =>
      get<CallOverallTrendResponse>('v1/reports/calls/overall/trend', {
        searchParams: { start, end, trend, group },
      }),
    enabled: enabled && Boolean(start) && Boolean(end) && Boolean(group),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}
