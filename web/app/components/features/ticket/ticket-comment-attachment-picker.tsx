'use client'

import { useCallback, useRef, useState } from 'react'
import { IconLoader2, IconPaperclip, IconX } from '@tabler/icons-react'

import { useUploadCustomFieldFile } from '@/service/use-upload'
import { cn } from '@/lib/utils'
import type { TicketCommentAttachment } from '@/models/ticket-comment'

const DEFAULT_MAX_COUNT = 10
const DEFAULT_MAX_SIZE_MB = 100

type Props = {
  value: TicketCommentAttachment[]
  onChange: (next: TicketCommentAttachment[]) => void
  disabled?: boolean
  isZh: boolean
  /** Hard cap on attachment count; mirrors `MAX_ATTACHMENTS_PER_COMMENT` server-side. */
  maxCount?: number
  /** Per-file size cap in MB. */
  maxSizeMb?: number
  className?: string
}

/**
 * Compact attachment picker for the comment composer — paperclip button +
 * inline chips, no dropzone surface (the comment box is already cramped).
 */
export function TicketCommentAttachmentPicker({
  value,
  onChange,
  disabled = false,
  isZh,
  maxCount = DEFAULT_MAX_COUNT,
  maxSizeMb = DEFAULT_MAX_SIZE_MB,
  className,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const upload = useUploadCustomFieldFile()

  const slotsLeft = Math.max(0, maxCount - value.length)
  const busy = upload.isPending
  const pickerDisabled = disabled || busy || slotsLeft === 0

  const triggerPick = useCallback(() => {
    if (pickerDisabled) return
    inputRef.current?.click()
  }, [pickerDisabled])

  const handleSelect = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? [])
      event.target.value = ''
      if (files.length === 0) return

      setError(null)
      if (files.length > slotsLeft) {
        setError(
          isZh
            ? `最多只能上传 ${maxCount} 个附件`
            : `Up to ${maxCount} attachments allowed`,
        )
        return
      }

      const maxBytes = maxSizeMb * 1024 * 1024
      const next: TicketCommentAttachment[] = [...value]
      for (const file of files) {
        if (file.size > maxBytes) {
          setError(
            isZh ? `文件过大: ${file.name}` : `File too large: ${file.name}`,
          )
          break
        }
        try {
          const meta = await upload.mutateAsync(file)
          next.push({
            url: meta.url,
            name: meta.name,
            size: meta.size,
            content_type: meta.content_type,
          })
        } catch {
          setError(
            isZh ? `上传失败: ${file.name}` : `Upload failed: ${file.name}`,
          )
          break
        }
      }
      onChange(next)
    },
    [isZh, maxCount, maxSizeMb, onChange, slotsLeft, upload, value],
  )

  const removeAt = useCallback(
    (index: number) => {
      const next = value.filter((_, i) => i !== index)
      onChange(next)
      setError(null)
    },
    [onChange, value],
  )

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={triggerPick}
          disabled={pickerDisabled}
          className={cn(
            'inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-border bg-white px-2 text-xs text-muted-foreground transition-colors',
            'hover:border-muted-foreground hover:text-foreground',
            pickerDisabled && 'cursor-not-allowed opacity-50 hover:border-border hover:text-muted-foreground',
          )}
          aria-label={isZh ? '添加附件' : 'Add attachments'}
        >
          {busy ? (
            <IconLoader2 size={14} className="animate-spin" />
          ) : (
            <IconPaperclip size={14} />
          )}
          <span>
            {busy
              ? (isZh ? '上传中...' : 'Uploading...')
              : (isZh ? '添加附件' : 'Add attachments')}
          </span>
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          onChange={handleSelect}
          disabled={pickerDisabled}
        />
        {value.length > 0 && (
          <span className="text-[11px] text-muted-foreground">
            {value.length}/{maxCount}
          </span>
        )}
      </div>

      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {value.map((file, idx) => (
            <li
              key={`${file.url}-${idx}`}
              className="inline-flex max-w-[220px] items-center gap-1 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs"
            >
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 truncate text-primary underline-offset-2 hover:underline"
                title={file.name}
              >
                {file.name}
              </a>
              <button
                type="button"
                disabled={disabled || busy}
                onClick={() => removeAt(idx)}
                className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
                aria-label={isZh ? '移除附件' : 'Remove attachment'}
              >
                <IconX size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="text-[11px] text-destructive">{error}</p>}
    </div>
  )
}
