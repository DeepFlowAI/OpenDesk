'use client'

import dynamic from 'next/dynamic'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ImagePreviewLightbox } from '@/app/components/ui/image-preview-lightbox'
import { IconDownload, IconEye, IconFile, IconLoader2, IconX } from '@tabler/icons-react'
import type { ConversationFilePayload } from '@/models/conversation-file'
import {
  CONVERSATION_IMAGE_DISPLAY_PROCESS,
  getConversationFileUrl,
} from '@/service/use-conversation-files'
import { cn } from '@/lib/utils'
import { parsePendingAttachmentContent } from '@/lib/pending-attachment'
import {
  canPlayH264Mp4,
  isMp4VideoCandidate,
  MessageVideoAttachment,
} from '@/app/components/features/chat/message-video-attachment'

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
const PDFIUM_WASM_PATH = '/vendor/embedpdf/pdfium.wasm'
const ATTACHMENT_URL_CACHE_EARLY_EXPIRY_MS = 30 * 1000

export function resolvePdfiumWasmUrl(origin: string): string {
  return new URL(PDFIUM_WASM_PATH, origin).href
}

type CachedAttachmentUrl = {
  url: string
  expiresAt: number
}

const attachmentUrlCache = new Map<string, CachedAttachmentUrl>()

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
  compact?: boolean
  inlinePlayableVideo?: boolean
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

function attachmentUrlCacheKey(input: {
  conversationId?: number
  conversationPublicId?: string
  offlineMessageId?: number
  offlineMessagePublicId?: string
  visitorSessionToken?: string
  fileId: string
  downloadName?: string
  imageProcess?: string
}): string {
  return [
    input.conversationId ?? '',
    input.conversationPublicId ?? '',
    input.offlineMessageId ?? '',
    input.offlineMessagePublicId ?? '',
    input.visitorSessionToken ?? '',
    input.fileId,
    input.downloadName ?? '',
    input.imageProcess ?? '',
  ].join('\u0000')
}

function getCachedAttachmentUrl(cacheKey: string): string | null {
  const cached = attachmentUrlCache.get(cacheKey)
  if (!cached) return null
  if (cached.expiresAt <= Date.now()) {
    attachmentUrlCache.delete(cacheKey)
    return null
  }
  return cached.url
}

