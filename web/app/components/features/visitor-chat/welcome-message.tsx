'use client'

import { useState, type CSSProperties } from 'react'
import { IconChevronRight } from '@tabler/icons-react'
import type { ChannelConfig, OpenAgentFAQ, OpenAgentWelcomeMessageBlock } from '@/models/channel'
import { MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import { buildOpenAgentWelcomeEmbedSrcDoc } from '@/lib/open-agent-welcome-message'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { SafeHtml } from '@/components/safe-html'
import { cn } from '@/lib/utils'

type WelcomeMessageProps = {
  content: string
  config?: ChannelConfig
  showAvatar?: boolean
  avatarSrc?: string | null
  contentFormat?: 'html' | 'markdown'
  align?: 'start' | 'end'
}

type OpenAgentWelcomeMessageProps = {
  blocks: OpenAgentWelcomeMessageBlock[]
  config?: ChannelConfig
  showAvatar?: boolean
  avatarSrc?: string | null
  align?: 'start' | 'end'
}

type OpenAgentFAQMessageProps = {
  faq: OpenAgentFAQ
  config?: ChannelConfig
  showAvatar?: boolean
  reserveAvatarSpace?: boolean
  avatarSrc?: string | null
  faqDisabled?: boolean
  onFAQQuestionClick?: (text: string) => Promise<boolean> | boolean
}

function toCssBorderRadius(radius: [number, number, number, number]): string {
  const [topLeft, topRight, bottomLeft, bottomRight] = radius
  return `${topLeft}px ${topRight}px ${bottomRight}px ${bottomLeft}px`
}

function getAgentBubbleStyle(config?: ChannelConfig): CSSProperties {
  const radius = config?.agent_bubble_radius || [10, 10, 0, 10]
  return {
    backgroundColor: config?.agent_bubble_bg_color || 'var(--color-secondary)',
    color: config?.agent_bubble_text_color || 'var(--color-foreground)',
    borderRadius: toCssBorderRadius(radius),
    border: config?.agent_bubble_border_color
      ? `1px solid ${config.agent_bubble_border_color}`
      : undefined,
  }
}

export function WelcomeMessage({
  content,
  config,
  showAvatar = false,
  avatarSrc,
  contentFormat = 'html',
  align = 'start',
}: WelcomeMessageProps) {
  const bubbleClassName = cn(
    'min-h-[42px] max-w-[75%] min-w-0 whitespace-pre-wrap break-words break-all px-3 py-2 text-sm leading-6',
    richTextListStyleClass,
    contentFormat === 'markdown' && markdownTextRootClass,
  )

  return (
    <div className={cn('flex items-end gap-2 px-5', align === 'end' ? 'flex-row-reverse' : 'flex-row')}>
      {showAvatar && avatarSrc && (
        <img
          src={avatarSrc}
          alt=""
          className="h-9 w-9 shrink-0 rounded-full object-cover"
        />
      )}
      {contentFormat === 'markdown' ? (
        <div className={bubbleClassName} style={getAgentBubbleStyle(config)}>
          <MarkdownText>{content}</MarkdownText>
        </div>
      ) : (
        <SafeHtml
          html={content}
          className={bubbleClassName}
          style={getAgentBubbleStyle(config)}
        />
      )}
    </div>
  )
}

export function OpenAgentWelcomeMessage({
  blocks,
  config,
  showAvatar = false,
  avatarSrc,
  align = 'start',
}: OpenAgentWelcomeMessageProps) {
  return (
    <div className={cn('flex items-end gap-2 px-5', align === 'end' ? 'flex-row-reverse' : 'flex-row')}>
      {showAvatar && avatarSrc && (
        <img
          src={avatarSrc}
          alt=""
          className="h-9 w-9 shrink-0 rounded-full object-cover"
        />
      )}
      <div
        className={cn(
          'min-h-[42px] max-w-[75%] min-w-0 break-words break-all px-3 py-2 text-sm leading-6',
          markdownTextRootClass,
          richTextListStyleClass,
        )}
        style={getAgentBubbleStyle(config)}
      >
        <div className="space-y-3">
          {blocks.map((block, index) => (
            block.type === 'markdown' ? (
              <MarkdownText key={`open-agent-welcome-md-${index}`}>
                {block.content}
              </MarkdownText>
            ) : (
              <iframe
                key={`open-agent-welcome-embed-${index}`}
                title={`open agent welcome embed ${index + 1}`}
                srcDoc={buildOpenAgentWelcomeEmbedSrcDoc(block.embed_code)}
                sandbox="allow-scripts allow-forms allow-popups allow-presentation"
                allow="autoplay; fullscreen; picture-in-picture"
                className="block w-full rounded-lg border border-border bg-white"
                style={{ height: block.height, maxHeight: '45vh' }}
              />
            )
          ))}
        </div>
      </div>
    </div>
  )
}

export function OpenAgentFAQMessage({
  faq,
  config,
  showAvatar = false,
  reserveAvatarSpace = false,
  avatarSrc,
  faqDisabled = false,
  onFAQQuestionClick,
}: OpenAgentFAQMessageProps) {
  const [activeCategoryIndex, setActiveCategoryIndex] = useState(0)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const activeCategory = faq.categories[activeCategoryIndex] || faq.categories[0]
  const buttonStyle = {
    '--opendesk-faq-button-bg': config?.send_button_bg_color || 'var(--color-primary)',
  } as CSSProperties

  async function handleQuestionClick(text: string) {
    if (!onFAQQuestionClick || faqDisabled || pendingQuestion) return
    setPendingQuestion(text)
    try {
      await onFAQQuestionClick(text)
    } finally {
      setPendingQuestion(null)
    }
  }

  return (
    <div className="flex flex-row items-end gap-2 px-5">
      {showAvatar && avatarSrc && (
        <img
          src={avatarSrc}
          alt=""
          className="h-9 w-9 shrink-0 rounded-full object-cover"
        />
      )}
      {!showAvatar && reserveAvatarSpace && (
        <span aria-hidden="true" className="h-9 w-9 shrink-0" />
      )}
      <div
        className="min-h-[42px] max-w-[75%] min-w-0 break-words break-all px-4 py-3 text-sm leading-6"
        style={{ ...getAgentBubbleStyle(config), ...buttonStyle }}
      >
        <div className="mb-3 text-sm font-semibold">{faq.title}</div>
        {faq.categories.length > 1 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {faq.categories.map((category, index) => {
              const active = index === activeCategoryIndex
              return (
                <button
                  key={`${category.name}-${index}`}
                  type="button"
                  className={cn(
                    'rounded-full border px-3 py-1.5 text-sm font-medium leading-5 transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                    active
                      ? 'border-[var(--opendesk-faq-button-bg)] bg-[var(--opendesk-faq-button-bg)] text-white'
                      : 'border-[var(--opendesk-faq-button-bg)] bg-white text-[var(--opendesk-faq-button-bg)] hover:opacity-90',
                  )}
                  onClick={() => setActiveCategoryIndex(index)}
                  disabled={faqDisabled || Boolean(pendingQuestion)}
                >
                  {category.name}
                </button>
              )
            })}
          </div>
        )}
        <div className="flex flex-col gap-1">
          {activeCategory.questions.map((question, index) => (
            <button
              key={`${question.text}-${index}`}
              type="button"
              className="flex w-full items-center justify-between gap-3 rounded-md py-1.5 text-left text-sm leading-6 transition-colors hover:bg-black/5 disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void handleQuestionClick(question.text)}
              disabled={faqDisabled || Boolean(pendingQuestion)}
            >
              <span className="min-w-0 flex-1 break-words">{question.text}</span>
              <IconChevronRight size={18} stroke={1.75} className="shrink-0 opacity-45" aria-hidden />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
