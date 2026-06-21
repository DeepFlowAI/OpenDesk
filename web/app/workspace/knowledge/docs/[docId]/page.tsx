'use client'

import { useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import {
  IconArrowLeft,
  IconEdit,
  IconTrash,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { SafeHtml } from '@/components/safe-html'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { cn } from '@/lib/utils'
import { hasPermission } from '@/utils/permissions'
import { useDeleteKnowledgeDocument, useKnowledgeDocument } from '@/service/use-knowledge'
import {
  buildKnowledgeReturnQuery,
  formatKnowledgeDate,
  formatKnowledgeValidity,
  knowledgeActorName,
  knowledgeDirectoryPath,
  knowledgeListHref,
  knowledgeStatusClass,
  knowledgeStatusLabel,
  readKnowledgeError,
} from '@/app/components/features/knowledge/knowledge-utils'

export default function KnowledgeDocumentReadPage() {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const user = useAuthStore((state) => state.user)
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const docId = Number(params.docId)
  const { data: document, isLoading } = useKnowledgeDocument(docId)
  const deleteDocument = useDeleteKnowledgeDocument()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const canEdit = hasPermission(user, 'knowledge.workspace.document.edit')
  const canDelete = hasPermission(user, 'knowledge.workspace.document.delete')
  const returnQuery = buildKnowledgeReturnQuery(searchParams)

  return (
    <div className="flex min-h-full flex-col bg-white">
      <div className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5E5] bg-white px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => router.push(knowledgeListHref(searchParams))}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
            title={isZh ? '返回' : 'Back'}
          >
            <IconArrowLeft size={20} />
          </button>
          <h1 className="truncate text-base font-semibold text-[#1A1A1A]">
            {isZh ? '文档详情' : 'Article Detail'}
          </h1>
        </div>

        {document && (
          <div className="flex items-center gap-2">
            {canEdit && (
              <button
                type="button"
                onClick={() => router.push(`/workspace/knowledge/docs/${document.id}/edit${returnQuery}`)}
                className="flex h-9 items-center gap-2 rounded-lg border border-[#E5E5E5] px-3 text-sm font-medium text-[#404040] transition-colors hover:bg-[#F5F5F5]"
              >
                <IconEdit size={16} />
                {isZh ? '编辑' : 'Edit'}
              </button>
            )}
            {canDelete && (
              <button
                type="button"
                onClick={() => setDeleteOpen(true)}
                className="flex h-9 items-center gap-2 rounded-lg border border-[#FECACA] px-3 text-sm font-medium text-[#DC2626] transition-colors hover:bg-[#FEF2F2]"
              >
                <IconTrash size={16} />
                {isZh ? '删除' : 'Delete'}
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-8">
        {isLoading ? (
          <div className="mx-auto max-w-[920px] space-y-5 rounded-lg border border-[#E5E5E5] bg-white px-12 py-10">
            <div className="h-8 w-2/3 animate-pulse rounded bg-[#F3F4F6]" />
            <div className="h-4 w-full animate-pulse rounded bg-[#F3F4F6]" />
            <div className="h-72 w-full animate-pulse rounded bg-[#F3F4F6]" />
          </div>
        ) : document ? (
          <article className="mx-auto max-w-[920px] rounded-lg border border-[#E5E5E5] bg-white px-12 py-10">
            <div className="mb-6 border-b border-[#E5E5E5] pb-6">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    'inline-flex h-6 items-center rounded-md px-2 text-xs font-medium',
                    knowledgeStatusClass(document.display_status),
                  )}
                >
                  {knowledgeStatusLabel(document.display_status, isZh)}
                </span>
                <span className="text-xs text-[#999999]">{knowledgeDirectoryPath(document)}</span>
              </div>
              <h2 className="text-2xl font-semibold leading-tight text-[#1A1A1A]">{document.title}</h2>
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-[#737373]">
                <span>{isZh ? '有效期' : 'Validity'}: {formatKnowledgeValidity(document.validity_type, document.valid_from, document.valid_to, isZh)}</span>
                <span>{isZh ? '更新人' : 'Editor'}: {knowledgeActorName(document)}</span>
                <span>{isZh ? '更新时间' : 'Updated'}: {formatKnowledgeDate(document.updated_at)}</span>
              </div>
            </div>
            <SafeHtml
              html={document.content_html}
              className={cn('text-sm leading-7 text-[#1A1A1A]', richTextListStyleClass)}
            />
          </article>
        ) : (
          <div className="mx-auto flex h-80 max-w-[920px] items-center justify-center rounded-lg border border-[#E5E5E5] text-sm text-[#737373]">
            {isZh ? '文档不存在或无权限访问' : 'Article not found or inaccessible'}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={deleteOpen}
        title={isZh ? '删除文档' : 'Delete Article'}
        message={isZh ? '删除后不可恢复。' : 'This cannot be undone.'}
        itemName={document?.title}
        confirmLabel={isZh ? '确定删除' : 'Delete'}
        variant="destructive"
        loading={deleteDocument.isPending}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={async () => {
          if (!document) return
          try {
            await deleteDocument.mutateAsync(document.id)
            toast.success(isZh ? '文档已删除' : 'Article deleted')
            router.push(knowledgeListHref(searchParams))
          } catch (error) {
            toast.error(await readKnowledgeError(error, isZh ? '删除文档失败' : 'Failed to delete article'))
          }
        }}
      />
    </div>
  )
}
