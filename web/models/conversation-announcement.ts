import type { PaginatedResponse } from '@/models/common'
import type { WelcomeMessageCondition } from '@/models/welcome-message-rule'

export type AnnouncementTimeRangeType = 'permanent' | 'limited'
export type AnnouncementTimeStatus = 'permanent' | 'active' | 'not_started' | 'expired'
export type AnnouncementBackgroundColor = 'yellow' | 'green' | 'blue' | 'pink' | 'purple' | 'gray'

export type ConversationAnnouncementCondition = WelcomeMessageCondition

export type ConversationAnnouncementListItem = {
  id: number
  priority: number
  name: string
  enabled: boolean
  time_range_type: AnnouncementTimeRangeType
  start_at: string | null
  end_at: string | null
  conditions: ConversationAnnouncementCondition[]
  auto_popup: boolean
  background_color: AnnouncementBackgroundColor
  time_status: AnnouncementTimeStatus
  created_at: string | null
  updated_at: string | null
}

export type ConversationAnnouncement = ConversationAnnouncementListItem & {
  summary_html: string
  detail_html: string
}

export type ConversationAnnouncementPublic = {
  id: number
  name: string
  summary_html: string
  detail_html: string
  auto_popup: boolean
  background_color: AnnouncementBackgroundColor
}

export type ConversationAnnouncementListResponse = PaginatedResponse<ConversationAnnouncementListItem>

export type SaveConversationAnnouncementPayload = {
  name: string
  enabled: boolean
  time_range_type: AnnouncementTimeRangeType
  start_at: string | null
  end_at: string | null
  conditions: ConversationAnnouncementCondition[]
  auto_popup: boolean
  background_color: AnnouncementBackgroundColor
  summary_html: string
  detail_html: string
}

export const ANNOUNCEMENT_BACKGROUND_VALUES: Record<AnnouncementBackgroundColor, string> = {
  yellow: '#FFF6CC',
  green: '#E8F7E9',
  blue: '#EAF3FF',
  pink: '#FFECEF',
  purple: '#F1ECFF',
  gray: '#F4F4F2',
}
