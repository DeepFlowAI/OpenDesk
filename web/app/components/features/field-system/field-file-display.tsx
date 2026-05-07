'use client'

import dynamic from 'next/dynamic'
import { useEffect, useMemo, useRef, useState } from 'react'
import { ImagePreviewLightbox } from '@/app/components/ui/image-preview-lightbox'
import { IconDownload, IconEye, IconFile, IconLoader2, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { FieldFileAttachment } from '@/app/components/features/field-system/field-file-editor'

const PDFViewer = dynamic(
  () => import('@embedpdf/react-pdf-viewer').then((mod) => mod.PDFViewer),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center">
        <IconLoader2 size={18} className="animate-spin text-muted-foreground" />
      </div>
    ),
  },
)

type PreviewKind = 'image' | 'pdf' | 'document'

type FieldFileDisplayProps = {
  value: unknown
  className?: string
}

function normalizeFileValue(value: unknown): FieldFileAttachment[] {
  if (value == null) return []
  const items = Array.isArray(value) ? value : [value]
  return items.filter(
    (item): item is FieldFileAttachment =>
      !!item && typeof item === 'object' && typeof (item as FieldFileAttachment).url === 'string',
  )
}

function fileExtension(filename: string): string {
  const cleanName = filename.split('?')[0]?.split('#')[0] ?? filename
  return cleanName.includes('.') ? cleanName.split('.').pop()?.toLowerCase() ?? '' : ''
}

function previewKind(contentType: string | null | undefined, filename: string): PreviewKind | null {
  const mime = contentType?.toLowerCase() ?? ''
  const ext = fileExtension(filename)

  if (mime.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'avif'].includes(ext)) {
    return 'image'
  }
  if (mime === 'application/pdf' || ext === 'pdf') return 'pdf'
  if (
    mime.includes('word') ||
    mime.includes('excel') ||
    mime.includes('spreadsheet') ||
    mime.includes('powerpoint') ||
    mime.includes('presentation') ||
    ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'md', 'json', 'xml', 'html', 'htm'].includes(ext)
  ) {
    return 'document'
  }

  return null
}

function fileIconSrc(contentType: string | null | undefined, filename: string): string | null {
  const mime = contentType?.toLowerCase() ?? ''
  const ext = fileExtension(filename)

  if (mime === 'application/pdf' || ext === 'pdf') return '/file-icons/pdf.svg'
  if (mime.includes('word') || ['doc', 'docx'].includes(ext)) return '/file-icons/word.svg'
  if (mime.includes('excel') || mime.includes('spreadsheet') || ['xls', 'xlsx'].includes(ext)) {
    return '/file-icons/excel.svg'
  }
  if (mime.includes('powerpoint') || mime.includes('presentation') || ['ppt', 'pptx'].includes(ext)) {
    return '/file-icons/ppt.svg'
  }
  if (mime.includes('zip') || ['zip', 'rar', '7z'].includes(ext)) return '/file-icons/zip.svg'

  return null
}

function formatBytes(size: number | undefined): string | null {
  if (typeof size !== 'number' || !Number.isFinite(size) || size <= 0) return null
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function JitDocumentViewer({ url, filename }: { url: string; filename: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const viewerRef = useRef<{ destroy: () => void } | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function mountViewer() {
      if (!containerRef.current) return

      try {
        setError(false)
        const { createViewer } = await import('jit-viewer')
        if (cancelled || !containerRef.current) return

        const viewer = createViewer({
          target: containerRef.current,
          file: url,
          filename,
          toolbar: true,
          width: '100%',
          height: '100%',
          locale: 'zh-CN',
          theme: 'light',
          onError: () => setError(true),
        })

        viewerRef.current = viewer
        await viewer.mount()
      } catch {
        if (!cancelled) setError(true)
      }
    }

    void mountViewer()

    return () => {
      cancelled = true
      viewerRef.current?.destroy()
      viewerRef.current = null
    }
  }, [url, filename])

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <IconFile size={36} className="text-muted-foreground" />
        <div className="text-sm font-medium">该文件暂时无法在线预览</div>
        <div className="max-w-md text-xs text-muted-foreground">请下载文件后查看。</div>
      </div>
    )
  }

  return <div ref={containerRef} className="h-full w-full" />
}

export function FieldFileDisplay({ value, className }: FieldFileDisplayProps) {
  const files = useMemo(() => normalizeFileValue(value), [value])
  const [previewFile, setPreviewFile] = useState<FieldFileAttachment | null>(null)
  const previewName = previewFile?.name || '附件'
  const currentPreviewKind = previewFile ? previewKind(previewFile.content_type, previewName) : null

  if (files.length === 0) return <span className={cn('text-muted-foreground', className)}>—</span>

  return (
    <>
      <ul className={cn('flex w-full min-w-0 flex-col gap-1.5', className)}>
        {files.map((file, i) => {
          const name = file.name || `文件 ${i + 1}`
          const icon = fileIconSrc(file.content_type, name)
          const canPreview = previewKind(file.content_type, name) !== null
          const sizeLabel = formatBytes(file.size)

          return (
            <li
              key={`${file.url}-${i}`}
              className="flex w-full min-w-0 items-center gap-2 rounded-md border border-border bg-muted/20 px-2.5 py-1.5 text-sm"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground">
                {icon ? <img src={icon} alt="" className="h-5 w-5" /> : <IconFile size={16} />}
              </span>
              <span className="min-w-0 flex-1 truncate text-foreground" title={name}>
                {name}
              </span>
              {sizeLabel && <span className="shrink-0 text-[11px] text-muted-foreground">{sizeLabel}</span>}
              {canPreview && (
                <button
                  type="button"
                  className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Preview file"
                  title="预览"
                  onClick={() => setPreviewFile(file)}
                >
                  <IconEye size={14} />
                </button>
              )}
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                download={name}
                className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Download file"
                title="下载"
              >
                <IconDownload size={14} />
              </a>
            </li>
          )
        })}
      </ul>

      {previewFile && currentPreviewKind === 'image' && (
        <ImagePreviewLightbox
          open
          close={() => setPreviewFile(null)}
          slides={[{ src: previewFile.url, alt: previewName }]}
          carousel={{ finite: true }}
          render={{ buttonPrev: () => null, buttonNext: () => null }}
        />
      )}

      {previewFile && currentPreviewKind && currentPreviewKind !== 'image' && (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 p-4"
          onClick={() => setPreviewFile(null)}
        >
          <div
            className="flex h-[min(80vh,720px)] w-[min(90vw,960px)] flex-col overflow-hidden rounded-lg bg-background shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
              <div className="min-w-0 truncate text-sm font-medium" title={previewName}>
                {previewName}
              </div>
              <button
                type="button"
                className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setPreviewFile(null)}
                aria-label="Close preview"
              >
                <IconX size={18} />
              </button>
            </div>
            {currentPreviewKind === 'pdf' ? (
              <PDFViewer
                config={{
                  src: previewFile.url,
                  tabBar: 'never',
                  theme: { preference: 'light' },
                }}
                className="min-h-0 flex-1 bg-white"
              />
            ) : (
              <div className="min-h-0 flex-1 bg-white">
                <JitDocumentViewer url={previewFile.url} filename={previewName} />
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
