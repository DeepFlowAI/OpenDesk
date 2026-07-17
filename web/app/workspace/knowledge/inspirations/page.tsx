'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  IconChevronLeft,
  IconChevronRight,
  IconSearch,
  IconX,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { hasPermission } from '@/utils/permissions'
import type { KnowledgeDirectoryNode, KnowledgeInspiration, KnowledgeInspirationStatus } from '@/models/knowledge'
import {
  useArchiveKnowledgeInspiration,
  useCreateKnowledgeDirectory,
  useDeleteKnowledgeDirectory,
  useDeleteKnowledgeInspiration,
  useKnowledgeDirectories,
  useKnowledgeInspirationCounts,
  useKnowledgeInspirations,
  useMoveKnowledgeDirectory,
  useUpdateKnowledgeDirectory,
} from '@/service/use-knowledge'
import { DirectoryModal } from '@/app/components/features/knowledge/directory-modal'
import { DirectorySidebar } from '@/app/components/features/knowledge/directory-sidebar'
import { InspirationTable } from '@/app/components/features/knowledge/inspiration-table'
import { readKnowledgeError } from '@/app/components/features/knowledge/knowledge-utils'
import { SessionDetailDrawer } from '@/app/components/features/session-records/session-detail-drawer'

const PER_PAGE = 20

type DirectoryModalState =
  | { mode: 'create'; parentId: number | null; directory?: null }
  | { mode: 'edit'; parentId?: null; directory: KnowledgeDirectoryNode }

type StatusFilter = KnowledgeInspirationStatus | null

function parsePositiveInt(value: string | null): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

function parseStatus(value: string | null): StatusFilter {
  if (value === 'pending' || value === 'archived' || value === 'document_created') return value
  return null
}

function statusLabel(status: StatusFilter, isZh: boolean): string {
  if (status === 'pending') return isZh ? '待处理' : 'Pending'
  if (status === 'archived') return isZh ? '已归档' : 'Archived'
  if (status === 'document_created') return isZh ? '已新建' : 'Document created'
  return isZh ? '全部' : 'All'
}

