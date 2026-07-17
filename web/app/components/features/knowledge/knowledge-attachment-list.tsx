'use client'

import { useState } from 'react'
import { IconDownload, IconFile, IconLoader2 } from '@tabler/icons-react'
import { toast } from 'sonner'
import type { KnowledgeDocumentAttachment } from '@/models/knowledge'
import { getKnowledgeAttachmentUrl } from '@/service/use-knowledge'
import { readKnowledgeError } from './knowledge-utils'

export function formatKnowledgeAttachmentSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

type KnowledgeAttachmentListProps = {
  attachments: KnowledgeDocumentAttachment[]
  isZh: boolean
  compact?: boolean
}

export function KnowledgeAttachmentList({ attachments, isZh, compact = false }: KnowledgeAttachmentListProps) {
  const [openingId, setOpeningId] = useState<number | null>(null)

  const openAttachment = async (attachment: KnowledgeDocumentAttachment) => {
    setOpeningId(attachment.id)
    try {
      const result = await getKnowledgeAttachmentUrl(attachment.id)
      const anchor = window.document.createElement('a')
      anchor.href = result.url
      anchor.target = '_blank'
      anchor.rel = 'noopener noreferrer'
      anchor.click()
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '打开附件失败' : 'Failed to open attachment'))
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <div className="space-y-2">
      {attachments.map((attachment) => (
        <button
          key={attachment.id}
          type="button"
          onClick={() => openAttachment(attachment)}
          disabled={openingId === attachment.id}
          className="flex w-full items-center gap-3 rounded-lg border border-[#E5E5E5] bg-white px-3 py-2.5 text-left transition-colors hover:bg-[#FAFAFA] disabled:opacity-60"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#F5F5F5] text-[#737373]">
            <IconFile size={17} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-[#1A1A1A]">{attachment.name}</span>
            {!compact && (
              <span className="mt-0.5 block text-xs text-[#999999]">
                {formatKnowledgeAttachmentSize(attachment.size)}
              </span>
            )}
          </span>
          {openingId === attachment.id ? (
            <IconLoader2 size={16} className="shrink-0 animate-spin text-[#737373]" />
          ) : (
            <IconDownload size={16} className="shrink-0 text-[#737373]" />
          )}
        </button>
      ))}
    </div>
  )
}
