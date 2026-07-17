import type { Message } from '@/models/conversation'
import type { ConversationFilePayload } from '@/models/conversation-file'
import type { CustomFieldFileUploadResult } from '@/service/use-upload'
import { postForm } from '@/service/base'
import { getConversationFileUrl } from '@/service/use-conversation-files'

export const MAX_KNOWLEDGE_IMAGE_BYTES = 10 * 1024 * 1024
export const MAX_OSS_IMAGE_PROCESS_SOURCE_BYTES = 20 * 1024 * 1024

export const KNOWLEDGE_STATIC_IMAGE_PROCESS_PROFILES = [
  'image/resize,l_4096,limit_1/format,webp/quality,Q_85',
  'image/resize,l_3072,limit_1/format,webp/quality,Q_75',
  'image/resize,l_2048,limit_1/format,webp/quality,Q_65',
] as const

export const KNOWLEDGE_GIF_IMAGE_PROCESS_PROFILES = [
  'image/resize,l_4096,limit_1/format,gif',
  'image/resize,l_3072,limit_1/format,gif',
  'image/resize,l_2048,limit_1/format,gif',
] as const

export type KnowledgeImageTransferErrorCode =
  | 'invalid_source'
  | 'not_image'
  | 'source_too_large'
  | 'processing_unavailable'
  | 'output_too_large'
  | 'fetch_failed'

export class KnowledgeImageTransferError extends Error {
  constructor(
    public readonly code: KnowledgeImageTransferErrorCode,
    message: string,
  ) {
    super(message)
    this.name = 'KnowledgeImageTransferError'
  }
}

export type KnowledgeImageSource = {
  conversationId: number
  fileId?: string
  url?: string
  name?: string
  mimeType?: string
  size?: number
}

function imageContentTypeFromName(name: string | undefined): string | null {
  const ext = name?.split('.').pop()?.toLowerCase()
  if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg'
  if (ext === 'png') return 'image/png'
  if (ext === 'gif') return 'image/gif'
  if (ext === 'webp') return 'image/webp'
  return null
}

function resolveImageContentType(blob: Blob, source: KnowledgeImageSource): string {
  const contentType = blob.type.startsWith('image/')
    ? blob.type
    : source.mimeType?.startsWith('image/')
      ? source.mimeType
      : imageContentTypeFromName(source.name)
  if (!contentType) {
    throw new KnowledgeImageTransferError('not_image', 'Conversation file is not an image')
  }
  return contentType
}

function fileNameForContentType(name: string | undefined, contentType: string): string {
  const ext = contentType === 'image/jpeg'
    ? 'jpg'
    : contentType.split('/')[1]?.split(';')[0] || 'png'
  if (!name) return `knowledge-image.${ext}`
  const base = name.replace(/\.[^.]+$/, '') || 'knowledge-image'
  return `${base}.${ext}`
}

function isGifSource(source: KnowledgeImageSource, originalContentType: string): boolean {
  return originalContentType === 'image/gif'
    || source.mimeType === 'image/gif'
    || source.name?.toLowerCase().endsWith('.gif') === true
}

async function fetchImageBlob(url: string, source: KnowledgeImageSource): Promise<Blob> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new KnowledgeImageTransferError('fetch_failed', 'Failed to fetch conversation image')
  }
  const blob = await response.blob()
  resolveImageContentType(blob, source)
  return blob
}

async function getSourceUrl(
  source: KnowledgeImageSource,
  imageProcess?: string,
): Promise<string> {
  if (source.fileId) {
    const access = await getConversationFileUrl({
      conversationId: source.conversationId,
      fileId: source.fileId,
      downloadName: source.name,
      ...(imageProcess ? { imageProcess } : {}),
    })
    return access.url
  }
  if (source.url && !imageProcess) return source.url
  throw new KnowledgeImageTransferError(
    'processing_unavailable',
    'Conversation image cannot be processed without a file ID',
  )
}

async function uploadKnowledgeImage(
  blob: Blob,
  source: KnowledgeImageSource,
  contentType: string,
): Promise<CustomFieldFileUploadResult> {
  const file = new File([blob], fileNameForContentType(source.name, contentType), {
    type: contentType,
    lastModified: Date.now(),
  })
  const formData = new FormData()
  formData.append('file', file)
  return postForm<CustomFieldFileUploadResult>('v1/upload/custom-field-file', formData)
}

