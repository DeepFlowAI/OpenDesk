import type { Message } from '@/models/conversation'
import type { ConversationFilePayload } from '@/models/conversation-file'
import {
  buildKnowledgeImageHtml,
  knowledgeImageSourceFromMessage,
  persistConversationImagesInHtml,
  persistKnowledgeImage,
  KnowledgeImageTransferError,
} from '@/lib/knowledge-message-image'

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function sanitizeRichTextHtml(html: string): string {
  const withoutBlockedElements = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '')
    .replace(/<(iframe|object|embed)\b[^>]*>[\s\S]*?<\/\1>/gi, '')

  if (typeof document === 'undefined') {
    return withoutBlockedElements
      .replace(/\s+on[a-z]+\s*=\s*(".*?"|'.*?'|[^\s>]+)/gi, '')
      .replace(/\s+(href|src)\s*=\s*("|')\s*javascript:[\s\S]*?\2/gi, '')
      .replace(/\s+(href|src)\s*=\s*javascript:[^\s>]+/gi, '')
  }

  const template = document.createElement('template')
  template.innerHTML = withoutBlockedElements
  template.content.querySelectorAll('script, style, iframe, object, embed').forEach((node) => node.remove())
  template.content.querySelectorAll('*').forEach((node) => {
    Array.from(node.attributes).forEach((attribute) => {
      const name = attribute.name.toLowerCase()
      const value = attribute.value.trim().toLowerCase()
      if (name.startsWith('on')) node.removeAttribute(attribute.name)
      if ((name === 'href' || name === 'src') && value.startsWith('javascript:')) {
        node.removeAttribute(attribute.name)
      }
    })
  })
  return template.innerHTML.trim()
}

function textToParagraphHtml(text: string): string {
  const normalized = text.replace(/\r\n?/g, '\n').trim()
  if (!normalized) return '<p></p>'
  return normalized
    .split(/\n{2,}/)
    .map((paragraph) => `<p>${escapeHtml(paragraph).replaceAll('\n', '<br>')}</p>`)
    .join('')
}

export function knowledgeFilePayloadFromMessage(
  message: Pick<Message, 'content_type' | 'content'>,
): ConversationFilePayload | null {
  if (message.content_type !== 'file') return null
  try {
    const payload = JSON.parse(message.content) as Partial<ConversationFilePayload>
    if (
      payload.schema_version !== 1
      || typeof payload.file_id !== 'string'
      || !payload.file_id
      || typeof payload.name !== 'string'
      || !payload.name
      || typeof payload.size !== 'number'
      || payload.size <= 0
      || typeof payload.mime_type !== 'string'
      || !payload.mime_type
    ) {
      return null
    }
    return payload as ConversationFilePayload
  } catch {
    return null
  }
}

export async function buildKnowledgeDocumentContentFromMessage(
  message: Pick<Message, 'conversation_id' | 'content_type' | 'content'>,
): Promise<string> {
  if (message.content_type === 'image') {
    const source = knowledgeImageSourceFromMessage(message)
    if (!source) {
      throw new KnowledgeImageTransferError('invalid_source', 'Conversation image source is invalid')
    }
    const uploaded = await persistKnowledgeImage(source)
    return buildKnowledgeImageHtml(uploaded, source.name)
  }
  if (message.content_type === 'rich_text') {
    const content = await persistConversationImagesInHtml(message)
    return sanitizeRichTextHtml(content) || '<p></p>'
  }
  return textToParagraphHtml(message.content)
}