export default function KnowledgeInspirationsPage() {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const user = useAuthStore((state) => state.user)
  const router = useRouter()
  const searchParams = useSearchParams()

  const page = parsePositiveInt(searchParams.get('page')) ?? 1
  const query = searchParams.get('q') ?? ''
  const status = parseStatus(searchParams.get('status'))
  const [searchInput, setSearchInput] = useState(query)
  const [directoryModal, setDirectoryModal] = useState<DirectoryModalState | null>(null)
  const [directoryToDelete, setDirectoryToDelete] = useState<KnowledgeDirectoryNode | null>(null)
  const [inspirationToDelete, setInspirationToDelete] = useState<KnowledgeInspiration | null>(null)
  const [relatedRecordId, setRelatedRecordId] = useState<number | null>(null)

  const canViewInspirations = hasPermission(user, 'knowledge.workspace.inspiration.view')
  const canManageInspirations = hasPermission(user, 'knowledge.workspace.inspiration.manage')
  const canCreateDocument = hasPermission(user, 'knowledge.workspace.document.create')
  const canManageDirectory = hasPermission(user, 'knowledge.workspace.directory.manage')

  const { data: directoryData } = useKnowledgeDirectories()
  const directories = useMemo(() => directoryData?.items ?? [], [directoryData])
  const { data: countsData } = useKnowledgeInspirationCounts({ q: query }, { enabled: canViewInspirations })
  const inspirationsParams = useMemo(
    () => ({
      q: query,
      status,
      page,
      per_page: PER_PAGE,
    }),
    [page, query, status],
  )
  const { data: inspirationsData, isLoading: inspirationsLoading } = useKnowledgeInspirations(
    inspirationsParams,
    { enabled: canViewInspirations },
  )

  const createDirectory = useCreateKnowledgeDirectory()
  const updateDirectory = useUpdateKnowledgeDirectory()
  const moveDirectory = useMoveKnowledgeDirectory()
  const deleteDirectory = useDeleteKnowledgeDirectory()
  const archiveInspiration = useArchiveKnowledgeInspiration()
  const deleteInspiration = useDeleteKnowledgeInspiration()

  useEffect(() => {
    setSearchInput(query)
  }, [query])

  const updateQuery = (patch: { q?: string | null; status?: StatusFilter; page?: number | null }) => {
    const next = new URLSearchParams(searchParams.toString())
    if ('q' in patch) {
      const value = patch.q?.trim()
      if (value) next.set('q', value)
      else next.delete('q')
    }
    if ('status' in patch) {
      if (patch.status) next.set('status', patch.status)
      else next.delete('status')
    }
    if ('page' in patch) {
      if (patch.page && patch.page > 1) next.set('page', String(patch.page))
      else next.delete('page')
    }
    const qs = next.toString()
    router.replace(`/workspace/knowledge/inspirations${qs ? `?${qs}` : ''}`)
  }

  const handleSearch = (event: FormEvent) => {
    event.preventDefault()
    updateQuery({ q: searchInput, page: 1 })
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

  const handleMoveDirectory = async (
    directoryId: number,
    payload: { parent_id?: number | null; sort_order?: number | null },
  ) => {
    try {
      await moveDirectory.mutateAsync({ id: directoryId, payload })
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '调整目录失败' : 'Failed to reorder directory'))
    }
  }

  const buildCreateDocumentHref = (inspiration: KnowledgeInspiration) => {
    const next = new URLSearchParams(searchParams.toString())
    next.set('inspiration', String(inspiration.id))
    next.set('source', 'inspirations')
    const qs = next.toString()
    return `/workspace/knowledge/docs/new${qs ? `?${qs}` : ''}`
  }

  const filters: Array<{ status: StatusFilter; count: number }> = [
    { status: null, count: countsData?.total ?? 0 },
    { status: 'pending', count: countsData?.pending ?? 0 },
    { status: 'archived', count: countsData?.archived ?? 0 },
    { status: 'document_created', count: countsData?.document_created ?? 0 },
  ]

  return (
    <div className="flex h-full min-h-0 bg-white">
      <DirectorySidebar
        directories={directories}
        selectedDirectoryId={null}
        activeView="inspirations"
        canManage={canManageDirectory}
        canViewInspirations={canViewInspirations}
        pendingInspirations={countsData?.pending ?? 0}
        isZh={isZh}
        onSelect={(directoryId) => {
          const qs = directoryId ? `?directory=${directoryId}` : ''
          router.push(`/workspace/knowledge${qs}`)
        }}
        onSelectInspirations={() => undefined}
        onCreate={(parentId) => setDirectoryModal({ mode: 'create', parentId })}
        onEdit={(directory) => setDirectoryModal({ mode: 'edit', directory })}
        onDelete={setDirectoryToDelete}
        onMove={handleMoveDirectory}
      />

      <section className="flex min-w-0 flex-1 flex-col bg-white">
        <div className="flex h-16 shrink-0 items-center justify-between px-8">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-[#1A1A1A]">
              {isZh ? '知识灵感' : 'Knowledge inspirations'}
            </h1>
          </div>

          <form onSubmit={handleSearch} className="relative">
            <IconSearch size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#999999]" />
            <input
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              className="h-9 w-[280px] rounded-lg border border-[#E5E5E5] bg-white pl-9 pr-9 text-sm text-[#1A1A1A] outline-none transition-colors placeholder:text-[#999999] focus:border-[#1A1A1A]"
              placeholder={isZh ? '搜索知识灵感内容' : 'Search inspirations'}
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
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-8 py-6">
          {!canViewInspirations ? (
            <div className="rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] px-4 py-8 text-center text-sm text-[#737373]">
              {isZh ? '无权限查看知识灵感' : 'You do not have permission to view knowledge inspirations'}
            </div>
          ) : (
            <>
              <div className="mb-4 flex gap-2 overflow-x-auto">
                {filters.map((item) => {
                  const active = item.status === status
                  return (
                    <button
                      key={item.status ?? 'all'}
                      type="button"
                      onClick={() => updateQuery({ status: item.status, page: 1 })}
                      className={[
                        'inline-flex h-8 shrink-0 items-center gap-2 rounded-full border px-3 text-sm transition-colors',
                        active
                          ? 'border-[#1A1A1A] bg-[#1A1A1A] text-white'
                          : 'border-[#E5E5E5] bg-white text-[#404040] hover:bg-[#F5F5F5]',
                      ].join(' ')}
                    >
                      <span>{statusLabel(item.status, isZh)}</span>
                      <span
                        className={active
                          ? 'rounded-full bg-white/20 px-1.5 text-xs'
                          : 'rounded-full bg-[#F5F5F5] px-1.5 text-xs text-[#737373]'}
                      >
                        {item.count}
                      </span>
                    </button>
                  )
                })}
              </div>

              <InspirationTable
                inspirations={inspirationsData?.items ?? []}
                loading={inspirationsLoading}
                hasQuery={Boolean(query.trim())}
                canManage={canManageInspirations}
                canCreateDocument={canCreateDocument}
                isZh={isZh}
                onArchive={async (inspiration) => {
                  try {
                    await archiveInspiration.mutateAsync(inspiration.id)
                    toast.success(isZh ? '已归档知识灵感' : 'Knowledge inspiration archived')
                  } catch (error) {
                    toast.error(await readKnowledgeError(error, isZh ? '归档知识灵感失败' : 'Failed to archive inspiration'))
                  }
                }}
                onCreateDocument={(inspiration) => router.push(buildCreateDocumentHref(inspiration))}
                onOpenRelatedRecord={(inspiration) => {
                  if (inspiration.source_conversation_id) setRelatedRecordId(inspiration.source_conversation_id)
                }}
                onDelete={setInspirationToDelete}
              />

              {inspirationsData && inspirationsData.pages > 1 && (
                <div className="mt-4 flex items-center justify-end gap-2 text-sm text-[#737373]">
                  <span>
                    {inspirationsData.page} / {inspirationsData.pages}
                  </span>
                  <button
                    type="button"
                    disabled={inspirationsData.page <= 1}
                    onClick={() => updateQuery({ page: inspirationsData.page - 1 })}
                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#E5E5E5] text-[#737373] transition-colors hover:bg-[#F5F5F5] disabled:opacity-40"
                    title={isZh ? '上一页' : 'Previous'}
                  >
                    <IconChevronLeft size={16} />
                  </button>
                  <button
                    type="button"
                    disabled={inspirationsData.page >= inspirationsData.pages}
                    onClick={() => updateQuery({ page: inspirationsData.page + 1 })}
                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#E5E5E5] text-[#737373] transition-colors hover:bg-[#F5F5F5] disabled:opacity-40"
                    title={isZh ? '下一页' : 'Next'}
                  >
                    <IconChevronRight size={16} />
                  </button>
                </div>
              )}
            </>
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
            setDirectoryToDelete(null)
          } catch (error) {
            toast.error(await readKnowledgeError(error, isZh ? '删除目录失败' : 'Failed to delete directory'))
          }
        }}
      />

      <ConfirmDialog
        open={inspirationToDelete != null}
        title={isZh ? '删除知识灵感' : 'Delete knowledge inspiration'}
        message={isZh ? '确定删除以下知识灵感？删除后不可恢复。' : 'Are you sure you want to delete this knowledge inspiration? This action cannot be undone.'}
        itemName={inspirationToDelete?.content_plain}
        confirmLabel={isZh ? '确定删除' : 'Delete'}
        variant="destructive"
        loading={deleteInspiration.isPending}
        onCancel={() => setInspirationToDelete(null)}
        onConfirm={async () => {
          if (!inspirationToDelete) return
          try {
            await deleteInspiration.mutateAsync(inspirationToDelete.id)
            toast.success(isZh ? '已删除知识灵感' : 'Knowledge inspiration deleted')
            setInspirationToDelete(null)
          } catch (error) {
            toast.error(await readKnowledgeError(error, isZh ? '删除知识灵感失败' : 'Failed to delete inspiration'))
          }
        }}
      />

      {relatedRecordId && (
        <SessionDetailDrawer
          recordId={relatedRecordId}
          onClose={() => setRelatedRecordId(null)}
        />
      )}
    </div>
  )
}
