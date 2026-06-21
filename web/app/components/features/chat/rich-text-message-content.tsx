'use client'

import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { SafeHtml } from '@/components/safe-html'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { cn } from '@/lib/utils'
import { getConversationFileUrl } from '@/service/use-conversation-files'

type RichTextMessageContentProps = {
  html: string
  className?: string
  style?: CSSProperties
  conversationId?: number
  conversationPublicId?: string
  visitorSessionToken?: string
}

type ImageUrlState = 'loading' | 'failed' | string

const TRANSPARENT_IMAGE_SRC =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='

type RichTextImageRef = {
  fileId: string
  downloadName?: string
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

    const existingSrc = img.getAttribute('src')?.trim() ?? ''
    if (existingSrc && !existingSrc.startsWith('blob:') && !existingSrc.startsWith('data:')) {
      return
    }

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
  const [imageUrls, setImageUrls] = useState<Record<string, ImageUrlState>>({})

  useEffect(() => {
    if (images.length === 0) {
      setImageUrls({})
      return
    }

    let cancelled = false
    setImageUrls(Object.fromEntries(images.map((item) => [item.fileId, 'loading'])))

    for (const image of images) {
      void getConversationFileUrl({
        conversationId,
        conversationPublicId,
        visitorSessionToken,
        fileId: image.fileId,
        downloadName: image.downloadName,
      })
        .then((result) => {
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
  }, [conversationId, conversationPublicId, images, visitorSessionToken])

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
