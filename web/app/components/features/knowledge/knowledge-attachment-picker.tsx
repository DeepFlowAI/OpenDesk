'use client'

import { useRef, useState } from 'react'
import { IconFile, IconLoader2, IconPaperclip, IconTrash, IconUpload } from '@tabler/icons-react'
import { toast } from 'sonner'
import type { KnowledgeDocumentAttachment } from '@/models/knowledge'
import {
  deleteStagedKnowledgeAttachment,
  uploadKnowledgeAttachment,
} from '@/service/use-knowledge'
import { formatKnowledgeAttachmentSize } from './knowledge-attachment-list'
import { readKnowledgeError } from './knowledge-utils'

const MAX_ATTACHMENTS = 10
const MAX_FILE_SIZE = 100 * 1024 * 1024

type KnowledgeAttachmentPickerProps = {
  attachments: KnowledgeDocumentAttachment[]
  isZh: boolean
  disabled?: boolean
  onChange: (attachments: KnowledgeDocumentAttachment[]) => void
  onUploadingChange: (uploading: boolean) => void
}

export function KnowledgeAttachmentPicker({
  attachments,
  isZh,
  disabled = false,
  onChange,
  onUploadingChange,
}: KnowledgeAttachmentPickerProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploadingNames, setUploadingNames] = useState<string[]>([])
  const [removingId, setRemovingId] = useState<number | null>(null)

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return
    const selected = Array.from(files)
    if (attachments.length + selected.length > MAX_ATTACHMENTS) {
      toast.error(isZh ? `每篇文档最多添加 ${MAX_ATTACHMENTS} 个附件` : `Up to ${MAX_ATTACHMENTS} attachments are allowed`)
      if (inputRef.current) inputRef.current.value = ''
      return
    }
    const oversized = selected.find((file) => file.size > MAX_FILE_SIZE)
    if (oversized) {
      toast.error(isZh ? `${oversized.name} 超过 100 MB` : `${oversized.name} exceeds 100 MB`)
      if (inputRef.current) inputRef.current.value = ''
      return
    }

    let next = [...attachments]
    onUploadingChange(true)
    setUploadingNames(selected.map((file) => file.name))
    try {
      for (const file of selected) {
        try {
          const uploaded = await uploadKnowledgeAttachment(file)
          next = [...next, uploaded]
          onChange(next)
        } catch (error) {
          toast.error(await readKnowledgeError(error, isZh ? `${file.name} 上传失败` : `Failed to upload ${file.name}`))
        } finally {
          setUploadingNames((current) => current.filter((name) => name !== file.name))
        }
      }
    } finally {
      onUploadingChange(false)
      setUploadingNames([])
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const removeAttachment = async (attachment: KnowledgeDocumentAttachment) => {
    setRemovingId(attachment.id)
    try {
      if (attachment.document_id == null) {
        await deleteStagedKnowledgeAttachment(attachment.id)
      }
      onChange(attachments.filter((item) => item.id !== attachment.id))
    } catch (error) {
      toast.error(await readKnowledgeError(error, isZh ? '删除附件失败' : 'Failed to remove attachment'))
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-[#404040]">{isZh ? '附件' : 'Attachments'}</span>
        <span className="text-xs text-[#999999]">
          {attachments.length}/{MAX_ATTACHMENTS}
        </span>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => void handleFiles(event.target.files)}
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled || uploadingNames.length > 0 || attachments.length >= MAX_ATTACHMENTS}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-[#D4D4D4] bg-[#FAFAFA] px-4 py-4 text-sm text-[#525252] transition-colors hover:border-[#A3A3A3] hover:bg-[#F5F5F5] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploadingNames.length > 0 ? <IconLoader2 size={18} className="animate-spin" /> : <IconUpload size={18} />}
        {uploadingNames.length > 0
          ? (isZh ? '附件上传中' : 'Uploading attachments')
          : (isZh ? '选择文件' : 'Choose files')}
        <span className="text-xs text-[#999999]">{isZh ? '单个最大 100 MB' : '100 MB max each'}</span>
      </button>

      {(attachments.length > 0 || uploadingNames.length > 0) && (
        <div className="mt-3 space-y-2">
          {attachments.map((attachment) => (
            <div
              key={attachment.id}
              className="flex items-center gap-3 rounded-lg border border-[#E5E5E5] bg-white px-3 py-2.5"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#F5F5F5] text-[#737373]">
                <IconFile size={17} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-[#1A1A1A]">{attachment.name}</span>
                <span className="mt-0.5 block text-xs text-[#999999]">{formatKnowledgeAttachmentSize(attachment.size)}</span>
              </span>
              <button
                type="button"
                onClick={() => void removeAttachment(attachment)}
                disabled={disabled || removingId === attachment.id}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#737373] transition-colors hover:bg-[#FEF2F2] hover:text-[#DC2626] disabled:opacity-50"
                title={isZh ? '删除附件' : 'Remove attachment'}
              >
                {removingId === attachment.id ? <IconLoader2 size={16} className="animate-spin" /> : <IconTrash size={16} />}
              </button>
            </div>
          ))}
          {uploadingNames.map((name, index) => (
            <div
              key={`${name}-${index}`}
              className="flex items-center gap-3 rounded-lg border border-[#E5E5E5] bg-[#FAFAFA] px-3 py-2.5"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white text-[#737373]">
                <IconPaperclip size={17} />
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-[#525252]">{name}</span>
              <IconLoader2 size={16} className="shrink-0 animate-spin text-[#737373]" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
