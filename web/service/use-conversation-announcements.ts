import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post, put } from './base'
import type {
  ConversationAnnouncement,
  ConversationAnnouncementListResponse,
  SaveConversationAnnouncementPayload,
} from '@/models/conversation-announcement'

const NS = 'conversation-announcements'

export const conversationAnnouncementKeys = {
  all: [NS] as const,
  lists: () => [...conversationAnnouncementKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...conversationAnnouncementKeys.lists(), params] as const,
  details: () => [...conversationAnnouncementKeys.all, 'detail'] as const,
  detail: (id: number) => [...conversationAnnouncementKeys.details(), id] as const,
}

export const useConversationAnnouncements = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: conversationAnnouncementKeys.list(params ?? {}),
    queryFn: () =>
      get<ConversationAnnouncementListResponse>('v1/conversation-settings/announcements', {
        searchParams: params as Record<string, string | number>,
      }),
  })

export const useConversationAnnouncement = (id: number) =>
  useQuery({
    queryKey: conversationAnnouncementKeys.detail(id),
    queryFn: () => get<ConversationAnnouncement>(`v1/conversation-settings/announcements/${id}`),
    enabled: !!id,
  })

export const useCreateConversationAnnouncement = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SaveConversationAnnouncementPayload) =>
      post<ConversationAnnouncement>('v1/conversation-settings/announcements', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: conversationAnnouncementKeys.lists() }),
  })
}

export const useUpdateConversationAnnouncement = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: SaveConversationAnnouncementPayload }) =>
      put<ConversationAnnouncement>(`v1/conversation-settings/announcements/${id}`, { json: data }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: conversationAnnouncementKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: conversationAnnouncementKeys.lists() })
    },
  })
}

export const usePatchConversationAnnouncementEnabled = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      patch<ConversationAnnouncement>(`v1/conversation-settings/announcements/${id}`, { json: { enabled } }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: conversationAnnouncementKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: conversationAnnouncementKeys.lists() })
    },
  })
}

export const useDeleteConversationAnnouncement = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/conversation-settings/announcements/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: conversationAnnouncementKeys.lists() }),
  })
}

export const useReorderConversationAnnouncements = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ordered_ids: number[]) =>
      put('v1/conversation-settings/announcements/reorder', { json: { ordered_ids } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: conversationAnnouncementKeys.lists() }),
  })
}
