import type { Message } from '@/models/conversation'
import type { KnowledgeInspirationContentFormat, KnowledgeInspirationPayload } from '@/models/knowledge'
import {
  buildKnowledgeImageHtml,
  knowledgeImageSourceFromMessage,
  persistConversationImagesInHtml,
  persistKnowledgeImage,
  KnowledgeImageTransferError,
} from '@/lib/knowledge-message-image'

const RICH_TEXT_HTML_PATTERN =
  /<\s*(p|br|strong|b|em|i|u|ul|ol|li|h[1-6]|span|div|a|blockquote|mark|img)\b/i

export function messageContentLooksLikeHtml(content: string): boolean {
  return RICH_TEXT_HTML_PATTERN.test(content.trim())
}

export function resolveKnowledgeInspirationContentFormat(
  message: Pick<Message, 'content_type' | 'content'>,
): KnowledgeInspirationContentFormat {
  if (message.content_type === 'image') return 'rich_text'
  if (message.content_type === 'rich_text') return 'rich_text'
  if (messageContentLooksLikeHtml(message.content)) return 'rich_text'
  return 'text'
}

async function normalizeKnowledgeInspirationContent(message: Message): Promise<string> {
  const content = message.content.trim()
  if (message.content_type === 'image') {
    const source = knowledgeImageSourceFromMessage(message)
    if (!source) {
      throw new KnowledgeImageTransferError('invalid_source', 'Conversation image source is invalid')
    }
    const uploaded = await persistKnowledgeImage(source)
    return buildKnowledgeImageHtml(uploaded, source.name)
  }
  if (resolveKnowledgeInspirationContentFormat(message) !== 'rich_text') return content
  return persistConversationImagesInHtml(message)
}

export async function buildKnowledgeInspirationPayloadFromMessage(
  message: Message,
): Promise<KnowledgeInspirationPayload> {
  const contentFormat = resolveKnowledgeInspirationContentFormat(message)
  return {
    content: await normalizeKnowledgeInspirationContent(message),
    content_format: contentFormat,
    source_conversation_id: Number(message.conversation_id),
    source_message_id: Number(message.id),
  }
}
