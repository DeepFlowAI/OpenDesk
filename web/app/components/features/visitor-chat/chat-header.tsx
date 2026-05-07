'use client'

import type { ChannelPublicConfig } from '@/service/use-visitor-chat'

type ChatHeaderProps = {
  channel: ChannelPublicConfig
  isMobile: boolean
}

export function ChatHeader({ channel, isMobile }: ChatHeaderProps) {
  const config = channel.config
  const gradientStart = config.header_gradient_start || 'oklch(0.205 0 0)'
  const gradientEnd = config.header_gradient_end || 'oklch(0.205 0 0)'
  const titleColor = config.header_title_color || '#ffffff'
  const title = config.title || channel.name

  return (
    <header
      className="flex shrink-0 items-center gap-3 px-4 py-3"
      style={{
        background: `linear-gradient(to right, ${gradientStart}, ${gradientEnd})`,
        minHeight: isMobile ? 56 : 60,
      }}
    >
      {channel.logo_url && (
        <img
          src={channel.logo_url}
          alt={channel.name}
          className="h-8 w-8 shrink-0 rounded-md object-cover"
        />
      )}
      <h1
        className="truncate text-base font-semibold"
        style={{ color: titleColor }}
      >
        {title}
      </h1>
    </header>
  )
}
