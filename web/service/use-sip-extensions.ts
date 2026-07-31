import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './base'
import type {
  BindableEmployee,
  CreateSipExtensionPayload,
  CreateSipExtensionResponse,
  SipExtension,
  SipExtensionListParams,
  SipExtensionListResponse,
  SipRegistrationSecret,
  UpdateSipExtensionPayload,
} from '@/models/sip-extension'

const NS = 'sip-extensions'

export const sipExtensionKeys = {
  all: [NS] as const,
  lists: () => [...sipExtensionKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...sipExtensionKeys.lists(), params] as const,
  registrationInfo: (id: number) => [...sipExtensionKeys.all, 'registration-info', id] as const,
}

export const useSipExtensions = (params?: SipExtensionListParams) =>
  useQuery({
    queryKey: sipExtensionKeys.list((params ?? {}) as Record<string, unknown>),
    queryFn: () =>
      get<SipExtensionListResponse>('v1/sip-extensions', { searchParams: cleanParams(params) }),
  })

export const useBindableEmployees = (
  keyword: string,
  enabled: boolean,
  forExtensionId?: number | null,
) =>
  useQuery({
    queryKey: [
      ...sipExtensionKeys.all,
      'bindable-employees',
      keyword,
      forExtensionId ?? null,
    ] as const,
    queryFn: () => {
      const searchParams: Record<string, string | number> = {}
      if (keyword) searchParams.keyword = keyword
      if (forExtensionId != null) searchParams.for_extension_id = forExtensionId
      return get<BindableEmployee[]>('v1/sip-extensions/bindable-employees', {
        searchParams: Object.keys(searchParams).length ? searchParams : undefined,
      })
    },
    enabled,
  })

export const useSipRegistrationInfo = (id: number | null) =>
  useQuery({
    queryKey: sipExtensionKeys.registrationInfo(id ?? 0),
    queryFn: () => get<SipRegistrationSecret>(`v1/sip-extensions/${id}/registration-info`),
    enabled: !!id,
  })

export const useCreateSipExtension = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateSipExtensionPayload) =>
      post<CreateSipExtensionResponse>('v1/sip-extensions', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sipExtensionKeys.lists() }),
  })
}

export const useUpdateSipExtension = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateSipExtensionPayload }) =>
      put<SipExtension>(`v1/sip-extensions/${id}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sipExtensionKeys.lists() }),
  })
}

export const useResetSipExtensionPassword = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      post<CreateSipExtensionResponse>(`v1/sip-extensions/${id}/reset-password`),
    onSuccess: () => qc.invalidateQueries({ queryKey: sipExtensionKeys.lists() }),
  })
}

export const useDisableSipExtension = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<SipExtension>(`v1/sip-extensions/${id}/disable`),
    onSuccess: () => qc.invalidateQueries({ queryKey: sipExtensionKeys.lists() }),
  })
}

export const useEnableSipExtension = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => post<SipExtension>(`v1/sip-extensions/${id}/enable`),
    onSuccess: () => qc.invalidateQueries({ queryKey: sipExtensionKeys.lists() }),
  })
}

function cleanParams(params?: SipExtensionListParams): Record<string, string | number> | undefined {
  if (!params) return undefined
  const result: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '' && value !== null) result[key] = value as string | number
  }
  return result
}
