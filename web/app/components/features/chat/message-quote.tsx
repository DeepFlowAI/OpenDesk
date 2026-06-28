'use client'

import { IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import {
  quoteAriaLabel,
  quoteSenderLabel,
  quoteSummaryLabel,
  shouldShowQuoteSenderLabel,
  type QuoteAudience,
} from '@/lib/message-quote'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import type { Locale } from '@/context/locale-store'
import type { Message, MessageQuote } from '@/models/conversation'

type QuoteAttachmentContext = {
  conversationId?: number
  conversationPublicId?: string
  visitorSessionToken?: string
}

type MessageQuotePreviewProps = {
  quote: MessageQuote
  locale: Locale
  original?: Message | null
  onRemove?: () => void
  className?: string
  audience?: QuoteAudience
  attachmentContext?: QuoteAttachmentContext
}

type MessageQuoteBlockProps = {
  quote: MessageQuote
  locale: Locale
  original?: Message | null
  onClick?: () => void
  className?: string
  variant?: 'default' | 'embedded'
  audience?: QuoteAudience
  attachmentContext?: QuoteAttachmentContext
}

function quoteAttachmentNode(
  quote: MessageQuote,
  original: Message | null | undefined,
  attachmentContext?: QuoteAttachmentContext,
) {
  const recalled = quote.is_recalled || Boolean(original?.is_recalled)
  if (recalled || !original) return null
  if (quote.content_type !== 'image' && quote.content_type !== 'file') return null
  return (
    <MessageAttachment
      compact
      contentType={quote.content_type}
      content={original.content}
      conversationId={attachmentContext?.conversationId}
      conversationPublicId={attachmentContext?.conversationPublicId}
      visitorSessionToken={attachmentContext?.visitorSessionToken}
    />
  )
}

export function MessageQuotePreview({
  quote,
  locale,
  original,
  onRemove,
  className,
  audience = 'workspace',
  attachmentContext,
}: MessageQuotePreviewProps) {
  const senderLabel = shouldShowQuoteSenderLabel(quote, audience)
    ? quoteSenderLabel(quote, locale)
    : null
  const attachmentNode = quoteAttachmentNode(quote, original, attachmentContext)

  return (
    <div
      className={cn(
        'flex min-w-0 items-stretch bg-muted/60 py-2 pr-3 text-sm',
        className,
      )}
      aria-label={quoteAriaLabel(quote, locale, original, audience)}
    >
      <div className="w-[3px] shrink-0 self-stretch bg-current/25" aria-hidden />
      <div className="min-w-0 flex-1 pl-3">
        {senderLabel && (
          <div className="truncate text-xs font-medium text-foreground">
            {senderLabel}
          </div>
        )}
        {attachmentNode ? (
          <div className={cn(senderLabel && 'mt-1')}>{attachmentNode}</div>
        ) : (
          <div
            className={cn(
              'line-clamp-2 break-words text-xs leading-5 text-muted-foreground',
              senderLabel && 'mt-0.5',
            )}
          >
            {quoteSummaryLabel(quote, locale, original)}
          </div>
        )}
      </div>
      {onRemove && (
        <button
          type="button"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          onClick={onRemove}
          aria-label={locale === 'zh' ? '取消引用' : 'Remove quote'}
          title={locale === 'zh' ? '取消引用' : 'Remove quote'}
        >
          <IconX size={14} aria-hidden />
        </button>
      )}
    </div>
  )
}

export function MessageQuoteBlock({
  quote,
  locale,
  original,
  onClick,
  className,
  variant = 'default',
  audience = 'workspace',
  attachmentContext,
}: MessageQuoteBlockProps) {
  const senderLabel = shouldShowQuoteSenderLabel(quote, audience)
    ? quoteSenderLabel(quote, locale)
    : null
  const attachmentNode = quoteAttachmentNode(quote, original, attachmentContext)

  const content = variant === 'embedded' ? (
    <div className="min-w-0 border-l-[3px] border-current/25 pl-3 text-current">
      {senderLabel && (
        <div className="truncate text-[13px] font-semibold leading-5 opacity-60">
          {senderLabel}
          {locale === 'zh' ? '：' : ':'}
        </div>
      )}
      {attachmentNode ? (
        <div className={cn(senderLabel && 'mt-1')}>{attachmentNode}</div>
      ) : (
        <div
          className={cn(
            'line-clamp-3 break-words text-[13px] leading-6 opacity-60',
            senderLabel && 'mt-1',
          )}
        >
          {quoteSummaryLabel(quote, locale, original)}
        </div>
      )}
    </div>
  ) : (
    <>
      {senderLabel && (
        <div className="truncate text-[11px] font-medium text-muted-foreground">
          {senderLabel}
        </div>
      )}
      {attachmentNode ? (
        <div className={cn(senderLabel && 'mt-0.5')}>{attachmentNode}</div>
      ) : (
        <div
          className={cn(
            'line-clamp-2 break-words text-[12px] leading-5 text-muted-foreground',
            senderLabel && 'mt-0.5',
          )}
        >
          {quoteSummaryLabel(quote, locale, original)}
        </div>
      )}
    </>
  )

  const baseClass = cn(
    variant === 'embedded'
      ? 'w-full min-w-0 bg-transparent p-0 text-left'
      : 'mb-2 w-full min-w-0 border-l-2 border-border bg-muted/60 px-2.5 py-1.5 text-left',
    className,
  )

  if (!onClick) {
    return (
      <div className={baseClass} aria-label={quoteAriaLabel(quote, locale, original, audience)}>
        {content}
      </div>
    )
  }

  return (
    <button
      type="button"
      className={cn(
        baseClass,
        variant === 'embedded'
          ? 'transition-opacity hover:opacity-80'
          : 'transition-colors hover:bg-muted',
      )}
      onClick={onClick}
      aria-label={quoteAriaLabel(quote, locale, original, audience)}
    >
      {content}
    </button>
  )
}