export function knowledgeImageSourceFromMessage(
  message: Pick<Message, 'conversation_id' | 'content'>,
): KnowledgeImageSource | null {
  const content = message.content.trim()
  if (!content) return null

  try {
    const payload = JSON.parse(content) as Partial<ConversationFilePayload>
    if (typeof payload.file_id === 'string' && payload.file_id) {
      return {
        conversationId: Number(message.conversation_id),
        fileId: payload.file_id,
        name: typeof payload.name === 'string' ? payload.name : undefined,
        mimeType: typeof payload.mime_type === 'string' ? payload.mime_type : undefined,
        size: typeof payload.size === 'number' ? payload.size : undefined,
      }
    }
  } catch {
    // Older image messages may contain a direct URL instead of a file payload.
  }

  try {
    const url = new URL(content)
    if (url.protocol === 'http:' || url.protocol === 'https:') {
      return {
        conversationId: Number(message.conversation_id),
        url: content,
      }
    }
  } catch {
    return null
  }
  return null
}

export async function persistKnowledgeImage(
  source: KnowledgeImageSource,
): Promise<CustomFieldFileUploadResult> {
  if ((!source.fileId && !source.url) || !Number.isFinite(source.conversationId)) {
    throw new KnowledgeImageTransferError('invalid_source', 'Conversation image source is invalid')
  }
  if (source.size != null && source.size > MAX_OSS_IMAGE_PROCESS_SOURCE_BYTES) {
    throw new KnowledgeImageTransferError('source_too_large', 'Conversation image exceeds 20MB')
  }

  const originalUrl = await getSourceUrl(source)
  const originalBlob = await fetchImageBlob(originalUrl, source)
  const originalContentType = resolveImageContentType(originalBlob, source)
  if (originalBlob.size <= MAX_KNOWLEDGE_IMAGE_BYTES) {
    return uploadKnowledgeImage(originalBlob, source, originalContentType)
  }
  if (originalBlob.size > MAX_OSS_IMAGE_PROCESS_SOURCE_BYTES) {
    throw new KnowledgeImageTransferError('source_too_large', 'Conversation image exceeds 20MB')
  }
  if (!source.fileId) {
    throw new KnowledgeImageTransferError(
      'processing_unavailable',
      'Direct image URL cannot use OSS image processing',
    )
  }

  const gif = isGifSource(source, originalContentType)
  const profiles = gif
    ? KNOWLEDGE_GIF_IMAGE_PROCESS_PROFILES
    : KNOWLEDGE_STATIC_IMAGE_PROCESS_PROFILES
  const outputContentType = gif ? 'image/gif' : 'image/webp'
  for (const imageProcess of profiles) {
    const processedUrl = await getSourceUrl(source, imageProcess)
    const processedBlob = await fetchImageBlob(processedUrl, {
      ...source,
      mimeType: outputContentType,
    })
    if (processedBlob.size <= MAX_KNOWLEDGE_IMAGE_BYTES) {
      return uploadKnowledgeImage(processedBlob, source, outputContentType)
    }
  }

  throw new KnowledgeImageTransferError(
    'output_too_large',
    'Processed image still exceeds 10MB',
  )
}

function escapeHtmlAttribute(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
}

export function buildKnowledgeImageHtml(
  uploaded: CustomFieldFileUploadResult,
  fallbackName?: string,
): string {
  const name = uploaded.name || fallbackName || '图片'
  return `<p><img src="${escapeHtmlAttribute(uploaded.url)}" alt="${escapeHtmlAttribute(name)}" title="${escapeHtmlAttribute(name)}"></p>`
}

export async function persistConversationImagesInHtml(
  message: Pick<Message, 'conversation_id' | 'content'>,
): Promise<string> {
  const content = message.content.trim()
  if (typeof document === 'undefined') return content

  const template = document.createElement('template')
  template.innerHTML = content
  const images = Array.from(
    template.content.querySelectorAll<HTMLImageElement>('img[data-file-id]'),
  )

  await Promise.all(images.map(async (element) => {
    const fileId = element.getAttribute('data-file-id')
    if (!fileId) return
    const name = element.alt || element.getAttribute('data-name') || undefined
    const uploaded = await persistKnowledgeImage({
      conversationId: Number(message.conversation_id),
      fileId,
      name,
      mimeType: imageContentTypeFromName(name) ?? undefined,
    })
    element.setAttribute('src', uploaded.url)
    element.setAttribute('alt', element.alt || uploaded.name || '图片')
    element.setAttribute('title', uploaded.name || element.alt || '图片')
    element.removeAttribute('data-file-id')
    element.removeAttribute('data-name')
  }))

  return template.innerHTML.trim()
}
