import { useQuery } from '@tanstack/react-query'
import { get } from '@/service/base'
import type { CallMonitorResponse } from '@/models/call-monitor'

const AUTO_REFRESH_MS = 30_000

export const callMonitorKeys = {
  all: ['call-monitor'] as const,
}

export const useCallMonitor = (enabled = true) =>
  useQuery({
    queryKey: callMonitorKeys.all,
    queryFn: () => get<CallMonitorResponse>('v1/reports/call-monitor'),
    enabled,
    refetchInterval: AUTO_REFRESH_MS,
    refetchIntervalInBackground: false,
    staleTime: AUTO_REFRESH_MS - 1_000,
  })
