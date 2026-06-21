'use client'

import dynamic from 'next/dynamic'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ImagePreviewLightbox } from '@/app/components/ui/image-preview-lightbox'
import { IconDownload, IconEye, IconFile, IconLoader2, IconX } from '@tabler/icons-react'
import type { ConversationFilePayload } from '@/models/conversation-file'
import { getConversationFileUrl } from '@/service/use-conversation-files'
import { cn } from '@/lib/utils'

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

const attachmentCardClassName =
  'overflow-hidden rounded-[18px] border border-border bg-background p-3 text-foreground'
const imageAttachmentClassName =
  'overflow-hidden rounded-[18px] border border-border bg-muted text-foreground'

type MessageAttachmentProps = {
  conversationId?: number
  conversationPublicId?: string
  offlineMessageId?: number
  offlineMessagePublicId?: string
  visitorSessionToken?: string
  contentType: 'image' | 'file'
  content: string
  className?: string
  imageGallery?: MessageAttachmentGalleryItem[]
  currentImageId?: string | number
}

export type MessageAttachmentGalleryItem = {
  id: string | number
  content: string
}

type ResolvedImageSlide = {
  id: string | number
  slide: { src: string; alt: string }
}

function parsePayload(content: string): ConversationFilePayload | null {
  try {
    const payload = JSON.parse(content) as ConversationFilePayload
    if (!payload.file_id || !payload.name || !payload.mime_type) return null
    return payload
  } catch {
    return null
  }
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function isPdf(mimeType: string | undefined, filename: string | undefined): boolean {
  return mimeType === 'application/pdf' || Boolean(filename?.toLowerCase().endsWith('.pdf'))
}

function getFileIconSrc(mimeType: string | undefined, filename: string): string | null {
  const lowerName = filename.toLowerCase()
  const lowerMime = mimeType?.toLowerCase() ?? ''

  if (lowerMime === 'application/pdf' || lowerName.endsWith('.pdf')) return '/file-icons/pdf.svg'
  if (
    lowerMime.includes('word') ||
    lowerName.endsWith('.doc') ||
    lowerName.endsWith('.docx')
  ) {
    return '/file-icons/word.svg'
  }
  if (
    lowerMime.includes('excel') ||
    lowerMime.includes('spreadsheet') ||
    lowerName.endsWith('.xls') ||
    lowerName.endsWith('.xlsx')
  ) {
    return '/file-icons/excel.svg'
  }
  if (
    lowerMime.includes('powerpoint') ||
    lowerMime.includes('presentation') ||
    lowerName.endsWith('.ppt') ||
    lowerName.endsWith('.pptx')
  ) {
    return '/file-icons/ppt.svg'
  }
  if (
    lowerMime.includes('zip') ||
    lowerName.endsWith('.zip') ||
    lowerName.endsWith('.rar') ||
    lowerName.endsWith('.7z')
  ) {
    return '/file-icons/zip.svg'
  }

  return null
}

function TruncatedFileName({ name, className }: { name: string; className?: string }) {
  const textRef = useRef<HTMLDivElement | null>(null)
  const [isTruncated, setIsTruncated] = useState(false)

  const updateTruncated = useCallback(() => {
    const element = textRef.current
    if (!element) return
    setIsTruncated(element.scrollWidth > element.clientWidth)
  }, [])

  useEffect(() => {
    updateTruncated()
    window.addEventListener('resize', updateTruncated)
    return () => window.removeEventListener('resize', updateTruncated)
  }, [name, updateTruncated])

  return (
    <div
      ref={textRef}
      className={cn('truncate text-sm font-medium', className)}
      title={isTruncated ? name : undefined}
      onMouseEnter={updateTruncated}
    >
      {name}
    </div>
  )
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

export function MessageAttachment({
  conversationId,
  conversationPublicId,
  offlineMessageId,
  offlineMessagePublicId,
  visitorSessionToken,
  contentType,
  content,
  className,
  imageGallery,
  currentImageId,
}: MessageAttachmentProps) {
  const payload = useMemo(() => parsePayload(content), [content])
  const [url, setUrl] = useState<string | null>(payload ? null : content)
  const [loading, setLoading] = useState(Boolean(payload))
  const [error, setError] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [lightboxSlides, setLightboxSlides] = useState<Array<{ src: string; alt: string }>>([])
  const [lightboxIndex, setLightboxIndex] = useState(0)
  const isImage = contentType === 'image'
  const isPdfFile = isPdf(payload?.mime_type, payload?.name)
  const fileName = payload?.name || '附件'
  const fileIconSrc = getFileIconSrc(payload?.mime_type, fileName)

  useEffect(() => {
    let alive = true
    if (!payload) return

    setLoading(true)
    setError(false)
    getConversationFileUrl({
      conversationId,
      conversationPublicId,
      offlineMessageId,
      offlineMessagePublicId,
      visitorSessionToken,
      fileId: payload.file_id,
      downloadName: payload.name,
    })
      .then((res) => {
        if (alive) setUrl(res.url)
      })
      .catch(() => {
        if (alive) setError(true)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })

    return () => {
      alive = false
    }
  }, [conversationId, conversationPublicId, offlineMessageId, offlineMessagePublicId, payload, visitorSessionToken])

  const handleDownload = useCallback(async () => {
    if (!payload) {
      if (url) window.open(url, '_blank', 'noopener,noreferrer')
      return
    }
    const res = await getConversationFileUrl({
      conversationId,
      conversationPublicId,
      offlineMessageId,
      offlineMessagePublicId,
      visitorSessionToken,
      fileId: payload.file_id,
      downloadName: payload.name,
      download: true,
    })
    window.open(res.url, '_blank', 'noopener,noreferrer')
  }, [conversationId, conversationPublicId, offlineMessageId, offlineMessagePublicId, payload, url, visitorSessionToken])

  const handleImagePreview = useCallback(async () => {
    if (!url) return

    setPreviewLoading(true)
    const fallbackId = currentImageId ?? 'current'
    const gallery = imageGallery?.length ? imageGallery : [{ id: fallbackId, content }]
    const currentId = currentImageId ?? gallery[0]?.id ?? fallbackId

    const resolved = await Promise.all(
      gallery.map(async (item): Promise<ResolvedImageSlide | null> => {
        try {
          const itemPayload = parsePayload(item.content)
          if (!itemPayload) {
            return { id: item.id, slide: { src: item.content, alt: 'image' } }
          }
          if (String(item.id) === String(currentId) && url) {
            return { id: item.id, slide: { src: url, alt: itemPayload.name || 'image' } }
          }
          const res = await getConversationFileUrl({
            conversationId,
            conversationPublicId,
            offlineMessageId,
            offlineMessagePublicId,
            visitorSessionToken,
            fileId: itemPayload.file_id,
            downloadName: itemPayload.name,
          })
          return { id: item.id, slide: { src: res.url, alt: itemPayload.name || 'image' } }
        } catch {
          return null
        }
      }),
    )

    const slidesWithId = resolved.filter((item): item is ResolvedImageSlide => item !== null)
    const slides = slidesWithId.map((item) => item.slide)
    if (slides.length > 0) {
      setLightboxSlides(slides)
      setLightboxIndex(Math.max(0, slidesWithId.findIndex((item) => String(item.id) === String(currentId))))
      setPreviewOpen(true)
    }
    setPreviewLoading(false)
  }, [content, conversationId, conversationPublicId, currentImageId, imageGallery, offlineMessageId, offlineMessagePublicId, url, visitorSessionToken])

  if (isImage) {
    if (loading) {
      return (
        <div className={cn('inline-block max-w-full', imageAttachmentClassName, className)}>
          <div className="flex h-32 w-48 items-center justify-center bg-muted">
            <IconLoader2 size={18} className="animate-spin text-muted-foreground" />
          </div>
        </div>
      )
    }
    if (error || !url) {
      return (
        <div className={cn('inline-block max-w-full px-3 py-2 text-sm text-muted-foreground', imageAttachmentClassName, className)}>
          文件暂时无法访问
        </div>
      )
    }
    return (
      <>
        <div className={cn('inline-block max-w-full', imageAttachmentClassName, className)}>
          <button
            type="button"
            className="block max-w-full overflow-hidden disabled:cursor-wait"
            disabled={previewLoading}
            onClick={() => {
              void handleImagePreview()
            }}
          >
            <img src={url} alt={payload?.name || 'image'} className="block max-h-60 max-w-full object-cover" />
          </button>
        </div>
        <ImagePreviewLightbox
          open={previewOpen}
          close={() => setPreviewOpen(false)}
          index={lightboxIndex}
          slides={lightboxSlides.length > 0 ? lightboxSlides : [{ src: url, alt: payload?.name || 'image' }]}
          carousel={{ finite: true }}
          render={lightboxSlides.length <= 1 ? { buttonPrev: () => null, buttonNext: () => null } : undefined}
        />
      </>
    )
  }

  return (
    <div className={cn('w-64', attachmentCardClassName, className)}>
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground">
          {fileIconSrc ? (
            <img src={fileIconSrc} alt="" className="h-7 w-7" />
          ) : (
            <IconFile size={20} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <TruncatedFileName name={fileName} />
          <div className="mt-0.5 text-xs text-muted-foreground">
            {payload ? formatSize(payload.size) : '文件'}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-xs hover:bg-muted disabled:opacity-50"
          disabled={loading || error || !url}
          aria-label="Preview file"
          title="预览"
          onClick={(event) => {
            event.stopPropagation()
            setPreviewOpen(true)
          }}
        >
          <IconEye size={14} />
        </button>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border text-xs hover:bg-muted disabled:opacity-50"
          disabled={loading || error}
          aria-label="Download file"
          title="下载"
          onClick={(event) => {
            event.stopPropagation()
            void handleDownload()
          }}
        >
          <IconDownload size={14} />
        </button>
      </div>
      {previewOpen && url && (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 p-4"
          onClick={() => setPreviewOpen(false)}
        >
          <div
            className="flex h-[min(80vh,720px)] w-[min(90vw,960px)] flex-col overflow-hidden rounded-lg bg-background shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
              <TruncatedFileName name={fileName} className="min-w-0" />
              <button
                type="button"
                className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={() => setPreviewOpen(false)}
                aria-label="Close preview"
              >
                <IconX size={18} />
              </button>
            </div>
            {isPdfFile ? (
              <PDFViewer
                config={{
                  src: url,
                  tabBar: 'never',
                  theme: { preference: 'light' },
                }}
                className="min-h-0 flex-1 bg-white"
              />
            ) : (
              <div className="min-h-0 flex-1 bg-white">
                <JitDocumentViewer url={url} filename={fileName} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
