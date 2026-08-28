'use client'

import { useCallback, useEffect, useMemo, useState, type CSSProperties, type MouseEvent } from 'react'
import { ImagePreviewLightbox } from '@/app/components/ui/image-preview-lightbox'
import { SafeHtml } from '@/components/safe-html'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { cn } from '@/lib/utils'
import {
  CONVERSATION_IMAGE_DISPLAY_PROCESS,
  getConversationFileUrl,
} from '@/service/use-conversation-files'

type RichTextMessageContentProps = {
  html: string
  className?: string
  style?: CSSProperties
  conversationId?: number
  conversationPublicId?: string
  visitorSessionToken?: string
}

type ImageUrlState = 'loading' | 'failed' | string

type CachedImageUrl = {
  url: string
  expiresAt: number
}

const TRANSPARENT_IMAGE_SRC =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='
const RICH_TEXT_IMAGE_CACHE_EARLY_EXPIRY_MS = 30 * 1000
const richTextImageUrlCache = new Map<string, CachedImageUrl>()

type RichTextImageRef = {
  fileId: string
  downloadName?: string
}

type PreviewSlide = {
  fileId?: string
  slide: { src: string; alt: string }
}

export function isUsableRichTextImageSrc(src: string | null | undefined): boolean {
  if (!src) return false
  if (src === 'loading' || src === 'failed' || src === TRANSPARENT_IMAGE_SRC) return false
  if (src.startsWith('blob:')) return true
  try {
    const url = new URL(src, 'https://local.invalid')
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

function richTextImageCacheKey(input: {
  conversationId?: number
  conversationPublicId?: string
  visitorSessionToken?: string
  fileId: string
  downloadName?: string
  imageProcess?: string
}): string {
  return [
    input.conversationId ?? '',
    input.conversationPublicId ?? '',
    input.visitorSessionToken ?? '',
    input.fileId,
    input.downloadName ?? '',
    input.imageProcess ?? '',
  ].join('\u0000')
}

function getCachedRichTextImageUrl(cacheKey: string): string | null {
  const cached = richTextImageUrlCache.get(cacheKey)
  if (!cached) return null
  if (cached.expiresAt <= Date.now()) {
    richTextImageUrlCache.delete(cacheKey)
    return null
  }
  return cached.url
}

function setCachedRichTextImageUrl(cacheKey: string, url: string, expiresSeconds: number): void {
  richTextImageUrlCache.set(cacheKey, {
    url,
    expiresAt: Date.now() + expiresSeconds * 1000 - RICH_TEXT_IMAGE_CACHE_EARLY_EXPIRY_MS,
  })
}

function extractRichTextImages(html: string): RichTextImageRef[] {
  if (typeof document === 'undefined') {
    const images: RichTextImageRef[] = []
    const pattern = /<img\b[^>]*\bdata-file-id="([^"]+)"[^>]*>/gi
    let match: RegExpExecArray | null
    while ((match = pattern.exec(html)) !== null) {
      const tag = match[0]
      const fileId = match[1]
      images.push({
        fileId,
        downloadName: tag.match(/\balt="([^"]*)"/)?.[1]
          || tag.match(/\bdata-name="([^"]*)"/)?.[1]
          || undefined,
      })
    }
    return images
  }

  const template = document.createElement('template')
  template.innerHTML = html
  return Array.from(template.content.querySelectorAll<HTMLImageElement>('img[data-file-id]'))
    .map((img) => ({
      fileId: img.getAttribute('data-file-id') ?? '',
      downloadName: img.alt || img.getAttribute('data-name') || undefined,
    }))
    .filter((item) => item.fileId.length > 0)
}

