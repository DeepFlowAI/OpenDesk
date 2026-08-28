export type OutboundPrescreenIntentDraft = {
  intent_key?: string | null
  name: string
  enabled: boolean
  similarity_threshold: number
  is_system: boolean
  positive_examples: string[]
  negative_examples: string[]
}

export type OutboundPrescreenIntent = OutboundPrescreenIntentDraft & {
  id: number
  intent_key: string
  embeddings_ready: boolean
  created_at: string
  updated_at: string
}

export type OutboundPrescreenConfigDraft = {
  intents: OutboundPrescreenIntentDraft[]
}

export type OutboundPrescreenConfig = {
  intents: OutboundPrescreenIntent[]
}

export type OutboundPrescreenDecision = {
  result: 'matched' | 'uncertain'
  auto_hangup: boolean
  intent_key: string | null
  intent_name: string | null
  similarity: number | null
  threshold: number | null
  matched_positive: string | null
  matched_negative: string | null
  negative_similarity: number | null
  reason: string | null
}

export type OutboundPrescreenTestPayload = {
  config: OutboundPrescreenConfigDraft
  text: string
  voiced_ms?: number
  voice_match?: boolean
}
