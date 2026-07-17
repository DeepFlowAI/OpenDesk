import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  AgentCurrentDevice,
  AgentDeviceListResponse,
  CallDeviceType,
} from '@/models/call-device'

const NS = 'agent-devices'

export const agentDeviceKeys = {
  all: [NS] as const,
  list: () => [...agentDeviceKeys.all, 'list'] as const,
  current: () => [...agentDeviceKeys.all, 'current'] as const,
}

export const useMyCallDevices = (options?: { enabled?: boolean; refetchInterval?: number }) =>
  useQuery({
    queryKey: agentDeviceKeys.list(),
    queryFn: () => get<AgentDeviceListResponse>('v1/call-center/agents/me/devices'),
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchInterval,
  })

export const useMyCurrentCallDevice = (options?: { enabled?: boolean }) =>
  useQuery({
    queryKey: agentDeviceKeys.current(),
    queryFn: () => get<AgentCurrentDevice>('v1/call-center/agents/me/current-device'),
    enabled: options?.enabled ?? true,
  })

export const useSetMyCurrentCallDevice = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (deviceType: CallDeviceType) =>
      put<AgentCurrentDevice>('v1/call-center/agents/me/current-device', {
        json: { device_type: deviceType },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentDeviceKeys.current() })
      qc.invalidateQueries({ queryKey: agentDeviceKeys.list() })
    },
  })
}
