'use client'

import { useCallback, useMemo, useState } from 'react'
import { useDropzone, type Accept, type FileRejection } from 'react-dropzone'
import { IconLoader2, IconPaperclip, IconX } from '@tabler/icons-react'
import { useUploadCustomFieldFile } from '@/service/use-upload'
import { cn } from '@/lib/utils'

export type FieldFileAttachment = {
  url: string
  name: string
  size?: number
  content_type?: string | null
}

function normalizeFileValue(value: unknown): FieldFileAttachment[] {
  if (value == null) return []
  if (Array.isArray(value)) {
    return value.filter(
      (item): item is FieldFileAttachment =>
        !!item && typeof item === 'object' && typeof (item as FieldFileAttachment).url === 'string',
    )
  }
  if (typeof value === 'object' && value !== null && 'url' in value) {
    const o = value as FieldFileAttachment
    if (typeof o.url === 'string') return [o]
  }
  return []
}

/** Map admin "pdf,jpg" style config to react-dropzone Accept. */
function buildDropzoneAccept(allowed: string | null | undefined): Accept | undefined {
  if (!allowed || !String(allowed).trim()) return undefined
  const parts = String(allowed)
    .split(/[,，]/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean)
  if (parts.length === 0) return undefined

  const extToMime: Record<string, string> = {
    pdf: 'application/pdf',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    webp: 'image/webp',
    svg: 'image/svg+xml',
    txt: 'text/plain',
    csv: 'text/csv',
    md: 'text/markdown',
    json: 'application/json',
    xml: 'application/xml',
    zip: 'application/zip',
    doc: 'application/msword',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    xls: 'application/vnd.ms-excel',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ppt: 'application/vnd.ms-powerpoint',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    mp4: 'video/mp4',
    mp3: 'audio/mpeg',
    wav: 'audio/wav',
  }

  const result: Accept = {}
  for (const p of parts) {
    if (p.includes('/')) {
      if (!result[p]) result[p] = []
      continue
    }
    const ext = p.replace(/^\./, '')
    const mime = extToMime[ext] ?? 'application/octet-stream'
    const dot = `.${ext}`
    const prev = result[mime] ?? []
    if (!prev.includes(dot)) result[mime] = [...prev, dot]
  }
  return result
}

function isExtensionBlocked(name: string, blocked: string | null | undefined): boolean {
  if (!blocked || !String(blocked).trim()) return false
  const ext = name.includes('.') ? name.split('.').pop()?.toLowerCase() ?? '' : ''
  if (!ext) return false
  const blockedList = String(blocked)
    .split(/[,，]/)
    .map((s) => s.trim().toLowerCase().replace(/^\./, ''))
    .filter(Boolean)
  return blockedList.includes(ext)
}

type FieldFileEditorProps = {
  value: unknown
  onChange: (value: FieldFileAttachment[] | null) => void
  typeConfig?: Record<string, unknown>
  placeholder?: string
  disabled?: boolean
  className?: string
}

/**
 * File upload for custom FILE fields (JSON slot: list of attachments).
 * Uses react-dropzone for click + drag-and-drop.
 */
