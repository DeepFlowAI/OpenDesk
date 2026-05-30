import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from './base'
import type {
  TenantPhoneNumber,
  TenantPhoneNumberListResponse,
  UpdateTenantPhoneNumberTagsPayload,
} from '@/models/tenant-phone-number'

const NS = 'tenant-phone-numbers'

export interface TenantPhoneNumberListParams {
  page?: number
  per_page?: number
  q?: string
}

function toSearchParams(params?: TenantPhoneNumberListParams): Record<string, string | number> {
  if (!params) return {}
  return Object.fromEntries(
    Object.entries(params).filter(
      (entry): entry is [string, string | number] =>
        entry[1] !== undefined && entry[1] !== '',
    ),
  ) as Record<string, string | number>
}

export const tenantPhoneNumberKeys = {
  all: [NS] as const,
  lists: () => [...tenantPhoneNumberKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...tenantPhoneNumberKeys.lists(), params] as const,
  details: () => [...tenantPhoneNumberKeys.all, 'detail'] as const,
  detail: (id: string) => [...tenantPhoneNumberKeys.details(), id] as const,
}

export const useTenantPhoneNumbers = (params?: TenantPhoneNumberListParams) =>
  useQuery({
    queryKey: tenantPhoneNumberKeys.list((params ?? {}) as Record<string, unknown>),
    queryFn: () =>
      get<TenantPhoneNumberListResponse>('v1/call-center/phone-numbers', {
        searchParams: toSearchParams(params),
      }),
  })

export const useTenantPhoneNumber = (id: string, enabled = true) =>
  useQuery({
    queryKey: tenantPhoneNumberKeys.detail(id),
    queryFn: () => get<TenantPhoneNumber>(`v1/call-center/phone-numbers/${id}`),
    enabled: enabled && !!id,
  })

export const useUpdateTenantPhoneNumberTags = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string
      data: UpdateTenantPhoneNumberTagsPayload
    }) => put<TenantPhoneNumber>(`v1/call-center/phone-numbers/${id}/tags`, { json: data }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: tenantPhoneNumberKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: tenantPhoneNumberKeys.lists() })
    },
  })
}
