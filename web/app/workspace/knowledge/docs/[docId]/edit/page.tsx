'use client'

import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { hasPermission } from '@/utils/permissions'
import {
  useKnowledgeDirectories,
  useKnowledgeDocument,
  useUpdateKnowledgeDocument,
} from '@/service/use-knowledge'
import { KnowledgeDocumentForm } from '@/app/components/features/knowledge/document-form'
import {
  buildKnowledgeReturnQuery,
  knowledgeListHref,
  readKnowledgeError,
} from '@/app/components/features/knowledge/knowledge-utils'
import type { KnowledgeDocumentPayload } from '@/models/knowledge'

export default function EditKnowledgeDocumentPage() {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const user = useAuthStore((state) => state.user)
  const router = useRouter()
  const params = useParams()
  const searchParams = useSearchParams()
  const docId = Number(params.docId)
  const canEdit = hasPermission(user, 'knowledge.workspace.document.edit')
  const { data: directoryData } = useKnowledgeDirectories()
  const { data: document, isLoading } = useKnowledgeDocument(docId)
  const updateDocument = useUpdateKnowledgeDocument()
  const returnQuery = buildKnowledgeReturnQuery(searchParams)

  if (!canEdit) {
    return (
      <div className="flex h-full items-center justify-center bg-white text-sm text-[#737373]">
        {isZh ? '无权限编辑文档' : 'You do not have permission to edit articles'}
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex min-h-full flex-col bg-white">
        <div className="h-14 border-b border-[#E5E5E5]" />
        <div className="flex-1 px-8 py-8">
          <div className="mx-auto max-w-[920px] space-y-5 rounded-lg border border-[#E5E5E5] px-12 py-8">
            <div className="h-10 w-full animate-pulse rounded bg-[#F3F4F6]" />
            <div className="h-10 w-1/2 animate-pulse rounded bg-[#F3F4F6]" />
            <div className="h-96 w-full animate-pulse rounded bg-[#F3F4F6]" />
          </div>
        </div>
      </div>
    )
  }

  if (!document) {
    return (
      <div className="flex h-full items-center justify-center bg-white text-sm text-[#737373]">
        {isZh ? '文档不存在或无权限访问' : 'Article not found or inaccessible'}
      </div>
    )
  }

  const handleSubmit = async (payload: KnowledgeDocumentPayload) => {
    try {
      await updateDocument.mutateAsync({ id: document.id, payload })
      toast.success(isZh ? '文档已保存' : 'Article saved')
      router.push(`/workspace/knowledge/docs/${document.id}${returnQuery}`)
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '保存文档失败' : 'Failed to save article'))
      throw error
    }
  }

  return (
    <KnowledgeDocumentForm
      mode="edit"
      directories={directoryData?.items ?? []}
      document={document}
      saving={updateDocument.isPending}
      isZh={isZh}
      onCancel={() => router.push(knowledgeListHref(searchParams))}
      onSubmit={handleSubmit}
    />
  )
}
