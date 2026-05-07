import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  SystemSettings,
  UpdateSystemSettingsPayload,
  UpdateOrganizationSettingsPayload,
} from '@/models/system-settings'

const NS = 'system-settings'

export const systemSettingsKeys = {
  all: [NS] as const,
  detail: () => [...systemSettingsKeys.all, 'detail'] as const,
}

export const useSystemSettings = () =>
  useQuery({
    queryKey: systemSettingsKeys.detail(),
    queryFn: () => get<SystemSettings>('v1/system-settings'),
  })

export const useUpdateSystemSettings = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UpdateSystemSettingsPayload) =>
      put<SystemSettings>('v1/system-settings', { json: data }),
    onSuccess: (data) => {
      qc.setQueryData(systemSettingsKeys.detail(), data)
    },
  })
}

export const useUpdateOrganizationSettings = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UpdateOrganizationSettingsPayload) =>
      put<SystemSettings>('v1/system-settings/organization', { json: data }),
    onSuccess: (data) => {
      qc.setQueryData(systemSettingsKeys.detail(), data)
    },
  })
}
