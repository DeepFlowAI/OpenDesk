export type EventDeliveryStatus = 'pending' | 'processing' | 'succeeded' | 'failed'

export type EventDeliverySummary = {
  status: EventDeliveryStatus
  http_status: number | null
  duration_ms: number | null
  error_type: string | null
  attempted_at: string | null
}

export type EventSubscription = {
  public_id: string
  name: string
  endpoint_url: string
  description: string | null
  masked_secret: string
  secret_version: number
  is_active: boolean
  disabled_at: string | null
  created_at: string | null
  updated_at: string | null
  recent_delivery: EventDeliverySummary | null
}

export type EventSubscriptionList = {
  items: EventSubscription[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type EventSubscriptionPayload = {
  name: string
  endpoint_url: string
  description?: string | null
}

export type EventSubscriptionSecretResponse = {
  record: EventSubscription
  secret: string
}

export type EventSubscriptionTestResult = {
  delivery_id: string
  status: 'succeeded' | 'failed'
  http_status: number | null
  duration_ms: number
  error_type: string | null
}

export type EventSubscriptionListParams = {
  page: number
  per_page?: number
  q?: string
  status?: 'active' | 'disabled'
}
