import type { ChannelConfig } from '@/models/channel'

type AssistantMessageAvatarSource = {
  sender_type: string
  sender_avatar?: string | null
}

export function getOpenAgentAvatarUrl(config: Pick<ChannelConfig, 'open_agent_avatar_url'>): string | null {
  return config.open_agent_avatar_url?.trim() || null
}

export function shouldShowAssistantAvatar(
  senderType: string,
  config: Pick<ChannelConfig, 'use_agent_avatar' | 'open_agent_avatar_url'>,
): boolean {
  if (senderType === 'bot') return Boolean(getOpenAgentAvatarUrl(config))
  if (senderType === 'agent') return config.use_agent_avatar === true
  return false
}

export function getAssistantAvatarSrc(
  message: AssistantMessageAvatarSource,
  config: Pick<ChannelConfig, 'open_agent_avatar_url'>,
): string | null {
  if (message.sender_type === 'bot') return getOpenAgentAvatarUrl(config)
  return message.sender_avatar || null
}
