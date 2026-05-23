import type { WelcomeMessagePublic } from '@/models/welcome-message-rule'

export type ChannelConfig = {
  title: string | null
  document_title: string | null
  page_bg_color: string | null
  header_gradient_start: string | null
  header_gradient_end: string | null
  header_title_color: string | null
  message_area_bg_color: string | null
  agent_bubble_bg_color: string | null
  agent_bubble_text_color: string | null
  agent_bubble_border_color: string | null
  agent_bubble_radius: [number, number, number, number]
  use_agent_avatar: boolean
  user_bubble_bg_color: string | null
  user_bubble_text_color: string | null
  user_bubble_border_color: string | null
  user_bubble_radius: [number, number, number, number]
  embed_button_bg_color: string | null
  embed_button_icon_color: string | null
  send_button_bg_color: string | null
  input_placeholder: string | null
  service_hours_enabled: boolean
  service_hours_id: number | null
  offline_title: string
  offline_message: string
}

export type ChannelAvailability = {
  can_start_conversation: boolean
  reason: 'available' | 'outside_service_hours' | 'no_available_agent'
  offline_title: string
  offline_message: string
  checked_at: string | null
}

export type Channel = {
  id: number
  channel_key: string
  channel_key_version: number
  public_access_enabled: boolean
  key_rotated_at: string | null
  name: string
  channel_type: string
  access_mode: string
  logo_url: string | null
  favicon_url: string | null
  config: ChannelConfig
  created_at: string
  updated_at: string
}

export type ChannelPublic = Pick<
  Channel,
  'channel_key' | 'name' | 'channel_type' | 'access_mode' | 'logo_url' | 'favicon_url' | 'config'
> & {
  availability: ChannelAvailability | null
  has_conversation_history: boolean
  welcome_message: WelcomeMessagePublic | null
}

export type CreateChannelPayload = {
  name: string
  channel_type?: string
  access_mode?: string
  logo_url?: string | null
  favicon_url?: string | null
  config?: Partial<ChannelConfig>
}

export type UpdateChannelPayload = CreateChannelPayload
