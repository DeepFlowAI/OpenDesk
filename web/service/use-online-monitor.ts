import { useQuery } from '@tanstack/react-query'
import { get } from '@/service/base'
import type { OnlineMonitorResponse } from '@/models/online-monitor'

const AUTO_REFRESH_MS = 30_000

export const useOnlineMonitor = (enabled = true) =>
  useQuery({
    queryKey: ['online-monitor'],
    queryFn: () => get<OnlineMonitorResponse>('v1/reports/online-monitor'),
    enabled,
    refetchInterval: AUTO_REFRESH_MS,
    refetchIntervalInBackground: false,
    staleTime: AUTO_REFRESH_MS - 1_000,
  })
