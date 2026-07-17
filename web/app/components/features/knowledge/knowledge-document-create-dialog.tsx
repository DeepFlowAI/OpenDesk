'use client'

import { useRef } from 'react'
import { toast } from 'sonner'

import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { KnowledgeDocumentForm } from '@/app/components/features/knowledge/document-form'
import { readKnowledgeError } from '@/app/components/features/knowledge/knowledge-utils'
import { useCreateKnowledgeDocument, useKnowledgeDirectories } from '@/service/use-knowledge'
import type { KnowledgeDocumentAttachment, KnowledgeDocumentPayload } from '@/models/knowledge'

type KnowledgeDocumentCreateDialogProps = {
  open: boolean
  initialContentHtml: string
  initialAttachments?: KnowledgeDocumentAttachment[]
  isZh: boolean
  onClose: () => void
}

export function KnowledgeDocumentCreateDialog({
  open,
  initialContentHtml,
  initialAttachments,
  isZh,
  onClose,
}: KnowledgeDocumentCreateDialogProps) {
  const requestCloseRef = useRef<(() => void) | null>(null)
  const directories = useKnowledgeDirectories({ enabled: open })
  const createDocument = useCreateKnowledgeDocument()

  const handleSubmit = async (payload: KnowledgeDocumentPayload) => {
    try {
      await createDocument.mutateAsync(payload)
      toast.success(isZh ? '已新建知识文档' : 'Knowledge document created')
      onClose()
    } catch (error) {
      const responseStatus = (error as { response?: { status?: number } }).response?.status
      if (responseStatus === 403) {
        toast.error(
          isZh
            ? '无权限新建知识文档'
            : 'You do not have permission to create knowledge documents',
        )
      } else {
        toast.error(await readKnowledgeError(
          error,
          isZh
            ? '新建知识文档失败，请重试'
            : 'Failed to create the knowledge document. Try again.',
        ))
      }
      throw error
    }
  }

  const requestClose = () => {
    if (createDocument.isPending) return
    if (requestCloseRef.current) requestCloseRef.current()
    else onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && requestClose()}>
      <DialogContent
        className="flex max-h-[calc(100vh-2rem)] max-w-[920px] flex-col gap-0 overflow-hidden p-0 sm:max-w-[920px]"
        showCloseButton={false}
      >
        <DialogTitle className="sr-only">
          {isZh ? '新建知识文档' : 'Create knowledge document'}
        </DialogTitle>
        <KnowledgeDocumentForm
          mode="create"
          presentation="dialog"
          directories={directories.data?.items ?? []}
          directoriesLoading={directories.isLoading}
          directoriesError={directories.isError}
          onRetryDirectories={() => void directories.refetch()}
          initialContentHtml={initialContentHtml}
          initialAttachments={initialAttachments}
          saving={createDocument.isPending}
          isZh={isZh}
          requestCloseRef={requestCloseRef}
          onCancel={onClose}
          onSubmit={handleSubmit}
        />
      </DialogContent>
    </Dialog>
  )
}