function setCachedAttachmentUrl(cacheKey: string, url: string, expiresSeconds: number): void {
  attachmentUrlCache.set(cacheKey, {
    url,
    expiresAt: Date.now() + expiresSeconds * 1000 - ATTACHMENT_URL_CACHE_EARLY_EXPIRY_MS,
  })
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
  compact = false,
  inlinePlayableVideo = false,
}: MessageAttachmentProps) {
  const payload = useMemo(() => parsePayload(content), [content])
  const pendingPayload = useMemo(() => parsePendingAttachmentContent(content), [content])
  const attachmentPayload = payload ?? pendingPayload
  const isImage = contentType === 'image'
  const skipUrlFetch = compact && !isImage
  const displayImageProcess = isImage ? CONVERSATION_IMAGE_DISPLAY_PROCESS : undefined
  const displayUrlCacheKey = useMemo(
    () =>
      payload && !skipUrlFetch
        ? attachmentUrlCacheKey({
            conversationId,
            conversationPublicId,
            offlineMessageId,
            offlineMessagePublicId,
            visitorSessionToken,
            fileId: payload.file_id,
            downloadName: payload.name,
            imageProcess: displayImageProcess,
          })
        : null,
    [
      conversationId,
      conversationPublicId,
      displayImageProcess,
      offlineMessageId,
      offlineMessagePublicId,
      payload,
      skipUrlFetch,
      visitorSessionToken,
    ],
  )
  const cachedDisplayUrl = displayUrlCacheKey ? getCachedAttachmentUrl(displayUrlCacheKey) : null
  const [url, setUrl] = useState<string | null>(
    payload ? cachedDisplayUrl : pendingPayload?.local_url ?? content,
  )
  const [loading, setLoading] = useState(Boolean(payload && !skipUrlFetch && !cachedDisplayUrl))
  const [error, setError] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [lightboxSlides, setLightboxSlides] = useState<Array<{ src: string; alt: string }>>([])
  const [lightboxIndex, setLightboxIndex] = useState(0)
  const [browserSupportsInlineVideo, setBrowserSupportsInlineVideo] = useState<boolean | null>(null)
  const [videoPlaybackFailed, setVideoPlaybackFailed] = useState(false)
  const isPdfFile = isPdf(attachmentPayload?.mime_type, attachmentPayload?.name)
  const fileName = attachmentPayload?.name || '附件'
  const fileIconSrc = getFileIconSrc(attachmentPayload?.mime_type, fileName)
  const inlineVideoCandidate = inlinePlayableVideo
    && !compact
    && !isImage
    && isMp4VideoCandidate(attachmentPayload)

  useEffect(() => {
    setVideoPlaybackFailed(false)
    if (!inlineVideoCandidate) {
      setBrowserSupportsInlineVideo(null)
      return
    }
    setBrowserSupportsInlineVideo(canPlayH264Mp4(document.createElement('video')))
  }, [content, inlineVideoCandidate])

  useEffect(() => {
    if (!pendingPayload) return
    setUrl(pendingPayload.local_url)
    setLoading(false)
    setError(false)
  }, [pendingPayload])

  useEffect(() => {
    let alive = true
    if (!payload || skipUrlFetch) return

    if (displayUrlCacheKey) {
      const cachedUrl = getCachedAttachmentUrl(displayUrlCacheKey)
      if (cachedUrl) {
        setUrl(cachedUrl)
        setLoading(false)
        setError(false)
        return
      }
    }

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
      imageProcess: displayImageProcess,
    })
      .then((res) => {
        if (displayUrlCacheKey) setCachedAttachmentUrl(displayUrlCacheKey, res.url, res.expires_seconds)
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
  }, [
    conversationId,
    conversationPublicId,
    displayImageProcess,
    displayUrlCacheKey,
    offlineMessageId,
    offlineMessagePublicId,
    payload,
    skipUrlFetch,
    visitorSessionToken,
  ])

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
            const pendingItem = parsePendingAttachmentContent(item.content)
            return {
              id: item.id,
              slide: {
                src: pendingItem?.local_url ?? item.content,
                alt: pendingItem?.name ?? 'image',
              },
            }
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

  if (compact) {
    if (isImage) {
      if (loading) {
        return (
          <div className={cn('flex h-14 w-14 items-center justify-center overflow-hidden rounded-md border border-border/60 bg-muted', className)}>
            <IconLoader2 size={14} className="animate-spin text-muted-foreground" />
          </div>
        )
      }
      if (error || !url) {
        return (
          <div className={cn('flex h-14 w-14 items-center justify-center overflow-hidden rounded-md border border-border/60 bg-muted text-muted-foreground', className)}>
            <IconFile size={16} />
          </div>
        )
      }
      return (
        <div className={cn('inline-block overflow-hidden rounded-md border border-border/60 bg-muted', className)}>
          <img
            src={url}
            alt={attachmentPayload?.name || 'image'}
            className="block max-h-14 max-w-[120px] object-contain"
          />
        </div>
      )
    }
    return (
      <div className={cn('flex max-w-full items-center gap-2 rounded-md border border-border/60 bg-background/60 px-2 py-1.5', className)}>
        <div className="flex h-7 w-7 shrink-0 items-center justify-center text-muted-foreground">
          {fileIconSrc ? <img src={fileIconSrc} alt="" className="h-6 w-6" /> : <IconFile size={16} />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-medium text-foreground" title={fileName}>{fileName}</div>
          {attachmentPayload && <div className="text-[11px] text-muted-foreground">{formatSize(attachmentPayload.size)}</div>}
        </div>
      </div>
    )
  }

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
            <img src={url} alt={attachmentPayload?.name || 'image'} className="block max-h-60 max-w-full object-cover" />
          </button>
        </div>
        <ImagePreviewLightbox
          open={previewOpen}
          close={() => setPreviewOpen(false)}
          index={lightboxIndex}
          slides={lightboxSlides.length > 0 ? lightboxSlides : [{ src: url, alt: attachmentPayload?.name || 'image' }]}
          carousel={{ finite: true }}
          render={lightboxSlides.length <= 1 ? { buttonPrev: () => null, buttonNext: () => null } : undefined}
        />
      </>
    )
  }

  if (inlineVideoCandidate && browserSupportsInlineVideo !== false && !videoPlaybackFailed) {
    if (browserSupportsInlineVideo === null || loading) {
      return (
        <div className={cn('flex aspect-video w-[420px] max-w-full items-center justify-center overflow-hidden rounded-[18px] border border-border bg-black', className)}>
          <IconLoader2 size={20} className="animate-spin text-white/70" />
        </div>
      )
    }
    if (!error && url) {
      return (
        <MessageVideoAttachment
          url={url}
          fileName={fileName}
          sizeLabel={attachmentPayload ? formatSize(attachmentPayload.size) : '文件'}
          onDownload={handleDownload}
          onPlaybackError={() => setVideoPlaybackFailed(true)}
          className={className}
        />
      )
    }
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
            {attachmentPayload ? formatSize(attachmentPayload.size) : '文件'}
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
                  wasmUrl: resolvePdfiumWasmUrl(window.location.origin),
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
