'use client'

import { useEffect, useMemo, useState, type CSSProperties } from 'react'
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

function richTextImageCacheKey(input: {
  conversationId?: number
  conversationPublicId?: string
  visitorSessionToken?: string
  fileId: string
  downloadName?: string
}): string {
  return [
    input.conversationId ?? '',
    input.conversationPublicId ?? '',
    input.visitorSessionToken ?? '',
    input.fileId,
    input.downloadName ?? '',
    CONVERSATION_IMAGE_DISPLAY_PROCESS,
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

function buildRichTextDisplayHtml(html: string, imageUrls: Record<string, ImageUrlState>): string {
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
    if (typeof state === 'string') {
      img.setAttribute('src', state)
      img.removeAttribute('data-rich-text-loading')
      img.removeAttribute('data-rich-text-load-failed')
      return
    }

    img.setAttribute('src', TRANSPARENT_IMAGE_SRC)
    img.setAttribute('data-rich-text-loading', 'true')
    img.removeAttribute('data-rich-text-load-failed')
  })

  return template.innerHTML
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
        })
        return [image.fileId, getCachedRichTextImageUrl(cacheKey) ?? 'loading']
      })),
    [conversationId, conversationPublicId, images, visitorSessionToken],
  )
  const [imageUrls, setImageUrls] = useState<Record<string, ImageUrlState>>(initialImageUrls)

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

  return (
    <div className={cn('min-w-0', richTextListStyleClass, className)} style={style}>
      <SafeHtml html={displayHtml} />
    </div>
  )
}
