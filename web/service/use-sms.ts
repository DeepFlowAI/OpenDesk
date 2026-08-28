import { useMutation, useQuery } from '@tanstack/react-query'
import { get, post } from './base'
import type {
  SmsSendPayload,
  SmsSendRecordDetail,
  SmsSendRecordListResponse,
  SmsSendResult,
  SmsSendSource,
  SmsSendStatus,
  SmsTemplateDetail,
  SmsTemplateListResponse,
  SmsWorkspaceTemplateListResponse,
} from '@/models/sms'

const NS = 'sms'

export interface SmsTemplateListParams {
  page?: number
  per_page?: number
  q?: string
}

function toSearchParams(params?: SmsTemplateListParams): Record<string, string | number> {
  if (!params) return {}
  return Object.fromEntries(
    Object.entries(params).filter(
      (entry): entry is [string, string | number] =>
        entry[1] !== undefined && entry[1] !== '',
    ),
  ) as Record<string, string | number>
}

export const smsQueryKeys = {
  all: [NS] as const,
  templates: (params: Record<string, unknown>) => [...smsQueryKeys.all, 'templates', params] as const,
  template: (id: number | null | undefined) => [...smsQueryKeys.all, 'template', id] as const,
  workspaceTemplates: () => [...smsQueryKeys.all, 'workspace-templates'] as const,
}

export const useSmsTemplates = (params?: SmsTemplateListParams, options?: { enabled?: boolean }) =>
  useQuery({
    queryKey: smsQueryKeys.templates((params ?? {}) as Record<string, unknown>),
    queryFn: () =>
      get<SmsTemplateListResponse>('v1/call-center/sms/templates', {
        searchParams: toSearchParams(params),
      }),
    enabled: options?.enabled ?? true,
  })

export const useSmsTemplate = (id: number | null | undefined) =>
  useQuery({
    queryKey: smsQueryKeys.template(id),
    queryFn: () => get<SmsTemplateDetail>(`v1/call-center/sms/templates/${id}`),
    enabled: typeof id === 'number',
  })

export const useSmsWorkspaceTemplates = (options?: { enabled?: boolean }) =>
  useQuery({
    queryKey: smsQueryKeys.workspaceTemplates(),
    queryFn: () => get<SmsWorkspaceTemplateListResponse>('v1/call-center/sms/workspace/templates'),
    enabled: options?.enabled ?? true,
    staleTime: 60_000,
  })

export const useSendSms = () =>
  useMutation({
    mutationFn: (payload: SmsSendPayload) =>
      post<SmsSendResult>('v1/call-center/sms/send', { json: payload }),
    retry: false,
  })

export interface SmsSendRecordListParams {
  page?: number
  per_page?: number
  q?: string
  status?: SmsSendStatus | ''
  source?: SmsSendSource | ''
}

export const useSmsSendRecords = (params?: SmsSendRecordListParams) =>
  useQuery({
    queryKey: [...smsQueryKeys.all, 'records', (params ?? {}) as Record<string, unknown>] as const,
    queryFn: () =>
      get<SmsSendRecordListResponse>('v1/call-center/sms/records', {
        searchParams: toSearchParams(params),
      }),
    placeholderData: (prev) => prev,
  })

export const useSmsSendRecord = (id: number | null | undefined) =>
  useQuery({
    queryKey: [...smsQueryKeys.all, 'record', id] as const,
    queryFn: () => get<SmsSendRecordDetail>(`v1/call-center/sms/records/${id}`),
    enabled: typeof id === 'number',
  })
