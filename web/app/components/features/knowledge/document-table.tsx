'use client'

import {
  IconEdit,
  IconEye,
  IconFileText,
  IconTrash,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { KnowledgeDocument } from '@/models/knowledge'
import {
  formatKnowledgeDate,
  formatKnowledgeValidity,
  knowledgeActorName,
  knowledgeDirectoryPath,
  knowledgeStatusClass,
  knowledgeStatusLabel,
} from './knowledge-utils'

type DocumentTableProps = {
  documents: KnowledgeDocument[]
  loading: boolean
  canEdit: boolean
  canDelete: boolean
  isZh: boolean
  onRead: (document: KnowledgeDocument) => void
  onEdit: (document: KnowledgeDocument) => void
  onDelete: (document: KnowledgeDocument) => void
}

export function DocumentTable({
  documents,
  loading,
  canEdit,
  canDelete,
  isZh,
  onRead,
  onEdit,
  onDelete,
}: DocumentTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#E5E5E5] bg-white">
      <div className="grid h-11 grid-cols-[minmax(260px,1fr)_120px_72px_130px_110px_80px_88px] items-center border-b border-[#E5E5E5] bg-[#FAFAFA] px-4 text-xs font-medium text-[#737373]">
        <div>{isZh ? '标题' : 'Title'}</div>
        <div>{isZh ? '目录' : 'Directory'}</div>
        <div>{isZh ? '状态' : 'Status'}</div>
        <div>{isZh ? '有效期' : 'Validity'}</div>
        <div>{isZh ? '更新时间' : 'Updated'}</div>
        <div>{isZh ? '更新人' : 'Editor'}</div>
        <div className="text-right">{isZh ? '操作' : 'Actions'}</div>
      </div>

      {loading ? (
        <div className="space-y-0">
          {Array.from({ length: 5 }).map((_, index) => (
            <div
              key={index}
              className="grid h-14 grid-cols-[minmax(260px,1fr)_120px_72px_130px_110px_80px_88px] items-center border-b border-[#F0F0F0] px-4 last:border-b-0"
            >
              {Array.from({ length: 7 }).map((__, cellIndex) => (
                <div key={cellIndex} className="h-4 w-3/4 animate-pulse rounded bg-[#F3F4F6]" />
              ))}
            </div>
          ))}
        </div>
      ) : documents.length === 0 ? (
        <div className="flex h-64 flex-col items-center justify-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#F5F5F5] text-[#999999]">
            <IconFileText size={24} />
          </div>
          <p className="text-sm text-[#737373]">{isZh ? '暂无文档' : 'No articles'}</p>
        </div>
      ) : (
        <div>
          {documents.map((document) => (
            <div
              key={document.id}
              className="grid h-14 grid-cols-[minmax(260px,1fr)_120px_72px_130px_110px_80px_88px] items-center border-b border-[#F0F0F0] px-4 text-sm last:border-b-0 hover:bg-[#FAFAFA]"
            >
              <button
                type="button"
                onClick={() => onRead(document)}
                className="min-w-0 truncate pr-3 text-left font-medium text-[#1A1A1A] hover:underline"
                title={document.title}
              >
                {document.title}
              </button>
              <div className="truncate pr-3 text-[#737373]" title={knowledgeDirectoryPath(document)}>
                {knowledgeDirectoryPath(document) || '-'}
              </div>
              <div>
                <span
                  className={cn(
                    'inline-flex h-6 items-center rounded-md px-2 text-xs font-medium',
                    knowledgeStatusClass(document.display_status),
                  )}
                >
                  {knowledgeStatusLabel(document.display_status, isZh)}
                </span>
              </div>
              <div
                className="truncate pr-3 text-xs text-[#737373]"
                title={formatKnowledgeValidity(document.validity_type, document.valid_from, document.valid_to, isZh)}
              >
                {formatKnowledgeValidity(document.validity_type, document.valid_from, document.valid_to, isZh)}
              </div>
              <div className="truncate pr-3 text-xs text-[#737373]" title={formatKnowledgeDate(document.updated_at)}>
                {formatKnowledgeDate(document.updated_at).slice(0, 16)}
              </div>
              <div className="truncate pr-3 text-[#737373]" title={knowledgeActorName(document)}>
                {knowledgeActorName(document)}
              </div>
              <div className="flex justify-end gap-1">
                <button
                  type="button"
                  onClick={() => onRead(document)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                  title={isZh ? '查看' : 'View'}
                >
                  <IconEye size={16} />
                </button>
                {canEdit && (
                  <button
                    type="button"
                    onClick={() => onEdit(document)}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                    title={isZh ? '编辑' : 'Edit'}
                  >
                    <IconEdit size={16} />
                  </button>
                )}
                {canDelete && (
                  <button
                    type="button"
                    onClick={() => onDelete(document)}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-[#DC2626] transition-colors hover:bg-[#FEF2F2]"
                    title={isZh ? '删除' : 'Delete'}
                  >
                    <IconTrash size={16} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
