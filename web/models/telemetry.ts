export type TelemetryLevel = 'info' | 'warn' | 'error'

export type TelemetryCommon = {
  session_id: string
  device_id: string
  user_id?: string | null
  release?: string
  url?: string
  user_agent?: string
  network_type?: string | null
  viewport?: string
  sdk_name?: string
  sdk_version?: string
  ts_offset_ms?: number
}

export type TelemetryEvent = {
  name: string
  ts: number
  level?: TelemetryLevel
  trace_id?: string | null
  conversation_external_id?: string | null
  request_id?: string | null
  client_message_id?: string | null
  props?: Record<string, string | number | boolean> | null
  metrics?: Record<string, number> | null
}

export type TelemetryBatch = {
  common: TelemetryCommon
  events: TelemetryEvent[]
}

export type TelemetryBatchResponse = {
  accepted: number
  dropped: number
}
