import { useMutation, useQuery } from '@tanstack/react-query'
import { get, getBlob } from '@/service/base'
import type { TrendType } from '@/models/session-report'
import type {
  OverallExportParams,
  OverallSummaryResponse,
  OverallTrendResponse,
} from '@/models/session-report-overall'

export const useOverallSummary = (params: { start: string; end: string; enabled?: boolean }) => {
  const { start, end, enabled } = params
  return useQuery({
    queryKey: ['session-reports', 'overall', 'summary', start, end],
    queryFn: () =>
      get<OverallSummaryResponse>('v1/reports/sessions/overall/summary', {
        searchParams: { start, end },
      }),
    enabled: !!start && !!end && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const useOverallTrend = (params: {
  start: string
  end: string
  trend: TrendType
  group: string
  enabled?: boolean
}) => {
  const { start, end, trend, group, enabled } = params
  return useQuery({
    queryKey: ['session-reports', 'overall', 'trend', start, end, trend, group],
    queryFn: () =>
      get<OverallTrendResponse>('v1/reports/sessions/overall/trend', {
        searchParams: { start, end, trend, group },
      }),
    enabled: !!start && !!end && !!group && (enabled ?? true),
    staleTime: 30_000,
  })
}

export const downloadOverallExport = async (params: OverallExportParams) => {
  const { blob, headers } = await getBlob('v1/reports/sessions/overall/export', {
    searchParams: { start: params.start, end: params.end, trend: params.trend },
  })
  return {
    blob,
    filename: filenameFromContentDisposition(headers.get('content-disposition')),
  }
}

export const useOverallExport = () =>
  useMutation({
    mutationFn: downloadOverallExport,
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
