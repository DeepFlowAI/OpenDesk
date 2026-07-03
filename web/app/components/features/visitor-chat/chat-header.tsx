'use client'

import type { ChannelPublicConfig } from '@/service/use-visitor-chat'
import { IconVolume, IconVolumeOff, IconX } from '@tabler/icons-react'
import { cn } from '@/lib/utils'

type ChatHeaderProps = {
  channel: ChannelPublicConfig
  isMobile: boolean
  isEmbed?: boolean
  onEmbedClose?: () => void
  locale?: string
  messageSoundEnabled?: boolean
  onMessageSoundEnabledChange?: (enabled: boolean) => void
}

export function ChatHeader({
  channel,
  isMobile,
  isEmbed = false,
  onEmbedClose,
  locale = 'zh',
  messageSoundEnabled,
  onMessageSoundEnabledChange,
}: ChatHeaderProps) {
  const config = channel.config
  const gradientStart = config.header_gradient_start || 'oklch(0.205 0 0)'
  const gradientEnd = config.header_gradient_end || 'oklch(0.205 0 0)'
  const titleColor = config.header_title_color || '#ffffff'
  const title = config.title || channel.name
  const canToggleSound = typeof messageSoundEnabled === 'boolean' && typeof onMessageSoundEnabledChange === 'function'
  const soundEnabled = messageSoundEnabled === true
  const soundLabel = soundEnabled
    ? locale === 'zh'
      ? '关闭消息提醒音'
      : 'Mute message sound'
    : locale === 'zh'
      ? '开启消息提醒音'
      : 'Unmute message sound'
  const handleSoundToggle = () => {
    if (typeof messageSoundEnabled !== 'boolean') return
    onMessageSoundEnabledChange?.(!messageSoundEnabled)
  }

  return (
    <header
      className={cn(
        'flex shrink-0 items-center gap-3 px-4 py-3',
        isEmbed && 'overflow-hidden rounded-t-[14px]',
      )}
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
        className="min-w-0 flex-1 truncate text-base font-semibold"
        style={{ color: titleColor }}
      >
        {title}
      </h1>
      {canToggleSound && (
        <button
          type="button"
          aria-label={soundLabel}
          aria-pressed={soundEnabled}
          title={soundLabel}
          className={cn(
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60',
            !soundEnabled && 'opacity-75',
          )}
          style={{ color: titleColor }}
          onClick={handleSoundToggle}
        >
          {soundEnabled ? <IconVolume size={18} /> : <IconVolumeOff size={18} />}
        </button>
      )}
      {isEmbed && (
        <button
          type="button"
          aria-label="Close chat"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
          style={{ color: titleColor }}
          onClick={onEmbedClose}
        >
          <IconX size={18} />
        </button>
      )}
    </header>
  )
}
