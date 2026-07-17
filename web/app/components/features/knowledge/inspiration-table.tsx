'use client'

import {
  IconArchive,
  IconBulb,
  IconFilePlus,
  IconMessages,
  IconTrash,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { KnowledgeInspiration, KnowledgeInspirationStatus } from '@/models/knowledge'
import { formatKnowledgeDate } from './knowledge-utils'

type InspirationTableProps = {
  inspirations: KnowledgeInspiration[]
  loading: boolean
  hasQuery: boolean
  canManage: boolean
  canCreateDocument: boolean
  isZh: boolean
  onArchive: (inspiration: KnowledgeInspiration) => void
  onCreateDocument: (inspiration: KnowledgeInspiration) => void
  onOpenRelatedRecord: (inspiration: KnowledgeInspiration) => void
  onDelete: (inspiration: KnowledgeInspiration) => void
}

function statusLabel(status: KnowledgeInspirationStatus, isZh: boolean): string {
  if (status === 'archived') return isZh ? '已归档' : 'Archived'
  if (status === 'document_created') return isZh ? '已新建' : 'Document created'
  return isZh ? '待处理' : 'Pending'
}

function statusClass(status: KnowledgeInspirationStatus): string {
  if (status === 'archived') return 'bg-[#F3F4F6] text-[#737373]'
  if (status === 'document_created') return 'bg-[#ECFDF5] text-[#047857]'
  return 'bg-[#FFFBEB] text-[#B45309]'
}

function actorName(inspiration: KnowledgeInspiration): string {
  return inspiration.created_by?.actor_name || '-'
}

export function InspirationTable({
  inspirations,
  loading,
  hasQuery,
  canManage,
  canCreateDocument,
  isZh,
  onArchive,
  onCreateDocument,
  onOpenRelatedRecord,
  onDelete,
}: InspirationTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E5E5E5] bg-white">
      <div className="grid h-11 grid-cols-[minmax(300px,1fr)_120px_110px_96px_120px] items-center border-b border-[#E5E5E5] bg-[#FAFAFA] px-4 text-xs font-medium text-[#737373]">
        <div>{isZh ? '内容' : 'Content'}</div>
        <div>{isZh ? '提交人' : 'Submitter'}</div>
        <div>{isZh ? '相关记录' : 'Related record'}</div>
        <div>{isZh ? '状态' : 'Status'}</div>
        <div className="text-right">{isZh ? '操作' : 'Actions'}</div>
      </div>

      {loading ? (
        <div className="space-y-0">
          {Array.from({ length: 5 }).map((_, index) => (
            <div
              key={index}
              className="grid h-14 grid-cols-[minmax(300px,1fr)_120px_110px_96px_120px] items-center border-b border-[#F0F0F0] px-4 last:border-b-0"
            >
              {Array.from({ length: 5 }).map((__, cellIndex) => (
                <div key={cellIndex} className="h-4 w-3/4 animate-pulse rounded bg-[#F3F4F6]" />
              ))}
            </div>
          ))}
        </div>
      ) : inspirations.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#F5F5F5] text-[#999999]">
            <IconBulb size={24} />
          </div>
          <p className="text-sm text-[#737373]">
            {hasQuery
              ? (isZh ? '未找到匹配的知识灵感' : 'No matching knowledge inspirations')
              : (isZh ? '暂无知识灵感' : 'No knowledge inspirations')}
          </p>
        </div>
      ) : (
        <div>
          {inspirations.map((inspiration) => {
            const isPending = inspiration.status === 'pending'
            return (
              <div
                key={inspiration.id}
                className="grid min-h-14 grid-cols-[minmax(300px,1fr)_120px_110px_96px_120px] items-center border-b border-[#F0F0F0] px-4 py-3 text-sm last:border-b-0 hover:bg-[#FAFAFA]"
              >
                <div className="min-w-0 pr-4">
                  <p className="line-clamp-2 text-[#1A1A1A]" title={inspiration.content_plain}>
                    {inspiration.content_plain || '-'}
                  </p>
                  <p className="mt-1 text-xs text-[#999999]">
                    {formatKnowledgeDate(inspiration.created_at).slice(0, 16)}
                  </p>
                </div>
                <div className="truncate pr-3 text-[#737373]" title={actorName(inspiration)}>
                  {actorName(inspiration)}
                </div>
                <div>
                  {inspiration.source_conversation_id ? (
                    <button
                      type="button"
                      onClick={() => onOpenRelatedRecord(inspiration)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-[#404040] transition-colors hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                      title={isZh ? '打开相关会话' : 'Open related conversation'}
                    >
                      <IconMessages size={15} />
                      {isZh ? '会话' : 'Session'}
                    </button>
                  ) : (
                    <span className="text-xs text-[#999999]">-</span>
                  )}
                </div>
                <div>
                  <span
                    className={cn(
                      'inline-flex h-6 items-center rounded-md px-2 text-xs font-medium',
                      statusClass(inspiration.status),
                    )}
                  >
                    {statusLabel(inspiration.status, isZh)}
                  </span>
                </div>
                <div className="flex justify-end gap-1">
                  {canManage && isPending && (
                    <button
                      type="button"
                      onClick={() => onArchive(inspiration)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                      title={isZh ? '归档' : 'Archive'}
                    >
                      <IconArchive size={16} />
                    </button>
                  )}
                  {canCreateDocument && isPending && (
                    <button
                      type="button"
                      onClick={() => onCreateDocument(inspiration)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                      title={isZh ? '新建知识' : 'Create article'}
                    >
                      <IconFilePlus size={16} />
                    </button>
                  )}
                  {canManage && (
                    <button
                      type="button"
                      onClick={() => onDelete(inspiration)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-[#DC2626] transition-colors hover:bg-[#FEF2F2]"
                      title={isZh ? '删除' : 'Delete'}
                    >
                      <IconTrash size={16} />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
