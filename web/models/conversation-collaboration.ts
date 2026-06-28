import type { AgentBrief, Conversation } from '@/models/conversation'

export type CollaborationOnlineStatus = 'online' | 'busy' | 'offline'
export type CollaborationInvitationStatus = 'pending' | 'accepted' | 'declined' | 'canceled' | 'expired'

export type CollaborationTarget = {
  id: number
  name: string
  display_name: string | null
  job_number: string | null
  avatar: string | null
  online_status: CollaborationOnlineStatus
  current_count: number
  max_concurrent: number
  available: boolean
  disabled_reason: 'already_joined' | 'pending' | 'offline' | null
}

export type CollaborationTargetListResponse = {
  items: CollaborationTarget[]
  total: number
}

export type CollaborationInvitation = {
  id: number
  conversation_id: number
  status: CollaborationInvitationStatus
  inviter: AgentBrief | null
  invitee: AgentBrief | null
  owner: AgentBrief | null
  visitor_name: string | null
  channel_name: string | null
  last_message_preview: string | null
  expires_at: string
  responded_at: string | null
  created_at: string
}

export type CollaborationInvitationListResponse = {
  items: CollaborationInvitation[]
  total: number
}

export type CollaborationInvitationRespondResponse = {
  invitation: CollaborationInvitation
  conversation: Conversation | null
}
