'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  IconChevronLeft,
  IconChevronRight,
  IconDownload,
  IconPlus,
  IconSearch,
  IconUpload,
  IconX,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { hasPermission } from '@/utils/permissions'
import type { KnowledgeDirectoryNode, KnowledgeDocument } from '@/models/knowledge'
import {
  exportKnowledgeDocuments,
  useCreateKnowledgeDirectory,
  useDeleteKnowledgeDirectory,
  useDeleteKnowledgeDocument,
  useKnowledgeDirectories,
  useKnowledgeDocuments,
  useMoveKnowledgeDirectory,
  useUpdateKnowledgeDirectory,
} from '@/service/use-knowledge'
import { DirectoryModal } from '@/app/components/features/knowledge/directory-modal'
import { DirectorySidebar } from '@/app/components/features/knowledge/directory-sidebar'
import { DocumentTable } from '@/app/components/features/knowledge/document-table'
import { KnowledgeImportModal } from '@/app/components/features/knowledge/knowledge-import-modal'
import {
  buildKnowledgeReturnQuery,
  findKnowledgeDirectory,
  readKnowledgeError,
} from '@/app/components/features/knowledge/knowledge-utils'

const PER_PAGE = 20

type DirectoryModalState =
  | { mode: 'create'; parentId: number | null; directory?: null }
  | { mode: 'edit'; parentId?: null; directory: KnowledgeDirectoryNode }

function parsePositiveInt(value: string | null): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename || 'download.xlsx'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