export function buildRichTextDisplayHtml(html: string, imageUrls: Record<string, ImageUrlState>): string {
  if (typeof document === 'undefined') return html

  const template = document.createElement('template')
  template.innerHTML = html
  template.content.querySelectorAll<HTMLImageElement>('img[data-file-id]').forEach((img) => {
    const fileId = img.getAttribute('data-file-id')
    if (!fileId) return

    const state = imageUrls[fileId]
    if (state === 'failed') {
      img.setAttribute('src', TRANSPARENT_IMAGE_SRC)
      img.setAttribute('data-rich-text-load-failed', 'true')
      img.removeAttribute('data-rich-text-loading')
      return
    }
    // 'loading' is a string sentinel — must not be treated as a real URL.
    if (state === 'loading' || state == null) {
      img.setAttribute('src', TRANSPARENT_IMAGE_SRC)
      img.setAttribute('data-rich-text-loading', 'true')
      img.removeAttribute('data-rich-text-load-failed')
      return
    }

    img.setAttribute('src', state)
    img.removeAttribute('data-rich-text-loading')
    img.removeAttribute('data-rich-text-load-failed')
  })

  return template.innerHTML
}

async function resolvePreviewUrl(input: {
  conversationId?: number
  conversationPublicId?: string
  visitorSessionToken?: string
  fileId: string
  downloadName?: string
  fallbackUrl?: string
}): Promise<string | null> {
  const cacheKey = richTextImageCacheKey({
    conversationId: input.conversationId,
    conversationPublicId: input.conversationPublicId,
    visitorSessionToken: input.visitorSessionToken,
    fileId: input.fileId,
    downloadName: input.downloadName,
  })
  const cachedUrl = getCachedRichTextImageUrl(cacheKey)
  if (cachedUrl) return cachedUrl

  try {
    const result = await getConversationFileUrl({
      conversationId: input.conversationId,
      conversationPublicId: input.conversationPublicId,
      visitorSessionToken: input.visitorSessionToken,
      fileId: input.fileId,
      downloadName: input.downloadName,
    })
    setCachedRichTextImageUrl(cacheKey, result.url, result.expires_seconds)
    return result.url
  } catch {
    return isUsableRichTextImageSrc(input.fallbackUrl) ? input.fallbackUrl! : null
  }
}

function displayUrlForImage(
  imageUrls: Record<string, ImageUrlState>,
  fileId: string,
  clickedSrc?: string,
): string | undefined {
  const displayUrl = imageUrls[fileId]
  if (typeof displayUrl === 'string' && isUsableRichTextImageSrc(displayUrl)) return displayUrl
  if (isUsableRichTextImageSrc(clickedSrc)) return clickedSrc
  return undefined
}

