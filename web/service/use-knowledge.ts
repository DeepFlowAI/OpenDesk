import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, filenameFromContentDisposition, get, getBlob, patch, post, postForm, put } from './base'
import type {
  KnowledgeDirectoryListResponse,
  KnowledgeDirectoryMovePayload,
  KnowledgeDirectoryNode,
  KnowledgeDirectoryPayload,
  KnowledgeDocument,
  KnowledgeDocumentListParams,
  KnowledgeDocumentListResponse,
  KnowledgeDocumentPayload,
  KnowledgeImportExecuteResponse,
  KnowledgeImportPreviewResponse,
} from '@/models/knowledge'

const NS = 'knowledge'

export const knowledgeKeys = {
  all: [NS] as const,
  directories: () => [...knowledgeKeys.all, 'directories'] as const,
  documents: () => [...knowledgeKeys.all, 'documents'] as const,
  documentList: (params: KnowledgeDocumentListParams) => [...knowledgeKeys.documents(), params] as const,
  documentDetails: () => [...knowledgeKeys.all, 'documentDetail'] as const,
  documentDetail: (id: number | string) => [...knowledgeKeys.documentDetails(), id] as const,
}

function buildDocumentListQuery(params: KnowledgeDocumentListParams): string {
  const searchParams = new URLSearchParams()
  if (params.directory != null) searchParams.set('directory', String(params.directory))
  if (params.q?.trim()) searchParams.set('q', params.q.trim())
  if (params.display_status) searchParams.set('display_status', params.display_status)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.per_page) searchParams.set('per_page', String(params.per_page))
  const qs = searchParams.toString()
  return qs ? `?${qs}` : ''
}

function buildKnowledgeExportQuery(params: Pick<KnowledgeDocumentListParams, 'directory' | 'q'>, locale: string): string {
  const searchParams = new URLSearchParams()
  searchParams.set('locale', locale)
  if (params.directory != null) searchParams.set('directory', String(params.directory))
  if (params.q?.trim()) searchParams.set('q', params.q.trim())
  return `?${searchParams.toString()}`
}

export const useKnowledgeDirectories = () =>
  useQuery({
    queryKey: knowledgeKeys.directories(),
    queryFn: () => get<KnowledgeDirectoryListResponse>('v1/knowledge/directories'),
  })

export const useCreateKnowledgeDirectory = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: KnowledgeDirectoryPayload) =>
      post<KnowledgeDirectoryNode>('v1/knowledge/directories', { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
    },
  })
}

export const useUpdateKnowledgeDirectory = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: KnowledgeDirectoryPayload }) =>
      put<KnowledgeDirectoryNode>(`v1/knowledge/directories/${id}`, { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documentDetails() })
    },
  })
}

export const useMoveKnowledgeDirectory = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: KnowledgeDirectoryMovePayload }) =>
      patch<KnowledgeDirectoryNode>(`v1/knowledge/directories/${id}/move`, { json: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documentDetails() })
    },
  })
}

export const useDeleteKnowledgeDirectory = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/knowledge/directories/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
    },
  })
}

export const useKnowledgeDocuments = (params: KnowledgeDocumentListParams) =>
  useQuery({
    queryKey: knowledgeKeys.documentList(params),
    queryFn: () => get<KnowledgeDocumentListResponse>(`v1/knowledge/documents${buildDocumentListQuery(params)}`),
  })

export const downloadKnowledgeImportTemplate = async (locale: string) => {
  const { blob, headers } = await getBlob(`v1/knowledge/import/template?locale=${encodeURIComponent(locale)}`)
  return {
    blob,
    filename: filenameFromContentDisposition(
      headers.get('content-disposition'),
      'knowledge-import-template.xlsx',
    ),
  }
}

export const exportKnowledgeDocuments = async (
  params: Pick<KnowledgeDocumentListParams, 'directory' | 'q'>,
  locale: string,
) => {
  const { blob, headers } = await getBlob(`v1/knowledge/export${buildKnowledgeExportQuery(params, locale)}`, {
    timeout: 120000,
  })
  return {
    blob,
    filename: filenameFromContentDisposition(
      headers.get('content-disposition'),
      'knowledge-export.xlsx',
    ),
  }
}

export const previewKnowledgeImport = async (file: File, locale: string) => {
  const formData = new FormData()
  formData.append('file', file)
  return postForm<KnowledgeImportPreviewResponse>(
    `v1/knowledge/import/preview?locale=${encodeURIComponent(locale)}`,
    formData,
    120000,
  )
}

export const executeKnowledgeImport = async (previewToken: string) =>
  post<KnowledgeImportExecuteResponse>('v1/knowledge/import/execute', {
    json: { preview_token: previewToken },
    timeout: 120000,
  })

export const useExecuteKnowledgeImport = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: executeKnowledgeImport,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documentDetails() })
    },
  })
}

export const useKnowledgeDocument = (id: number | string | null | undefined) => {
  const documentId = Number(id)
  return useQuery({
    queryKey: knowledgeKeys.documentDetail(Number.isFinite(documentId) ? documentId : String(id ?? '')),
    queryFn: () => get<KnowledgeDocument>(`v1/knowledge/documents/${documentId}`),
    enabled: Number.isFinite(documentId) && documentId > 0,
  })
}

export const useCreateKnowledgeDocument = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: KnowledgeDocumentPayload) =>
      post<KnowledgeDocument>('v1/knowledge/documents', { json: payload }),
    onSuccess: (doc) => {
      qc.setQueryData(knowledgeKeys.documentDetail(doc.id), doc)
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
    },
  })
}

export const useUpdateKnowledgeDocument = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<KnowledgeDocumentPayload> }) =>
      put<KnowledgeDocument>(`v1/knowledge/documents/${id}`, { json: payload }),
    onSuccess: (doc) => {
      qc.setQueryData(knowledgeKeys.documentDetail(doc.id), doc)
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
    },
  })
}

export const useDeleteKnowledgeDocument = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => del(`v1/knowledge/documents/${id}`),
    onSuccess: (_data, id) => {
      qc.removeQueries({ queryKey: knowledgeKeys.documentDetail(id) })
      qc.invalidateQueries({ queryKey: knowledgeKeys.directories() })
      qc.invalidateQueries({ queryKey: knowledgeKeys.documents() })
    },
  })
}
