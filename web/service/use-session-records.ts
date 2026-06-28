import { useQuery } from '@tanstack/react-query'
import { get } from './base'
import type {
  SessionRecordListResponse,
  SessionRecordDetail,
  SessionRecordMessageListResponse,
  SessionRecordFilters,
  ReceptionTrajectory,
} from '@/models/session-record'

const NS = 'session-records'

export const sessionRecordKeys = {
  all: [NS] as const,
  lists: () => [...sessionRecordKeys.all, 'list'] as const,
  list: (filters: SessionRecordFilters) => [...sessionRecordKeys.lists(), filters] as const,
  detail: (id: number) => [...sessionRecordKeys.all, 'detail', id] as const,
  messages: (id: number, afterId?: number) => [...sessionRecordKeys.all, 'messages', id, afterId] as const,
  receptionTrajectory: (id: number) => [...sessionRecordKeys.all, 'reception-trajectory', id] as const,
}

export const useSessionRecords = (filters: SessionRecordFilters) =>
  useQuery({
    queryKey: sessionRecordKeys.list(filters),
    queryFn: () => {
      const params: Record<string, string | number> = {
        page: filters.page,
        per_page: filters.per_page,
      }
      if (filters.start_date) params.start_date = filters.start_date
      if (filters.end_date) params.end_date = filters.end_date
      if (filters.agent_id) params.agent_id = filters.agent_id
      if (filters.visitor_id) params.visitor_id = filters.visitor_id
      if (filters.session_type) params.session_type = filters.session_type
      if (filters.has_queue !== undefined) params.has_queue = filters.has_queue ? 'true' : 'false'
      if (filters.keyword) params.keyword = filters.keyword
      if (filters.satisfaction_status) params.satisfaction_status = filters.satisfaction_status
      if (filters.satisfaction_resolved) params.satisfaction_resolved = filters.satisfaction_resolved
      if (filters.satisfaction_service_option) params.satisfaction_service_option = filters.satisfaction_service_option
      if (filters.satisfaction_service_label) params.satisfaction_service_label = filters.satisfaction_service_label
      if (filters.satisfaction_product_option) params.satisfaction_product_option = filters.satisfaction_product_option
      if (filters.satisfaction_product_label) params.satisfaction_product_label = filters.satisfaction_product_label
      return get<SessionRecordListResponse>('v1/session-records', { searchParams: params })
    },
  })

export const useSessionRecordDetail = (id: number) =>
  useQuery({
    queryKey: sessionRecordKeys.detail(id),
    queryFn: () => get<SessionRecordDetail>(`v1/session-records/${id}`),
    enabled: id > 0,
  })

export const useSessionRecordMessages = (id: number, afterId?: number) =>
  useQuery({
    queryKey: sessionRecordKeys.messages(id, afterId),
    queryFn: () =>
      get<SessionRecordMessageListResponse>(`v1/session-records/${id}/messages`, {
        searchParams: afterId ? { after_id: afterId, limit: 20 } : { limit: 20 },
      }),
    enabled: id > 0,
  })

export const useReceptionTrajectory = (id: number) =>
  useQuery({
    queryKey: sessionRecordKeys.receptionTrajectory(id),
    queryFn: () => get<ReceptionTrajectory>(`v1/session-records/${id}/reception-segments`),
    enabled: id > 0,
  })
