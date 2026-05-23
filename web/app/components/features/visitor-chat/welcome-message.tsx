'use client'

import type { CSSProperties } from 'react'
import type { ChannelConfig } from '@/models/channel'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'

const DEFAULT_AGENT_AVATAR_SRC = '/default-avatar.jpg'

type WelcomeMessageProps = {
  content: string
  config?: ChannelConfig
  showAvatar?: boolean
  avatarSrc?: string | null
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
}: WelcomeMessageProps) {
  return (
    <div className="flex flex-row items-end gap-2 px-5">
      {showAvatar && (
        <img
          src={avatarSrc || DEFAULT_AGENT_AVATAR_SRC}
          alt=""
          className="h-9 w-9 shrink-0 rounded-full object-cover"
        />
      )}
      <div
        className={`min-h-[42px] max-w-[75%] whitespace-pre-wrap break-words px-3 py-2 text-sm leading-6 ${richTextListStyleClass}`}
        style={getAgentBubbleStyle(config)}
        dangerouslySetInnerHTML={{ __html: content }}
      />
    </div>
  )
}
