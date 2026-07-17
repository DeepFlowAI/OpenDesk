'use client'

import { useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { hasPermission } from '@/utils/permissions'
import {
  useCreateKnowledgeDocument,
  useKnowledgeDirectories,
  useKnowledgeInspiration,
  useMarkKnowledgeInspirationDocumentCreated,
} from '@/service/use-knowledge'
import { KnowledgeDocumentForm } from '@/app/components/features/knowledge/document-form'
import {
  buildKnowledgeReturnQuery,
  knowledgeListHref,
  readKnowledgeError,
} from '@/app/components/features/knowledge/knowledge-utils'
import type { KnowledgeDocumentPayload } from '@/models/knowledge'

function parsePositiveInt(value: string | null): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default function NewKnowledgeDocumentPage() {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const user = useAuthStore((state) => state.user)
  const router = useRouter()
  const searchParams = useSearchParams()
  const canCreate = hasPermission(user, 'knowledge.workspace.document.create')
  const { data: directoryData } = useKnowledgeDirectories()
  const createDocument = useCreateKnowledgeDocument()
  const inspirationId = parsePositiveInt(searchParams.get('inspiration'))
  const { data: inspiration, isError: inspirationError } = useKnowledgeInspiration(inspirationId)
  const markInspirationDocumentCreated = useMarkKnowledgeInspirationDocumentCreated()
  const returnQuery = buildKnowledgeReturnQuery(searchParams)

  useEffect(() => {
    if (!inspirationId || !inspirationError) return
    toast.error(isZh ? '关联知识灵感不存在或无权访问' : 'Linked inspiration does not exist or is not accessible')
  }, [inspirationError, inspirationId, isZh])

  if (!canCreate) {
    return (
      <div className="flex h-full items-center justify-center bg-white text-sm text-[#737373]">
        {isZh ? '无权限新建文档' : 'You do not have permission to create articles'}
      </div>
    )
  }

  const handleSubmit = async (payload: KnowledgeDocumentPayload) => {
    try {
      const created = await createDocument.mutateAsync(payload)
      if (inspirationId) {
        try {
          await markInspirationDocumentCreated.mutateAsync(inspirationId)
        } catch {
          toast.error(isZh ? '关联知识灵感标记失败' : 'Failed to update linked inspiration')
        }
      }
      toast.success(isZh ? '文档已创建' : 'Article created')
      router.push(`/workspace/knowledge/docs/${created.id}${returnQuery}`)
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '创建文档失败' : 'Failed to create article'))
      throw error
    }
  }

  return (
    <KnowledgeDocumentForm
      mode="create"
      directories={directoryData?.items ?? []}
      initialDirectoryId={parsePositiveInt(searchParams.get('directory'))}
      initialContentHtml={inspiration?.content_html}
      saving={createDocument.isPending || markInspirationDocumentCreated.isPending}
      isZh={isZh}
      onCancel={() => router.push(knowledgeListHref(searchParams))}
      onSubmit={handleSubmit}
    />
  )
}
