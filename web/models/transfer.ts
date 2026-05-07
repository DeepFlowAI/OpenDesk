export type TransferOnlineStatus = 'online' | 'busy' | 'offline'

export type TransferTarget = {
  id: number
  name: string
  display_name: string | null
  job_number: string | null
  avatar: string | null
  online_status: TransferOnlineStatus
  current_count: number
  max_concurrent: number
}

export type TransferTargetListResponse = {
  items: TransferTarget[]
  total: number
}

export type TransferConversationRequest = {
  target_agent_id: number
}
