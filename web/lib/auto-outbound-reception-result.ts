/**
 * Summarize auto-outbound reception_result for the call-records table.
 * Never paste raw JSON into cells — keep a single-line locale-aware label.
 */

import type { Locale } from '@/context/locale-store'
import type { AutoOutboundReceptionType } from '@/models/auto-outbound-task'
import { t } from '@/utils/i18n'

const AGENT_META_KEYS = new Set([
  'auto_submitted',
  'submitted_by',
  'submitted_at',
  'assigned',
  'agent_id',
  'degraded',
  'abandoned',
  'reason',
  'abandon_prompt',
  'exit',
  'error',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseResult(
  result: Record<string, unknown> | string | null | undefined,
): Record<string, unknown> | null {
  if (result == null || result === '') return null
  if (typeof result === 'string') {
    const trimmed = result.trim()
    if (!trimmed) return null
    try {
      const parsed: unknown = JSON.parse(trimmed)
      return isRecord(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return isRecord(result) ? result : null
}

function formatScalar(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

function summarizeCollected(collected: unknown): string {
  if (!isRecord(collected)) return ''
  const parts: string[] = []
  for (const [key, value] of Object.entries(collected)) {
    const text = formatScalar(value)
    if (!key || !text) continue
    parts.push(`${key}=${text}`)
  }
  return parts.join(', ')
}

function extractIntent(result: Record<string, unknown>): string {
  for (const key of ['intent', 'intent_label', 'intention', 'label', 'tag'] as const) {
    const text = formatScalar(result[key])
    if (text) return text
  }
  return ''
}

function isTransferred(result: Record<string, unknown>): boolean {
  return result.handoff === true || result.transferred === true || result.transfer === true
}

function extractAgentFields(result: Record<string, unknown>): Record<string, unknown> {
  const nested = result.field_values
  if (isRecord(nested)) return nested
  const fields: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(result)) {
    if (AGENT_META_KEYS.has(key)) continue
    if (key === 'field_values') continue
    fields[key] = value
  }
  return fields
}

function joinParts(parts: string[]): string {
  return parts.filter(Boolean).join(' · ')
}

function summarizeIvr(result: Record<string, unknown>, locale: Locale): string {
  const parts: string[] = []
  const exit = formatScalar(result.exit)
  if (exit) {
    parts.push(t('ws.autoOutbound.records.result.ivrExit', locale, { exit }))
  }
  const collected = summarizeCollected(result.collected)
  if (collected) {
    parts.push(t('ws.autoOutbound.records.result.ivrCollected', locale, { summary: collected }))
  }
  return parts.length ? joinParts(parts) : t('ws.autoOutbound.records.result.empty', locale)
}

function summarizeBot(result: Record<string, unknown>, locale: Locale): string {
  const parts: string[] = []
  const intent = extractIntent(result)
  if (intent) parts.push(intent)
  if (isTransferred(result)) {
    parts.push(t('ws.autoOutbound.records.result.botTransfer', locale))
  }
  return parts.length ? joinParts(parts) : t('ws.autoOutbound.records.result.empty', locale)
}

function summarizeAgent(result: Record<string, unknown>, locale: Locale): string {
  const fields = extractAgentFields(result)
  const entries = Object.entries(fields).filter(([, value]) => formatScalar(value) !== '')
  if (entries.length === 0) {
    return t('ws.autoOutbound.records.result.empty', locale)
  }
  if (entries.length === 1) {
    const [key, value] = entries[0]!
    return t('ws.autoOutbound.records.result.agentField', locale, {
      key,
      value: formatScalar(value),
    })
  }
  return t('ws.autoOutbound.records.result.agentFields', locale, { count: entries.length })
}

function resolveKind(
  result: Record<string, unknown>,
  receptionType: AutoOutboundReceptionType | null | undefined,
): 'abandoned' | 'ivr' | 'bot' | 'agent' | 'empty' {
  if (result.abandoned === true) return 'abandoned'
  if (receptionType === 'ivr') return 'ivr'
  if (receptionType === 'bot') return 'bot'
  if (receptionType === 'agent') return 'agent'
  if (receptionType === 'none') return 'empty'

  // Infer from payload when reception_type is missing.
  if ('intent' in result || 'handoff' in result || 'transferred' in result || 'transfer' in result) {
    return 'bot'
  }
  if ('exit' in result || 'collected' in result) return 'ivr'
  if ('field_values' in result || 'submitted_by' in result || 'auto_submitted' in result) {
    return 'agent'
  }
  if (Object.keys(extractAgentFields(result)).length > 0) return 'agent'
  return 'empty'
}

/**
 * Render reception_result + reception_type as a short one-line summary.
 */
export function summarizeReceptionResult(
  result: Record<string, unknown> | string | null | undefined,
  receptionType: AutoOutboundReceptionType | null | undefined,
  locale: Locale,
): string {
  const parsed = parseResult(result)
  if (!parsed) return t('ws.autoOutbound.records.result.empty', locale)

  const kind = resolveKind(parsed, receptionType)
  if (kind === 'abandoned') {
    return t('ws.autoOutbound.records.result.abandoned', locale)
  }
  if (kind === 'ivr') return summarizeIvr(parsed, locale)
  if (kind === 'bot') return summarizeBot(parsed, locale)
  if (kind === 'agent') return summarizeAgent(parsed, locale)
  return t('ws.autoOutbound.records.result.empty', locale)
}
