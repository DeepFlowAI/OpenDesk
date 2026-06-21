import type { AgentBrief, ChannelBrief, GroupBrief, Message, VisitorBrief } from '@/models/conversation'

export type QueueWorkspaceQueueBrief = {
  queue_type: 'employee_group' | 'employee' | string
  queue_id: number
  name: string | null
  waiting_count: number
}

export type QueueWorkspaceTask = {
  id: number
  source: 'queue_task'
  queue_task_id: number
  conversation_id: number | null
  conversation_public_id: string | null
  visitor: VisitorBrief | null
  channel: ChannelBrief | null
  group: GroupBrief | null
  queue: QueueWorkspaceQueueBrief
  priority: number
  status: string
  source_type: string
  last_message_preview: string | null
  last_message_at: string | null
  enqueued_at: string | null
  wait_seconds: number
  position_overall: number | null
  position_in_priority: number | null
}

export type QueueWorkspaceTaskListResponse = {
  items: QueueWorkspaceTask[]
  total: number
  visible_queues: QueueWorkspaceQueueBrief[]
}

export type QueueWorkspaceCountResponse = {
  total: number
}

export type QueueWorkspaceTaskDetail = QueueWorkspaceTask & {
  messages: Message[]
  can_assign_self: boolean
  can_assign_other: boolean
}

export type QueueAssignableAgent = {
  id: number
  name: string
  display_name: string | null
  job_number: string | null
  avatar: string | null
  group_ids: number[]
  group_names: string[]
  online_status: 'online' | 'busy' | 'offline' | string
  current_count: number
  max_concurrent: number
  selectable: boolean
}

export type QueueAssignableAgentListResponse = {
  items: QueueAssignableAgent[]
  total: number
}

export type QueueAssignmentWorkspaceResponse = {
  task: QueueWorkspaceTask
  conversation_id: number | null
  assigned_agent: AgentBrief | null
  assigned_to_current_user: boolean
}