export function RichTextMessageContent({
  html,
  className,
  style,
  conversationId,
  conversationPublicId,
  visitorSessionToken,
}: RichTextMessageContentProps) {
  const images = useMemo(() => extractRichTextImages(html), [html])
  const initialImageUrls = useMemo(
    () =>
      Object.fromEntries(images.map((image) => {
        const cacheKey = richTextImageCacheKey({
          conversationId,
          conversationPublicId,
          visitorSessionToken,
          fileId: image.fileId,
          downloadName: image.downloadName,
          imageProcess: CONVERSATION_IMAGE_DISPLAY_PROCESS,
        })
        return [image.fileId, getCachedRichTextImageUrl(cacheKey) ?? 'loading']
      })),
    [conversationId, conversationPublicId, images, visitorSessionToken],
  )
  const [imageUrls, setImageUrls] = useState<Record<string, ImageUrlState>>(initialImageUrls)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [lightboxSlides, setLightboxSlides] = useState<Array<{ src: string; alt: string }>>([])
  const [lightboxIndex, setLightboxIndex] = useState(0)

  useEffect(() => {
    if (images.length === 0) {
      setImageUrls({})
      return
    }

    let cancelled = false
    setImageUrls(initialImageUrls)

    for (const image of images) {
      const cacheKey = richTextImageCacheKey({
        conversationId,
        conversationPublicId,
        visitorSessionToken,
        fileId: image.fileId,
        downloadName: image.downloadName,
        imageProcess: CONVERSATION_IMAGE_DISPLAY_PROCESS,
      })
      const cachedUrl = getCachedRichTextImageUrl(cacheKey)
      if (cachedUrl) continue

      void getConversationFileUrl({
        conversationId,
        conversationPublicId,
        visitorSessionToken,
        fileId: image.fileId,
        downloadName: image.downloadName,
        imageProcess: CONVERSATION_IMAGE_DISPLAY_PROCESS,
      })
        .then((result) => {
          setCachedRichTextImageUrl(cacheKey, result.url, result.expires_seconds)
          if (cancelled) return
          setImageUrls((prev) => ({ ...prev, [image.fileId]: result.url }))
        })
        .catch(() => {
          if (cancelled) return
          setImageUrls((prev) => ({ ...prev, [image.fileId]: 'failed' }))
        })
    }

    return () => {
      cancelled = true
    }
  }, [conversationId, conversationPublicId, images, initialImageUrls, visitorSessionToken])

  const displayHtml = useMemo(
    () => buildRichTextDisplayHtml(html, imageUrls),
    [html, imageUrls],
  )

  const handleImageClick = useCallback(async (event: MouseEvent<HTMLDivElement>) => {
    const eventTarget = event.target
    if (!(eventTarget instanceof Element)) return
    const target = eventTarget.closest('img')
    if (!(target instanceof HTMLImageElement)) return
    if (target.getAttribute('data-rich-text-loading') === 'true') return
    if (target.getAttribute('data-rich-text-load-failed') === 'true') return

    const fileId = target.getAttribute('data-file-id')
    const clickedSrc = target.currentSrc || target.getAttribute('src') || ''
    if (!fileId && !isUsableRichTextImageSrc(clickedSrc)) return

    // Open with whatever is already on screen; do not wait on network first.
    const initialSlides: PreviewSlide[] = []
    if (images.length > 0) {
      for (const image of images) {
        const src = displayUrlForImage(
          imageUrls,
          image.fileId,
          image.fileId === fileId ? clickedSrc : undefined,
        )
        if (!src) continue
        initialSlides.push({
          fileId: image.fileId,
          slide: { src, alt: image.downloadName || 'image' },
        })
      }
    } else if (isUsableRichTextImageSrc(clickedSrc)) {
      initialSlides.push({
        slide: { src: clickedSrc, alt: target.alt || 'image' },
      })
    }

    if (initialSlides.length === 0) return

    event.preventDefault()
    event.stopPropagation()
    if (previewLoading) return

    const initialIndex = fileId
      ? Math.max(0, initialSlides.findIndex((item) => item.fileId === fileId))
      : 0
    setLightboxSlides(initialSlides.map((item) => item.slide))
    setLightboxIndex(initialIndex)
    setPreviewOpen(true)

    if (images.length === 0) return

    setPreviewLoading(true)
    try {
      const resolved = await Promise.all(
        images.map(async (image) => {
          const fallbackUrl = displayUrlForImage(
            imageUrls,
            image.fileId,
            image.fileId === fileId ? clickedSrc : undefined,
          )
          const src = await resolvePreviewUrl({
            conversationId,
            conversationPublicId,
            visitorSessionToken,
            fileId: image.fileId,
            downloadName: image.downloadName,
            fallbackUrl,
          })
          if (!isUsableRichTextImageSrc(src)) return null
          return {
            fileId: image.fileId,
            slide: { src: src!, alt: image.downloadName || 'image' },
          }
        }),
      )

      const slidesWithId = resolved.filter(
        (item): item is { fileId: string; slide: { src: string; alt: string } } => item !== null,
      )
      if (slidesWithId.length === 0) return

      const index = fileId
        ? Math.max(0, slidesWithId.findIndex((item) => item.fileId === fileId))
        : 0
      setLightboxSlides(slidesWithId.map((item) => item.slide))
      setLightboxIndex(index)
    } finally {
      setPreviewLoading(false)
    }
  }, [
    conversationId,
    conversationPublicId,
    images,
    imageUrls,
    previewLoading,
    visitorSessionToken,
  ])

  return (
    <>
      <div
        className={cn(
          'min-w-0',
          richTextListStyleClass,
          previewLoading && '[&_img[data-file-id]]:cursor-wait',
          className,
        )}
        style={style}
        onClick={(event) => {
          void handleImageClick(event)
        }}
      >
        <SafeHtml html={displayHtml} />
      </div>
      <ImagePreviewLightbox
        open={previewOpen}
        close={() => setPreviewOpen(false)}
        index={lightboxIndex}
        slides={lightboxSlides}
        carousel={{ finite: true }}
        render={lightboxSlides.length <= 1 ? { buttonPrev: () => null, buttonNext: () => null } : undefined}
      />
    </>
  )
}
