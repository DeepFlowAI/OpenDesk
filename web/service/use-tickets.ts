import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del } from './base'
import type {
  Ticket,
  TicketChange,
  CreateTicketPayload,
  UpdateTicketPayload,
  TicketQueryPayload,
  TicketViewCountsResponse,
} from '@/models/ticket'
import type { TicketView } from '@/models/ticket-view'
import type { PaginatedResponse } from '@/models/common'
import type { FdFormLayout } from '@/models/form-layout'
import type { FdInteractionRule } from '@/models/interaction-rule'
import type {
  ViewGroupRequestPayload,
  ViewGroupResponse,
} from '@/models/view-group'

const NS = 'tickets'

export const ticketKeys = {
  all: [NS] as const,
  queries: () => [...ticketKeys.all, 'query'] as const,
  query: (params: TicketQueryPayload) => [...ticketKeys.queries(), params] as const,
  details: () => [...ticketKeys.all, 'detail'] as const,
  detail: (id: number) => [...ticketKeys.details(), id] as const,
  changes: (id: number, params: { page?: number; per_page?: number }) =>
    [...ticketKeys.detail(id), 'changes', params] as const,
  enabledViews: () => [...ticketKeys.all, 'enabledViews'] as const,
  viewCounts: () => [...ticketKeys.all, 'viewCounts'] as const,
  viewGroupsRoot: () => [...ticketKeys.all, 'viewGroups'] as const,
  viewGroups: (viewId: number, payload: ViewGroupRequestPayload) =>
    [...ticketKeys.viewGroupsRoot(), viewId, payload] as const,
}

export const useQueryTickets = (payload: TicketQueryPayload) =>
  useQuery({
    queryKey: ticketKeys.query(payload),
    queryFn: () => post<PaginatedResponse<Ticket>>('v1/tickets/query', { json: payload }),
  })

export const useUserRelatedTickets = (userId: number) =>
  useQuery({
    queryKey: ticketKeys.query({
      temp_conditions: [{ field_id: null, field_key: 'user_id', operator: 'eq', value: userId }],
      temp_condition_logic: 'and',
      sort_by: 'created_at',
      sort_order: 'desc',
      page: 1,
      per_page: 50,
    }),
    queryFn: () =>
      post<PaginatedResponse<Ticket>>('v1/tickets/query', {
        json: {
          temp_conditions: [{ field_id: null, field_key: 'user_id', operator: 'eq', value: userId }],
          temp_condition_logic: 'and',
          sort_by: 'created_at',
          sort_order: 'desc',
          page: 1,
          per_page: 50,
        },
      }),
    enabled: userId > 0,
  })

export const useTicket = (id: number) =>
  useQuery({
    queryKey: ticketKeys.detail(id),
    queryFn: () => get<Ticket>(`v1/tickets/${id}`),
    enabled: !!id,
  })

export const useTicketChanges = (
  id: number,
  params: { page?: number; per_page?: number } = {},
  enabled = true,
) =>
  useQuery({
    queryKey: ticketKeys.changes(id, params),
    queryFn: () =>
      get<PaginatedResponse<TicketChange>>(`v1/tickets/${id}/changes`, {
        searchParams: params,
      }),
    enabled: enabled && !!id,
  })

export const useCreateTicket = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTicketPayload) =>
      post<Ticket>('v1/tickets', { json: data }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ticketKeys.queries() })
      qc.invalidateQueries({ queryKey: ticketKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: ticketKeys.viewGroupsRoot() })
    },
  })
}

export const useUpdateTicket = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateTicketPayload }) =>
      put<Ticket>(`v1/tickets/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ticketKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: [...ticketKeys.detail(v.id), 'changes'] })
      qc.invalidateQueries({ queryKey: ticketKeys.queries() })
      qc.invalidateQueries({ queryKey: ticketKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: ticketKeys.viewGroupsRoot() })
    },
  })
}

export const useDeleteTicket = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      await del(`v1/tickets/${id}`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ticketKeys.queries() })
      qc.invalidateQueries({ queryKey: ticketKeys.viewCounts() })
      qc.invalidateQueries({ queryKey: ticketKeys.viewGroupsRoot() })
    },
  })
}

export const useEnabledTicketViews = () =>
  useQuery({
    queryKey: ticketKeys.enabledViews(),
    queryFn: () => get<TicketView[]>('v1/tickets/views/enabled'),
  })

export const useTicketViewCounts = () =>
  useQuery({
    queryKey: ticketKeys.viewCounts(),
    queryFn: () => get<TicketViewCountsResponse>('v1/tickets/views/counts'),
  })

export const useTicketViewGroups = (
  viewId: number | null,
  payload: ViewGroupRequestPayload,
  enabled: boolean,
) =>
  useQuery({
    queryKey: ticketKeys.viewGroups(viewId ?? -1, payload),
    queryFn: () =>
      post<ViewGroupResponse>(`v1/tickets/views/${viewId}/groups`, {
        json: payload,
      }),
    enabled: enabled && viewId != null,
    staleTime: 30_000,
  })

export const useFormLayoutByScene = (scene: string) =>
  useQuery({
    queryKey: ['form-layouts', 'scene', scene],
    queryFn: () => get<FdFormLayout>(`v1/form-layouts/by-scene/${scene}`),
    enabled: !!scene,
  })

export const useInteractionRules = (layoutId: number | undefined) =>
  useQuery({
    queryKey: ['interaction-rules', layoutId],
    queryFn: () =>
      get<PaginatedResponse<FdInteractionRule>>(
        `v1/form-layouts/${layoutId}/interaction-rules`,
        { searchParams: { per_page: 200 } },
      ),
    enabled: !!layoutId,
  })
