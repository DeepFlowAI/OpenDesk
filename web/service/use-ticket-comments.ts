import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './base'
import type { PaginatedResponse } from '@/models/common'
import type {
  CreateTicketCommentPayload,
  TicketComment,
} from '@/models/ticket-comment'

const NS = 'ticket-comments'

type ListParams = { page?: number; per_page?: number }

export const ticketCommentKeys = {
  all: [NS] as const,
  forTicket: (ticketId: number) => [...ticketCommentKeys.all, ticketId] as const,
  list: (ticketId: number, params: ListParams) =>
    [...ticketCommentKeys.forTicket(ticketId), params] as const,
}

export const useTicketComments = (
  ticketId: number,
  params: ListParams = {},
  enabled = true,
) =>
  useQuery({
    queryKey: ticketCommentKeys.list(ticketId, params),
    queryFn: () =>
      get<PaginatedResponse<TicketComment>>(`v1/tickets/${ticketId}/comments`, {
        searchParams: params,
      }),
    enabled: enabled && !!ticketId,
  })

export const useCreateTicketComment = (ticketId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTicketCommentPayload) =>
      post<TicketComment>(`v1/tickets/${ticketId}/comments`, { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ticketCommentKeys.forTicket(ticketId) })
    },
  })
}