export default function KnowledgeWorkspacePage() {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const user = useAuthStore((state) => state.user)
  const router = useRouter()
  const searchParams = useSearchParams()

  const selectedDirectoryId = parsePositiveInt(searchParams.get('directory'))
  const page = parsePositiveInt(searchParams.get('page')) ?? 1
  const query = searchParams.get('q') ?? ''
  const [searchInput, setSearchInput] = useState(query)
  const [directoryModal, setDirectoryModal] = useState<DirectoryModalState | null>(null)
  const [directoryToDelete, setDirectoryToDelete] = useState<KnowledgeDirectoryNode | null>(null)
  const [documentToDelete, setDocumentToDelete] = useState<KnowledgeDocument | null>(null)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const canCreateDocument = hasPermission(user, 'knowledge.workspace.document.create')
  const canEditDocument = hasPermission(user, 'knowledge.workspace.document.edit')
  const canDeleteDocument = hasPermission(user, 'knowledge.workspace.document.delete')
  const canManageDirectory = hasPermission(user, 'knowledge.workspace.directory.manage')
  const canImportKnowledge = hasPermission(user, 'knowledge.workspace.import')
  const canExportKnowledge = hasPermission(user, 'knowledge.workspace.export')

  const { data: directoryData, isLoading: directoriesLoading } = useKnowledgeDirectories()
  const directories = useMemo(() => directoryData?.items ?? [], [directoryData])
  const selectedDirectory = useMemo(
    () => findKnowledgeDirectory(directories, selectedDirectoryId),
    [directories, selectedDirectoryId],
  )

  const documentsParams = useMemo(
    () => ({
      directory: selectedDirectoryId,
      q: query,
      page,
      per_page: PER_PAGE,
    }),
    [page, query, selectedDirectoryId],
  )
  const { data: documentsData, isLoading: documentsLoading } = useKnowledgeDocuments(documentsParams)

  const createDirectory = useCreateKnowledgeDirectory()
  const updateDirectory = useUpdateKnowledgeDirectory()
  const moveDirectory = useMoveKnowledgeDirectory()
  const deleteDirectory = useDeleteKnowledgeDirectory()
  const deleteDocument = useDeleteKnowledgeDocument()

  useEffect(() => {
    setSearchInput(query)
  }, [query])

  useEffect(() => {
    if (!selectedDirectoryId || directoriesLoading) return
    if (!selectedDirectory) updateQuery({ directory: null, page: 1 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [directoriesLoading, selectedDirectory, selectedDirectoryId])

  const updateQuery = (patch: { directory?: number | null; q?: string | null; page?: number | null }) => {
    const next = new URLSearchParams(searchParams.toString())
    if ('directory' in patch) {
      if (patch.directory) next.set('directory', String(patch.directory))
      else next.delete('directory')
    }
    if ('q' in patch) {
      const value = patch.q?.trim()
      if (value) next.set('q', value)
      else next.delete('q')
    }
    if ('page' in patch) {
      if (patch.page && patch.page > 1) next.set('page', String(patch.page))
      else next.delete('page')
    }
    const qs = next.toString()
    router.replace(`/workspace/knowledge${qs ? `?${qs}` : ''}`)
  }

  const handleSearch = (event: FormEvent) => {
    event.preventDefault()
    updateQuery({ q: searchInput, page: 1 })
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const result = await exportKnowledgeDocuments({ directory: selectedDirectoryId, q: query }, locale)
      triggerDownload(result.blob, result.filename)
      toast.success(isZh ? '已导出知识库' : 'Knowledge base exported')
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '导出知识库失败' : 'Failed to export knowledge base'))
    } finally {
      setExporting(false)
    }
  }

  const handleDirectorySubmit = async (payload: { name: string; parent_id?: number | null }) => {
    try {
      if (directoryModal?.mode === 'edit') {
        await updateDirectory.mutateAsync({ id: directoryModal.directory.id, payload })
        toast.success(isZh ? '目录已更新' : 'Directory updated')
      } else {
        await createDirectory.mutateAsync(payload)
        toast.success(isZh ? '目录已创建' : 'Directory created')
      }
      setDirectoryModal(null)
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '保存目录失败' : 'Failed to save directory'))
    }
  }

  const handleMoveDirectory = async (directoryId: number, payload: { parent_id?: number | null; sort_order?: number | null }) => {
    try {
      await moveDirectory.mutateAsync({ id: directoryId, payload })
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '调整目录失败' : 'Failed to reorder directory'))
    }
  }

  const returnQuery = buildKnowledgeReturnQuery(searchParams)

  return (
    <div className="flex h-full min-h-0 bg-white">
      <DirectorySidebar
        directories={directories}
        selectedDirectoryId={selectedDirectoryId}
        canManage={canManageDirectory}
        isZh={isZh}
        onSelect={(directoryId) => updateQuery({ directory: directoryId, page: 1 })}
        onCreate={(parentId) => setDirectoryModal({ mode: 'create', parentId })}
        onEdit={(directory) => setDirectoryModal({ mode: 'edit', directory })}
        onDelete={setDirectoryToDelete}
        onMove={handleMoveDirectory}
      />

      <section className="flex min-w-0 flex-1 flex-col bg-white">
        <div className="flex h-16 shrink-0 items-center justify-between px-8">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-[#1A1A1A]">
              {selectedDirectory?.name ?? (isZh ? '全部知识' : 'All Articles')}
            </h1>
          </div>

          <div className="flex items-center gap-3">
            <form onSubmit={handleSearch} className="relative">
              <IconSearch size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#999999]" />
              <input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                className="h-9 w-[280px] rounded-lg border border-[#E5E5E5] bg-white pl-9 pr-9 text-sm text-[#1A1A1A] outline-none transition-colors placeholder:text-[#999999] focus:border-[#1A1A1A]"
                placeholder={isZh ? '搜索文档标题或内容' : 'Search articles'}
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchInput('')
                    updateQuery({ q: null, page: 1 })
                  }}
                  className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[#999999] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                  title={isZh ? '清空' : 'Clear'}
                >
                  <IconX size={14} />
                </button>
              )}
            </form>
            {canImportKnowledge && (
              <button
                type="button"
                onClick={() => setImportModalOpen(true)}
                className="flex h-9 items-center gap-2 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm font-medium text-[#404040] transition-colors hover:bg-[#F5F5F5]"
              >
                <IconUpload size={16} />
                {isZh ? '导入' : 'Import'}
              </button>
            )}
            {canExportKnowledge && (
              <button
                type="button"
                onClick={handleExport}
                disabled={exporting}
                className="flex h-9 items-center gap-2 rounded-lg border border-[#E5E5E5] bg-white px-3 text-sm font-medium text-[#404040] transition-colors hover:bg-[#F5F5F5] disabled:opacity-60"
              >
                <IconDownload size={16} />
                {exporting ? (isZh ? '导出中...' : 'Exporting...') : (isZh ? '导出' : 'Export')}
              </button>
            )}
            {canCreateDocument && (
              <button
                type="button"
                onClick={() => router.push(`/workspace/knowledge/docs/new${returnQuery}`)}
                className="flex h-9 items-center gap-2 rounded-lg bg-[#1A1A1A] px-4 text-sm font-medium text-white transition-colors hover:bg-black/85"
              >
                <IconPlus size={16} />
                {isZh ? '新建文档' : 'New Article'}
              </button>
            )}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
          <DocumentTable
            documents={documentsData?.items ?? []}
            loading={documentsLoading}
            canEdit={canEditDocument}
            canDelete={canDeleteDocument}
            isZh={isZh}
            onRead={(document) => router.push(`/workspace/knowledge/docs/${document.id}${returnQuery}`)}
            onEdit={(document) => router.push(`/workspace/knowledge/docs/${document.id}/edit${returnQuery}`)}
            onDelete={setDocumentToDelete}
          />

          {documentsData && documentsData.pages > 1 && (
            <div className="mt-4 flex items-center justify-end gap-2 text-sm text-[#737373]">
              <span>
                {documentsData.page} / {documentsData.pages}
              </span>
              <button
                type="button"
                disabled={documentsData.page <= 1}
                onClick={() => updateQuery({ page: documentsData.page - 1 })}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#E5E5E5] text-[#737373] transition-colors hover:bg-[#F5F5F5] disabled:opacity-40"
                title={isZh ? '上一页' : 'Previous'}
              >
                <IconChevronLeft size={16} />
              </button>
              <button
                type="button"
                disabled={documentsData.page >= documentsData.pages}
                onClick={() => updateQuery({ page: documentsData.page + 1 })}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#E5E5E5] text-[#737373] transition-colors hover:bg-[#F5F5F5] disabled:opacity-40"
                title={isZh ? '下一页' : 'Next'}
              >
                <IconChevronRight size={16} />
              </button>
            </div>
          )}
        </div>
      </section>

      <DirectoryModal
        open={directoryModal != null}
        mode={directoryModal?.mode ?? 'create'}
        directories={directories}
        directory={directoryModal?.mode === 'edit' ? directoryModal.directory : null}
        initialParentId={directoryModal?.mode === 'create' ? directoryModal.parentId : null}
        loading={createDirectory.isPending || updateDirectory.isPending}
        isZh={isZh}
        onClose={() => setDirectoryModal(null)}
        onSubmit={handleDirectorySubmit}
      />

      <KnowledgeImportModal
        open={importModalOpen}
        locale={locale}
        onClose={() => setImportModalOpen(false)}
        onCompleted={() => undefined}
      />

      <ConfirmDialog
        open={directoryToDelete != null}
        title={isZh ? '删除目录' : 'Delete Directory'}
        message={isZh ? '仅空目录可删除，删除后不可恢复。' : 'Only empty directories can be deleted. This cannot be undone.'}
        itemName={directoryToDelete?.name}
        confirmLabel={isZh ? '确定删除' : 'Delete'}
        variant="destructive"
        loading={deleteDirectory.isPending}
        onCancel={() => setDirectoryToDelete(null)}
        onConfirm={async () => {
          if (!directoryToDelete) return
          try {
            await deleteDirectory.mutateAsync(directoryToDelete.id)
            toast.success(isZh ? '目录已删除' : 'Directory deleted')
            if (selectedDirectoryId === directoryToDelete.id) updateQuery({ directory: null, page: 1 })
            setDirectoryToDelete(null)
          } catch (error) {
            toast.error(await readKnowledgeError(error, isZh ? '删除目录失败' : 'Failed to delete directory'))
          }
        }}
      />

      <ConfirmDialog
        open={documentToDelete != null}
        title={isZh ? '删除文档' : 'Delete Article'}
        message={isZh ? '删除后不可恢复。' : 'This cannot be undone.'}
        itemName={documentToDelete?.title}
        confirmLabel={isZh ? '确定删除' : 'Delete'}
        variant="destructive"
        loading={deleteDocument.isPending}
        onCancel={() => setDocumentToDelete(null)}
        onConfirm={async () => {
          if (!documentToDelete) return
          try {
            await deleteDocument.mutateAsync(documentToDelete.id)
            toast.success(isZh ? '文档已删除' : 'Article deleted')
            setDocumentToDelete(null)
          } catch (error) {
            toast.error(await readKnowledgeError(error, isZh ? '删除文档失败' : 'Failed to delete article'))
          }
        }}
      />
    </div>
  )
}
