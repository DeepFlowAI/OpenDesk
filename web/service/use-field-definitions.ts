import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { get, post, put, del, patch } from './base'
import type {
  FdFieldDefinition,
  UnifiedField,
  FdFieldOption,
  FdTreeNode,
  CreateFdFieldDefinitionPayload,
  UpdateFdFieldDefinitionPayload,
  CreateFdFieldOptionPayload,
  UpdateFdFieldOptionPayload,
  CreateFdTreeNodePayload,
  UpdateFdTreeNodePayload,
  SortPayload,
  SystemFieldOverridePayload,
} from '@/models/field-definition'
import type { PaginatedResponse } from '@/models/common'

const NS = 'fieldDefinitions'

export type FieldDefinitionListParams = {
  domain?: string
  status?: string
  page?: number
  per_page?: number
}

export type UnifiedFieldListParams = {
  domain: string
  locale?: string
  include_metadata?: boolean
}

export const fieldDefinitionKeys = {
  all: [NS] as const,
  lists: () => [...fieldDefinitionKeys.all, 'list'] as const,
  list: (params: FieldDefinitionListParams) => [...fieldDefinitionKeys.lists(), params] as const,
  unified: (params: UnifiedFieldListParams) => [...fieldDefinitionKeys.all, 'unified', params] as const,
  details: () => [...fieldDefinitionKeys.all, 'detail'] as const,
  detail: (id: number) => [...fieldDefinitionKeys.details(), id] as const,
  options: (definitionId: number) => [...fieldDefinitionKeys.all, 'options', definitionId] as const,
  treeNodes: (definitionId: number) => [...fieldDefinitionKeys.all, 'treeNodes', definitionId] as const,
}

// ── Unified list (system + custom merged) ──

export const useUnifiedFields = (params: UnifiedFieldListParams) =>
  useQuery({
    queryKey: fieldDefinitionKeys.unified(params),
    queryFn: () =>
      get<PaginatedResponse<UnifiedField>>('v1/field-definitions/unified', {
        searchParams: params as unknown as Record<string, string>,
      }),
    enabled: !!params.domain,
  })

export const useUpdateSystemFieldOverride = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      domain,
      fieldKey,
      data,
    }: {
      domain: string
      fieldKey: string
      data: SystemFieldOverridePayload
    }) => patch<UnifiedField>(`v1/field-definitions/system/${domain}/${fieldKey}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: fieldDefinitionKeys.all }),
  })
}

// ── Field Definition CRUD (custom only) ──

export const useFieldDefinitions = (params?: FieldDefinitionListParams) =>
  useQuery({
    queryKey: fieldDefinitionKeys.list(params ?? {}),
    queryFn: () =>
      get<PaginatedResponse<FdFieldDefinition>>('v1/field-definitions', {
        searchParams: params as unknown as Record<string, string>,
      }),
  })

export const useFieldDefinition = (id: number) =>
  useQuery({
    queryKey: fieldDefinitionKeys.detail(id),
    queryFn: () => get<FdFieldDefinition>(`v1/field-definitions/${id}`),
    enabled: !!id,
  })

export const useCreateFieldDefinition = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateFdFieldDefinitionPayload) =>
      post<FdFieldDefinition>('v1/field-definitions', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: fieldDefinitionKeys.all }),
  })
}

export const useUpdateFieldDefinition = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateFdFieldDefinitionPayload }) =>
      put<FdFieldDefinition>(`v1/field-definitions/${id}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.detail(v.id) })
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.lists() })
    },
  })
}

export const useDeleteFieldDefinition = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/field-definitions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: fieldDefinitionKeys.lists() }),
  })
}

export const useSortFieldDefinitions = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ domain, data }: { domain: string; data: SortPayload }) =>
      put<{ message: string }>(`v1/field-definitions/sort?domain=${encodeURIComponent(domain)}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: fieldDefinitionKeys.all }),
  })
}

// ── Options CRUD ──

export const useFieldOptions = (definitionId: number) =>
  useQuery({
    queryKey: fieldDefinitionKeys.options(definitionId),
    queryFn: () => get<FdFieldOption[]>(`v1/field-definitions/${definitionId}/options`),
    enabled: !!definitionId,
  })

export const useCreateFieldOption = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ definitionId, data }: { definitionId: number; data: CreateFdFieldOptionPayload }) =>
      post<FdFieldOption>(`v1/field-definitions/${definitionId}/options`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.options(v.definitionId) })
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.detail(v.definitionId) })
    },
  })
}

export const useUpdateFieldOption = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      definitionId,
      optionId,
      data,
    }: {
      definitionId: number
      optionId: number
      data: UpdateFdFieldOptionPayload
    }) => put<FdFieldOption>(`v1/field-definitions/${definitionId}/options/${optionId}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.options(v.definitionId) })
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.detail(v.definitionId) })
    },
  })
}

export const useDeleteFieldOption = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ definitionId, optionId }: { definitionId: number; optionId: number }) =>
      del(`v1/field-definitions/${definitionId}/options/${optionId}`),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.options(v.definitionId) })
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.detail(v.definitionId) })
    },
  })
}

// ── Tree Nodes CRUD ──

export const useFieldTreeNodes = (definitionId: number) =>
  useQuery({
    queryKey: fieldDefinitionKeys.treeNodes(definitionId),
    queryFn: () => get<FdTreeNode[]>(`v1/field-definitions/${definitionId}/tree-nodes`),
    enabled: !!definitionId,
  })

export const useCreateFieldTreeNode = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ definitionId, data }: { definitionId: number; data: CreateFdTreeNodePayload }) =>
      post<FdTreeNode>(`v1/field-definitions/${definitionId}/tree-nodes`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.treeNodes(v.definitionId) })
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.detail(v.definitionId) })
    },
  })
}

export const useUpdateFieldTreeNode = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      definitionId,
      nodeId,
      data,
    }: {
      definitionId: number
      nodeId: number
      data: UpdateFdTreeNodePayload
    }) => put<FdTreeNode>(`v1/field-definitions/${definitionId}/tree-nodes/${nodeId}`, { json: data }),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.treeNodes(v.definitionId) })
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.detail(v.definitionId) })
    },
  })
}

export const useDeleteFieldTreeNode = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ definitionId, nodeId }: { definitionId: number; nodeId: number }) =>
      del(`v1/field-definitions/${definitionId}/tree-nodes/${nodeId}`),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.treeNodes(v.definitionId) })
      qc.invalidateQueries({ queryKey: fieldDefinitionKeys.detail(v.definitionId) })
    },
  })
}
