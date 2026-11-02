import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  consoleDelete,
  consoleGet,
  consolePatch,
  consolePost,
  consolePut,
  readConsoleToken,
} from '@/service/tenant-console-client'
import type { PaginatedResponse } from '@/models/common'
import type {
  ConsoleLoginResponse,
  ConsoleTenant,
  ConsoleTenantCreatePayload,
  ConsoleTenantStatus,
  ConsoleTenantUpdatePayload,
  PhoneNumber,
  PhoneNumberBatchPayload,
  PhoneNumberBatchResult,
  PhoneNumberCreatePayload,
  PhoneNumberListParams,
  PhoneNumberUpdatePayload,
  SipTrunk,
  SipTrunkListParams,
  SipTrunkOption,
  SipTrunkPayload,
} from '@/models/tenant-console'

const NS = 'tenant-console'

export const tenantConsoleKeys = {
  all: [NS] as const,
  me: [NS, 'me'] as const,
  tenants: [NS, 'tenants'] as const,
  tenantList: (params: Record<string, unknown>) => [NS, 'tenants', 'list', params] as const,
  tenantOptions: [NS, 'tenants', 'options'] as const,
  tenant: (id: string) => [NS, 'tenants', 'detail', id] as const,
  trunks: [NS, 'sip-trunks'] as const,
  trunkList: (params: Record<string, unknown>) => [NS, 'sip-trunks', 'list', params] as const,
  trunkOptions: [NS, 'sip-trunks', 'options'] as const,
  trunk: (id: string) => [NS, 'sip-trunks', 'detail', id] as const,
  phones: [NS, 'phone-numbers'] as const,
  phoneList: (params: Record<string, unknown>) => [NS, 'phone-numbers', 'list', params] as const,
  phone: (id: string) => [NS, 'phone-numbers', 'detail', id] as const,
}

/** Drop empty filter values so they are not sent as `?q=`. */
export function compactParams<T extends object>(params: T): Record<string, string | number> {
  const result: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    result[key] = value as string | number
  }
  return result
}

// ── Auth ────────────────────────────────────────────────

export const useConsoleLogin = () =>
  useMutation({
    mutationFn: (data: { username: string; password: string }) =>
      consolePost<ConsoleLoginResponse>('v1/tenant-console/auth/login', { json: data }),
  })

export const useConsoleMe = () =>
  useQuery({
    queryKey: tenantConsoleKeys.me,
    queryFn: () => consoleGet<{ username: string }>('v1/tenant-console/auth/me'),
    enabled: typeof window !== 'undefined' && !!readConsoleToken(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

// ── Tenants ─────────────────────────────────────────────

export const useConsoleTenants = (params: { page: number; per_page: number }) =>
  useQuery({
    queryKey: tenantConsoleKeys.tenantList(params),
    queryFn: () =>
      consoleGet<PaginatedResponse<ConsoleTenant>>('v1/tenants', { searchParams: params }),
    placeholderData: keepPreviousData,
  })

const OPTIONS_PAGE_SIZE = 100
const OPTIONS_MAX_PAGES = 20

/** All tenants (paged through) for binding selectors. */
export const useConsoleTenantOptions = () =>
  useQuery({
    queryKey: tenantConsoleKeys.tenantOptions,
    queryFn: async () => {
      const items: ConsoleTenant[] = []
      for (let page = 1; page <= OPTIONS_MAX_PAGES; page += 1) {
        const res = await consoleGet<PaginatedResponse<ConsoleTenant>>('v1/tenants', {
          searchParams: { page, per_page: OPTIONS_PAGE_SIZE },
        })
        items.push(...res.items)
        if (page >= res.pages) break
      }
      return items
    },
    staleTime: 60 * 1000,
  })

export const useConsoleTenant = (id: string) =>
  useQuery({
    queryKey: tenantConsoleKeys.tenant(id),
    queryFn: () => consoleGet<ConsoleTenant>(`v1/tenants/${encodeURIComponent(id)}`),
    enabled: !!id,
  })

export const useCreateConsoleTenant = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ConsoleTenantCreatePayload) =>
      consolePost<ConsoleTenant>('v1/tenants', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.tenants }),
  })
}

