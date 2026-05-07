import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  TicketView,
  CreateTicketViewPayload,
  UpdateTicketViewPayload,
  TicketViewSortPayload,
  TicketViewTogglePayload,
} from '@/models/ticket-view'
import type { PaginatedResponse } from '@/models/common'

const NS = 'ticketViews'

export const ticketViewKeys = {
  all: [NS] as const,
  lists: () => [...ticketViewKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...ticketViewKeys.lists(), params] as const,
  details: () => [...ticketViewKeys.all, 'detail'] as const,
  detail: (id: number) => [...ticketViewKeys.details(), id] as const,
}

export const useTicketViews = (params?: { page?: number; per_page?: number }) =>
  useQuery({
    queryKey: ticketViewKeys.list(params ?? {}),
    queryFn: () => get<PaginatedResponse<TicketView>>('v1/ticket-views', { searchParams: params }),
  })

export const useTicketView = (id: number) =>
  useQuery({
    queryKey: ticketViewKeys.detail(id),
    queryFn: () => get<TicketView>(`v1/ticket-views/${id}`),
    enabled: !!id,
  })

export const useCreateTicketView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTicketViewPayload) =>
      post<TicketView>('v1/ticket-views', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ticketViewKeys.lists() }),
  })
}

export const useUpdateTicketView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateTicketViewPayload }) =>
      put<TicketView>(`v1/ticket-views/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ticketViewKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: ticketViewKeys.lists() })
    },
  })
}

export const useDeleteTicketView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/ticket-views/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ticketViewKeys.lists() }),
  })
}

export const useToggleTicketView = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: TicketViewTogglePayload }) =>
      put<TicketView>(`v1/ticket-views/${id}/toggle`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ticketViewKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: ticketViewKeys.lists() })
    },
  })
}

export const useSortTicketViews = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TicketViewSortPayload) =>
      put<{ message: string }>('v1/ticket-views/sort', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ticketViewKeys.lists() }),
  })
}
