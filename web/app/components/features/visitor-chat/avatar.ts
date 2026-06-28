import type { ChannelConfig } from '@/models/channel'

type AssistantMessageAvatarSource = {
  sender_type: string
  sender_avatar?: string | null
}

export function getOpenAgentAvatarUrl(config: Pick<ChannelConfig, 'open_agent_avatar_url'>): string | null {
  return config.open_agent_avatar_url?.trim() || null
}

export function getAgentDefaultAvatarUrl(config: Pick<ChannelConfig, 'agent_default_avatar_url'>): string | null {
  return config.agent_default_avatar_url?.trim() || null
}

export function getAgentAvatarUrl(
  agentAvatar: string | null | undefined,
  config: Pick<ChannelConfig, 'use_agent_avatar' | 'agent_default_avatar_url'>,
): string | null {
  const defaultAvatar = getAgentDefaultAvatarUrl(config)
  if (config.use_agent_avatar === true) return agentAvatar?.trim() || defaultAvatar
  return defaultAvatar
}

export function shouldShowAgentAvatar(
  agentAvatar: string | null | undefined,
  config: Pick<ChannelConfig, 'use_agent_avatar' | 'agent_default_avatar_url'>,
): boolean {
  return Boolean(getAgentAvatarUrl(agentAvatar, config))
}

export function shouldShowAssistantAvatar(
  source: string | AssistantMessageAvatarSource,
  config: Pick<ChannelConfig, 'use_agent_avatar' | 'agent_default_avatar_url' | 'open_agent_avatar_url'>,
): boolean {
  const senderType = typeof source === 'string' ? source : source.sender_type
  if (senderType === 'bot') return Boolean(getOpenAgentAvatarUrl(config))
  if (senderType === 'agent') {
    const senderAvatar = typeof source === 'string' ? null : source.sender_avatar
    return shouldShowAgentAvatar(senderAvatar, config)
  }
  return false
}

export function getAssistantAvatarSrc(
  message: AssistantMessageAvatarSource,
  config: Pick<ChannelConfig, 'use_agent_avatar' | 'agent_default_avatar_url' | 'open_agent_avatar_url'>,
): string | null {
  if (message.sender_type === 'bot') return getOpenAgentAvatarUrl(config)
  if (message.sender_type === 'agent') return getAgentAvatarUrl(message.sender_avatar, config)
  return null
}
