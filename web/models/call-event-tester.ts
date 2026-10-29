export interface CallEventTesterReceiver {
  token: string
  webhook_path: string
  has_secret: boolean
  created_at: string
  expires_in_seconds: number
}

export interface CallEventEnvelope {
  id?: string
  type?: string
  source?: string
  subject?: string
  time?: string
  apiversion?: string
  test?: boolean
  data?: {
    sequence?: number
    call?: Record<string, unknown> & {
      direction?: string
      source?: string
      lifecycle_status?: string
      customer_number?: string
      service_number?: string
    }
    event?: Record<string, unknown> & {
      recording?: {
        public_id?: string
        phase?: string
        status?: string
        duration_ms?: number | null
        download_url?: string | null
        download_url_expires_at?: string | null
        failure_reason?: string | null
      }
    }
  }
}

export interface CallEventTesterEvent {
  seq: number
  received_at: string
  delivery_id: string | null
  user_agent: string | null
  secret_checked: boolean
  secret_ok: boolean
  duplicate: boolean
  body: CallEventEnvelope | string | null
}

export interface CallEventTesterEventList {
  items: CallEventTesterEvent[]
  last_seq: number
}
