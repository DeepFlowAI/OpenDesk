import type { Locale } from '@/context/locale-store'
import type { Message, MessageQuote } from '@/models/conversation'

const QUOTABLE_CONTENT_TYPES = new Set(['text', 'rich_text', 'image', 'file'])
const QUOTABLE_SENDER_TYPES = new Set(['visitor', 'agent', 'bot'])
const QUOTE_SUMMARY_MAX_LENGTH = 80

type FileContent = {
  name?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function fileNameFromContent(content: string): string | null {
  try {
    const parsed = JSON.parse(content) as unknown
    if (!isRecord(parsed)) return null
    const name = (parsed as FileContent).name
    return typeof name === 'string' && name.trim() ? name.trim() : null
  } catch {
    return null
  }
}

function stripHtml(html: string): string {
  if (typeof document !== 'undefined') {
    const div = document.createElement('div')
    div.innerHTML = html
    return (div.textContent || '').replace(/\s+/g, ' ').trim()
  }
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
}

function fallbackSenderName(senderType: string, locale: Locale): string {
  if (senderType === 'visitor') return locale === 'zh' ? '访客' : 'Visitor'
  if (senderType === 'agent') return locale === 'zh' ? '客服' : 'Agent'
  if (senderType === 'bot') return locale === 'zh' ? '机器人' : 'Bot'
  return locale === 'zh' ? '消息' : 'Message'
}

export function messageQuoteFromMetadata(metadata?: Record<string, unknown> | null): MessageQuote | null {
  const value = metadata?.quote
  if (!isRecord(value)) return null
  if (value.schema_version !== 1) return null
  if (typeof value.message_id !== 'number') return null
  if (typeof value.sender_type !== 'string') return null
  if (typeof value.content_type !== 'string') return null
  return {
    schema_version: 1,
    message_id: value.message_id,
    sender_type: value.sender_type as MessageQuote['sender_type'],
    sender_id: typeof value.sender_id === 'number' ? value.sender_id : null,
    sender_name: typeof value.sender_name === 'string' ? value.sender_name : null,
    content_type: value.content_type as MessageQuote['content_type'],
    summary: typeof value.summary === 'string' ? value.summary : undefined,
    file_name: typeof value.file_name === 'string' ? value.file_name : undefined,
    is_recalled: value.is_recalled === true,
  }
}

export function canQuoteMessage(message: Message, options?: {
  canSend?: boolean
  webChannel?: boolean
  closed?: boolean
}): boolean {
  if (options?.canSend === false || options?.webChannel === false || options?.closed === true) return false
  if (!message.id || message.id <= 0 || message.is_recalled) return false
  if (!QUOTABLE_CONTENT_TYPES.has(message.content_type)) return false
  return QUOTABLE_SENDER_TYPES.has(message.sender_type)
}

export function quoteFromMessage(message: Message, locale: Locale): MessageQuote {
  const fileName = message.content_type === 'file' ? fileNameFromContent(message.content) : null
  let summary = ''
  if (message.content_type === 'text') {
    summary = message.content.trim().slice(0, QUOTE_SUMMARY_MAX_LENGTH)
  } else if (message.content_type === 'rich_text') {
    const plain = stripHtml(message.content)
    if (plain) {
      summary = plain.slice(0, QUOTE_SUMMARY_MAX_LENGTH)
    } else if (/<img\b/i.test(message.content)) {
      summary = locale === 'zh' ? '图片' : 'Image'
    } else {
      summary = locale === 'zh' ? '富文本' : 'Rich text'
    }
  } else if (message.content_type === 'image') {
    summary = locale === 'zh' ? '图片' : 'Image'
  } else if (message.content_type === 'file') {
    summary = fileName
      ? `${locale === 'zh' ? '文件：' : 'File: '}${fileName}`
      : locale === 'zh' ? '文件' : 'File'
  }

  return {
    schema_version: 1,
    message_id: message.id,
    sender_type: message.sender_type,
    sender_id: message.sender_id,
    sender_name: message.sender_name || fallbackSenderName(message.sender_type, locale),
    content_type: message.content_type,
    summary,
    ...(fileName ? { file_name: fileName } : {}),
    ...(message.is_recalled ? { is_recalled: true } : {}),
  }
}

export type QuoteAudience = 'workspace' | 'visitor'

export function quoteSenderLabel(quote: MessageQuote, locale: Locale): string {
  return quote.sender_name || fallbackSenderName(quote.sender_type, locale)
}

export function shouldShowQuoteSenderLabel(
  quote: MessageQuote,
  audience: QuoteAudience = 'workspace',
): boolean {
  if (quote.sender_type === 'agent') return false
  if (audience === 'visitor' && quote.sender_type === 'visitor') return false
  return true
}

export function quoteSummaryLabel(
  quote: MessageQuote,
  locale: Locale,
  original?: Message | null,
): string {
  if (quote.is_recalled || original?.is_recalled) {
    return locale === 'zh' ? '原消息已撤回' : 'Original message was recalled'
  }
  if (quote.content_type === 'image') return locale === 'zh' ? '图片' : 'Image'
  if (quote.content_type === 'file') {
    const fileName = quote.file_name || (original ? fileNameFromContent(original.content) : null)
    return fileName
      ? `${locale === 'zh' ? '文件：' : 'File: '}${fileName}`
      : locale === 'zh' ? '文件' : 'File'
  }
  const summary = original
    ? quoteFromMessage(original, locale).summary
    : quote.summary
  return summary?.trim() || (locale === 'zh' ? '原消息不可查看' : 'Original message unavailable')
}

export function quoteAriaLabel(
  quote: MessageQuote,
  locale: Locale,
  original?: Message | null,
  audience: QuoteAudience = 'workspace',
): string {
  const summary = quoteSummaryLabel(quote, locale, original)
  if (!shouldShowQuoteSenderLabel(quote, audience)) {
    return locale === 'zh'
      ? `引用消息：${summary}`
      : `Quoted message: ${summary}`
  }
  const sender = quoteSenderLabel(quote, locale)
  return locale === 'zh'
    ? `引用 ${sender} 的消息：${summary}`
    : `Quoted message from ${sender}: ${summary}`
}
