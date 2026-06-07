import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  CreateTicketWorkflowPayload,
  GraphValidationResult,
  TicketWorkflow,
  TicketWorkflowListResponse,
  TicketWorkflowVersionDetail,
  TicketWorkflowVersionListResponse,
  UpdateTicketWorkflowPayload,
} from '@/models/ticket-workflow'
import type { TicketWorkflowGraph } from '@/models/ticket-workflow-graph'

const NS = 'ticket-workflows'

export const ticketWorkflowKeys = {
  all: [NS] as const,
  lists: () => [...ticketWorkflowKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...ticketWorkflowKeys.lists(), params] as const,
  details: () => [...ticketWorkflowKeys.all, 'detail'] as const,
  detail: (id: number) => [...ticketWorkflowKeys.details(), id] as const,
}

export const useTicketWorkflows = (params?: {
  page?: number
  per_page?: number
  keyword?: string
  include_deleted?: boolean
}) =>
  useQuery({
    queryKey: ticketWorkflowKeys.list(params ?? {}),
    queryFn: () =>
      get<TicketWorkflowListResponse>('v1/ticket-workflows', {
        searchParams: params as Record<string, string | number | boolean>,
      }),
  })

export const useTicketWorkflow = (id: number) =>
  useQuery({
    queryKey: ticketWorkflowKeys.detail(id),
    queryFn: () => get<TicketWorkflow>(`v1/ticket-workflows/${id}`),
    enabled: !!id,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })

export const useCreateTicketWorkflow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateTicketWorkflowPayload) =>
      post<TicketWorkflow>('v1/ticket-workflows', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ticketWorkflowKeys.lists() }),
  })
}

export const useUpdateTicketWorkflow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateTicketWorkflowPayload }) =>
      put<TicketWorkflow>(`v1/ticket-workflows/${id}`, { json: data }),
    onSuccess: (_, variables) => {
      qc.invalidateQueries({ queryKey: ticketWorkflowKeys.detail(variables.id) })
      qc.invalidateQueries({ queryKey: ticketWorkflowKeys.lists() })
    },
  })
}

export const useDeleteTicketWorkflow = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/ticket-workflows/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ticketWorkflowKeys.lists() }),
  })
}

export const useReorderTicketWorkflows = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: number[]) => post('v1/ticket-workflows/reorder', { json: { ids } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ticketWorkflowKeys.lists() }),
  })
}

export const useValidateTicketWorkflowGraph = (id: number) =>
  useMutation({
    mutationFn: (graph_json: TicketWorkflowGraph) =>
      post<GraphValidationResult>(`v1/ticket-workflows/${id}/validate`, { json: { graph_json } }),
  })

export const useTicketWorkflowVersions = (workflowId: number, enabled = true) =>
  useQuery({
    queryKey: [...ticketWorkflowKeys.detail(workflowId), 'versions'],
    queryFn: () =>
      get<TicketWorkflowVersionListResponse>(`v1/ticket-workflows/${workflowId}/versions`),
    enabled: enabled && !!workflowId,
  })

export const useTicketWorkflowVersion = (workflowId: number, versionNo: number | null) =>
  useQuery({
    queryKey: [...ticketWorkflowKeys.detail(workflowId), 'versions', versionNo],
    queryFn: () =>
      get<TicketWorkflowVersionDetail>(`v1/ticket-workflows/${workflowId}/versions/${versionNo}`),
    enabled: !!workflowId && !!versionNo,
  })

export const useRollbackTicketWorkflow = (workflowId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (versionNo: number) =>
      post<TicketWorkflow>(`v1/ticket-workflows/${workflowId}/rollback/${versionNo}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ticketWorkflowKeys.detail(workflowId) })
      qc.invalidateQueries({ queryKey: [...ticketWorkflowKeys.detail(workflowId), 'versions'] })
      qc.invalidateQueries({ queryKey: ticketWorkflowKeys.lists() })
    },
  })
}
