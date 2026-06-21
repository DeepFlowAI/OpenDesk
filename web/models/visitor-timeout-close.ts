export type VisitorTimeoutClosePayload = {
  enabled: boolean
  first_normal_minutes: number
  close_normal_minutes: number
  vip_enabled: boolean
  first_vip_minutes: number
  close_vip_minutes: number
  first_reminder_content: string
  close_reminder_content: string
  notify_agent: boolean
  notify_visitor: boolean
}

export type VisitorTimeoutCloseConfig = VisitorTimeoutClosePayload & {
  id: number | null
  tenant_id: number | null
  configured: boolean
  version: number
  updated_by_id: number | null
  updated_by_name: string | null
  updated_at: string | null
}
