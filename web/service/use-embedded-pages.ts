import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './base'
import type {
  EmbeddedPage,
  EmbeddedPageListResponse,
  EmbeddedPageLocation,
  EmbeddedPageWorkspaceResponse,
  SaveEmbeddedPagePayload,
} from '@/models/embedded-page'

const NS = 'embedded-pages'

export const embeddedPageKeys = {
  all: [NS] as const,
  lists: () => [...embeddedPageKeys.all, 'list'] as const,
  list: (location: EmbeddedPageLocation) => [...embeddedPageKeys.lists(), location] as const,
  details: () => [...embeddedPageKeys.all, 'detail'] as const,
  detail: (id: number) => [...embeddedPageKeys.details(), id] as const,
  workspace: (location: EmbeddedPageLocation) => [...embeddedPageKeys.all, 'workspace', location] as const,
}

export const useEmbeddedPages = (location: EmbeddedPageLocation) =>
  useQuery({
    queryKey: embeddedPageKeys.list(location),
    queryFn: () =>
      get<EmbeddedPageListResponse>('v1/conversation-settings/embedded-pages', {
        searchParams: { location },
      }),
  })

export const useEmbeddedPage = (id: number) =>
  useQuery({
    queryKey: embeddedPageKeys.detail(id),
    queryFn: () => get<EmbeddedPage>(`v1/conversation-settings/embedded-pages/${id}`),
    enabled: !!id,
  })

export const useWorkspaceEmbeddedPages = (location: EmbeddedPageLocation) =>
  useQuery({
    queryKey: embeddedPageKeys.workspace(location),
    queryFn: () =>
      get<EmbeddedPageWorkspaceResponse>('v1/conversation-settings/embedded-pages/workspace', {
        searchParams: { location },
      }),
  })

export const useCreateEmbeddedPage = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: SaveEmbeddedPagePayload) =>
      post<EmbeddedPage>('v1/conversation-settings/embedded-pages', { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: embeddedPageKeys.all }),
  })
}

export const useUpdateEmbeddedPage = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: SaveEmbeddedPagePayload }) =>
      put<EmbeddedPage>(`v1/conversation-settings/embedded-pages/${id}`, { json: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: embeddedPageKeys.all }),
  })
}

export const useDeleteEmbeddedPage = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/conversation-settings/embedded-pages/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: embeddedPageKeys.all }),
  })
}