export const useUpdateConsoleTenant = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ConsoleTenantUpdatePayload }) =>
      consolePut<ConsoleTenant>(`v1/tenants/${encodeURIComponent(id)}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.tenants }),
  })
}

export const useUpdateConsoleTenantStatus = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: ConsoleTenantStatus }) =>
      consolePatch<ConsoleTenant>(`v1/tenants/${encodeURIComponent(id)}/status`, {
        json: { status },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.tenants }),
  })
}

// ── SIP trunks ──────────────────────────────────────────

export const useSipTrunks = (params: SipTrunkListParams) =>
  useQuery({
    queryKey: tenantConsoleKeys.trunkList(params),
    queryFn: () =>
      consoleGet<PaginatedResponse<SipTrunk>>('v1/sip-trunks', {
        searchParams: compactParams(params),
      }),
    placeholderData: keepPreviousData,
  })

export const useSipTrunkOptions = () =>
  useQuery({
    queryKey: tenantConsoleKeys.trunkOptions,
    queryFn: () => consoleGet<SipTrunkOption[]>('v1/sip-trunks/options'),
    staleTime: 60 * 1000,
  })

export const useSipTrunk = (id: string) =>
  useQuery({
    queryKey: tenantConsoleKeys.trunk(id),
    queryFn: () => consoleGet<SipTrunk>(`v1/sip-trunks/${encodeURIComponent(id)}`),
    enabled: !!id,
  })

export const useCreateSipTrunk = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SipTrunkPayload) => consolePost<SipTrunk>('v1/sip-trunks', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.trunks }),
  })
}

export const useUpdateSipTrunk = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: SipTrunkPayload }) =>
      consolePut<SipTrunk>(`v1/sip-trunks/${encodeURIComponent(id)}`, { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tenantConsoleKeys.trunks })
      qc.invalidateQueries({ queryKey: tenantConsoleKeys.phones })
    },
  })
}

export const useDeleteSipTrunk = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => consoleDelete(`v1/sip-trunks/${encodeURIComponent(id)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: tenantConsoleKeys.trunks })
      qc.invalidateQueries({ queryKey: tenantConsoleKeys.phones })
    },
  })
}

// ── Phone numbers ───────────────────────────────────────

export const usePhoneNumbers = (params: PhoneNumberListParams) =>
  useQuery({
    queryKey: tenantConsoleKeys.phoneList(params),
    queryFn: () =>
      consoleGet<PaginatedResponse<PhoneNumber>>('v1/phone-numbers', {
        searchParams: compactParams(params),
      }),
    placeholderData: keepPreviousData,
  })

export const usePhoneNumber = (id: string) =>
  useQuery({
    queryKey: tenantConsoleKeys.phone(id),
    queryFn: () => consoleGet<PhoneNumber>(`v1/phone-numbers/${encodeURIComponent(id)}`),
    enabled: !!id,
  })

export const useCreatePhoneNumber = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: PhoneNumberCreatePayload) =>
      consolePost<PhoneNumber>('v1/phone-numbers', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.phones }),
  })
}

export const useUpdatePhoneNumber = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PhoneNumberUpdatePayload }) =>
      consolePut<PhoneNumber>(`v1/phone-numbers/${encodeURIComponent(id)}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.phones }),
  })
}

export const useBatchUpdatePhoneNumbers = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: PhoneNumberBatchPayload) =>
      consolePost<PhoneNumberBatchResult>('v1/phone-numbers/batch-update', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.phones }),
  })
}

export const useDeletePhoneNumber = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => consoleDelete(`v1/phone-numbers/${encodeURIComponent(id)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: tenantConsoleKeys.phones }),
  })
}