export function FieldFileEditor({
  value,
  onChange,
  typeConfig = {},
  placeholder = '',
  disabled = false,
  className,
}: FieldFileEditorProps) {
  const [localError, setLocalError] = useState<string | null>(null)
  const uploadMutation = useUploadCustomFieldFile()

  const maxCount = Math.max(1, Number(typeConfig.max_file_count) || 1)
  const maxMb = typeConfig.max_file_size_mb != null ? Number(typeConfig.max_file_size_mb) : null
  const maxBytes = maxMb != null && !Number.isNaN(maxMb) && maxMb > 0 ? maxMb * 1024 * 1024 : null
  const maxTotalMb = typeConfig.max_total_size_mb != null ? Number(typeConfig.max_total_size_mb) : null
  const maxTotalBytes =
    maxTotalMb != null && !Number.isNaN(maxTotalMb) && maxTotalMb > 0 ? maxTotalMb * 1024 * 1024 : null
  const accept = useMemo(
    () => buildDropzoneAccept(typeConfig.allowed_mime_types as string | undefined),
    [typeConfig],
  )
  const blocked = typeConfig.blocked_mime_types as string | undefined

  const files = normalizeFileValue(value)
  const busy = uploadMutation.isPending
  const slotFull = files.length >= maxCount
  const dropDisabled = disabled || busy || slotFull

  const processFiles = useCallback(
    async (incoming: File[]) => {
      setLocalError(null)
      if (!incoming.length) return

      const nextSlots = maxCount - files.length
      if (nextSlots <= 0) {
        setLocalError('已达到最大文件数量')
        return
      }

      const toAdd = incoming.slice(0, nextSlots)
      const uploaded: FieldFileAttachment[] = [...files]

      let runningTotalBytes = files.reduce(
        (sum, f) => sum + (typeof f.size === 'number' ? f.size : 0),
        0,
      )

      for (const file of toAdd) {
        if (isExtensionBlocked(file.name, blocked)) {
          setLocalError(`不允许的文件类型: ${file.name}`)
          return
        }
        if (maxBytes != null && file.size > maxBytes) {
          setLocalError(`文件过大: ${file.name}`)
          return
        }
        if (maxTotalBytes != null && runningTotalBytes + file.size > maxTotalBytes) {
          setLocalError('已超出总文件体积上限')
          return
        }
        try {
          const meta = await uploadMutation.mutateAsync(file)
          uploaded.push(meta)
          runningTotalBytes += typeof meta.size === 'number' ? meta.size : file.size
        } catch {
          setLocalError(`上传失败: ${file.name}`)
          return
        }
      }

      onChange(uploaded.length > 0 ? uploaded : null)
    },
    [files, maxCount, maxBytes, maxTotalBytes, blocked, onChange, uploadMutation],
  )

  const onDrop = useCallback(
    async (acceptedFiles: File[], fileRejections: FileRejection[]) => {
      if (fileRejections.length > 0) {
        const codes = fileRejections[0].errors.map((e) => e.code).join(', ')
        setLocalError(codes.includes('file-invalid-type') ? '文件类型不允许' : '无法添加该文件')
        if (acceptedFiles.length === 0) return
      }
      await processFiles(acceptedFiles)
    },
    [processFiles],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    disabled: dropDisabled,
    multiple: maxCount > 1,
    noClick: slotFull,
    noKeyboard: slotFull,
  })

  const removeAt = useCallback(
    (index: number) => {
      const next = files.filter((_, i) => i !== index)
      onChange(next.length > 0 ? next : null)
    },
    [files, onChange],
  )

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div
        {...getRootProps()}
        className={cn(
          'flex min-h-10 w-full max-w-md cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed border-border bg-transparent px-3 py-3 text-center text-sm transition-colors outline-none',
          'hover:border-muted-foreground hover:bg-muted/30',
          isDragActive && 'border-primary bg-primary/5',
          dropDisabled && 'cursor-not-allowed opacity-50 hover:border-border hover:bg-transparent',
        )}
      >
        <input {...getInputProps()} />
        <span className="inline-flex items-center gap-2 text-muted-foreground">
          {busy ? (
            <IconLoader2 size={18} className="shrink-0 animate-spin" />
          ) : (
            <IconPaperclip size={18} className="shrink-0" />
          )}
          {busy ? '上传中…' : placeholder}
        </span>
        {!busy && !slotFull && (
          <span className="text-xs text-muted-foreground/80">点击选择或拖拽文件到此处</span>
        )}
      </div>

      {files.length > 0 && (
        <ul className="flex max-w-md flex-col gap-1.5">
          {files.map((f, i) => (
            <li
              key={`${f.url}-${i}`}
              className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/20 px-2.5 py-1.5 text-sm"
            >
              <a
                href={f.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 truncate text-primary underline-offset-2 hover:underline"
              >
                {f.name || `文件 ${i + 1}`}
              </a>
              <button
                type="button"
                disabled={disabled || busy}
                onClick={(e) => {
                  e.stopPropagation()
                  removeAt(i)
                }}
                className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                aria-label="Remove file"
              >
                <IconX size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {localError && <p className="text-xs text-destructive">{localError}</p>}
    </div>
  )
}
