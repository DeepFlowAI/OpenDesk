import type { WelcomeMessagePublic } from '@/models/welcome-message-rule'

export type OpenAgentWelcomeMessageBlock =
  | {
      type: 'markdown'
      content: string
      embed_code?: null
      height?: null
    }
  | {
      type: 'embed'
      content?: null
      embed_code: string
      height: number
    }

export type OpenAgentFAQQuestion = {
  text: string
}

export type OpenAgentFAQCategory = {
  name: string
  questions: OpenAgentFAQQuestion[]
}

export type OpenAgentFAQ = {
  enabled: boolean
  title: string
  categories: OpenAgentFAQCategory[]
}

export type OpenAgentWelcomeMessage = {
  enabled: boolean
  blocks: OpenAgentWelcomeMessageBlock[]
  faq?: OpenAgentFAQ | null
}

export type AssistPanelConfigValue =
  | string
  | number
  | boolean
  | null
  | AssistPanelConfigValue[]
  | { [key: string]: AssistPanelConfigValue }

export type ChannelCustomButton = {
  label: string
  action_type: 'send_message' | 'link'
  message: string | null
  url: string | null
  enabled: boolean
}

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
  outside_service_hours_strategy: 'offline_message' | 'leave_message'
  offline_title: string
  offline_message: string
  leave_message_prompt: string
  queue_message: string
  queue_full_message: string
  queue_full_show_leave_message_button: boolean
  queue_full_leave_message_button_label: string
  open_agent_enabled: boolean
  open_agent_agent_id: number | null
  open_agent_agent_name: string | null
  open_agent_bot_strategy: 'always' | 'service_hours'
  open_agent_bot_service_hours_id: number | null
  open_agent_avatar_url: string | null
  open_agent_input_placeholder: string | null
  open_agent_handoff_enabled: boolean
  open_agent_handoff_label: string
  open_agent_handoff_after_messages: number
  open_agent_handoff_behavior: 'confirm' | 'auto'
  open_agent_custom_buttons_enabled: boolean
  open_agent_custom_buttons: ChannelCustomButton[]
  human_custom_buttons_enabled: boolean
  human_custom_buttons: ChannelCustomButton[]
  assist_panel_enabled: boolean
  assist_panel_title: string | null
  assist_panel_react_code: string | null
  assist_panel_config: Record<string, AssistPanelConfigValue>
}

export type ChannelAvailability = {
  can_start_conversation: boolean
  reason: 'available' | 'outside_service_hours' | 'no_available_agent' | 'queue_full'
  offline_title: string
  offline_message: string
  outside_service_hours_strategy: 'offline_message' | 'leave_message'
  leave_message_prompt: string
  queue_message: string
  queue_full_message: string
  queue_full_show_leave_message_button: boolean
  queue_full_leave_message_button_label: string
  current_queue_count: number | null
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
  open_agent_welcome_message: OpenAgentWelcomeMessage | null
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
