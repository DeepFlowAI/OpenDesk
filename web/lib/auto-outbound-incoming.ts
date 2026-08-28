/**
 * Helpers for auto-outbound agent dispatch on the call-center workspace.
 * Keep push-shape checks pure so unit tests do not need React / socket mocks.
 */

import type { Locale } from '@/context/locale-store'
import type { IncomingCall } from '@/lib/call-session-reducer'
import { t } from '@/utils/i18n'

export const AUTO_OUTBOUND_SOURCE = 'auto_outbound' as const
export const PERSONAL_AUTO_OUTBOUND_SOURCE = 'personal_auto_outbound' as const

export type AutoOutboundIncomingFields = {
  source?: string | null
  task_id?: number | null
  record_id?: number | null
}

type RestoredAutoOutboundContext = {
  source?: string
  task_id?: number
  record_id?: number
}

export type AutoOutboundBusinessTab = 'auto_outbound' | 'personal_auto_outbound'

type AutoOutboundHistoryRecord = AutoOutboundIncomingFields & {
  call_id: string
  call_source: string
  direction: 'inbound' | 'outbound'
  customer_number?: string | null
  service_number?: string | null
  started_at?: string | null
}

/** Normalize auto-outbound context supplied by socket/status responses. */
export function restoredAutoOutboundContext(
  fields: AutoOutboundIncomingFields | null | undefined,
): RestoredAutoOutboundContext {
  const taskId = Number(fields?.task_id)
  const recordId = Number(fields?.record_id)
  return {
    source: fields?.source ?? undefined,
    task_id: Number.isFinite(taskId) && taskId > 0 ? taskId : undefined,
    record_id: Number.isFinite(recordId) && recordId > 0 ? recordId : undefined,
  }
}

/** Build the existing business-panel context from a server-enriched history row. */
export function autoOutboundIncomingForCallRecord(
  record: AutoOutboundHistoryRecord | null | undefined,
): IncomingCall | null {
  if (!record || record.call_source !== AUTO_OUTBOUND_SOURCE) return null
  const context = restoredAutoOutboundContext(record)
  if (!shouldShowAutoOutboundBusinessTab(context)) return null
  const parsedStart = Date.parse(record.started_at || '')
  return {
    offer_id: '',
    call_id: record.call_id,
    from: record.service_number || '',
    to: record.customer_number || '',
    queue_id: null,
    startedAt: Number.isFinite(parsedStart) ? parsedStart : 0,
    direction: record.direction,
    ...context,
  }
}

/** True when the incoming offer was tagged by an auto-outbound assign. */
export function isAutoOutboundIncoming(
  incoming: AutoOutboundIncomingFields | null | undefined,
): boolean {
  return incoming?.source === AUTO_OUTBOUND_SOURCE || incoming?.source === PERSONAL_AUTO_OUTBOUND_SOURCE
}

export function isPersonalAutoOutboundIncoming(
  incoming: AutoOutboundIncomingFields | null | undefined,
): boolean {
  return incoming?.source === PERSONAL_AUTO_OUTBOUND_SOURCE
}

/**
 * Web phone + auto-outbound → system auto-accepts (no manual answer UI).
 * SIP desk phones keep the existing handset-ring UX.
 */
export function shouldAutoAcceptAutoOutbound(opts: {
  source?: string | null
  deviceType?: string | null
  /** When true, skip (page restore / already answered). */
  restore?: boolean
  alreadyAnswered?: boolean
}): boolean {
  if (opts.source !== AUTO_OUTBOUND_SOURCE && opts.source !== PERSONAL_AUTO_OUTBOUND_SOURCE) return false
  if (opts.restore || opts.alreadyAnswered) return false
  if (opts.deviceType === 'sip_phone') return false
  return true
}

/** Right-panel "外呼任务业务记录" tab is only for auto-outbound offers. */
export function shouldShowAutoOutboundBusinessTab(
  incoming: AutoOutboundIncomingFields | null | undefined,
): boolean {
  if (incoming?.source !== AUTO_OUTBOUND_SOURCE) return false
  const taskId = Number(incoming?.task_id)
  return Number.isFinite(taskId) && taskId > 0
}

/** Resolve the business-record tab available for this auto-outbound offer. */
export function autoOutboundBusinessTabForIncoming(
  incoming: AutoOutboundIncomingFields | null | undefined,
): AutoOutboundBusinessTab | null {
  if (shouldShowAutoOutboundBusinessTab(incoming)) return 'auto_outbound'
  if (incoming?.source !== PERSONAL_AUTO_OUTBOUND_SOURCE) return null
  const recordId = Number(incoming.record_id)
  return Number.isFinite(recordId) && recordId > 0 ? 'personal_auto_outbound' : null
}

export function autoOutboundTaskId(
  incoming: AutoOutboundIncomingFields | null | undefined,
): number | null {
  const taskId = Number(incoming?.task_id)
  return Number.isFinite(taskId) && taskId > 0 ? taskId : null
}

/**
 * Resolve the auto-outbound call-record id for wrap-up.
 *
 * Priority:
 * 1. Push payload `record_id` (when backend includes it)
 * 2. Match listed auto-outbound records by `call_record_id` (CDR id)
 * 3. Fallback: most recent agent-reception record for the same phone that has
 *    no completed wrap-up yet
 */
export function resolveAutoOutboundRecordId(opts: {
  pushRecordId?: number | null
  callRecordId?: number | null
  phoneNumber?: string | null
  records?: Array<{
    id: number
    call_record_id?: number | null
    phone_number?: string | null
    reception_type?: string | null
    reception_result?: unknown
  }>
}): number | null {
  const fromPush = Number(opts.pushRecordId)
  if (Number.isFinite(fromPush) && fromPush > 0) return fromPush

  const items = opts.records ?? []
  const cdrId = Number(opts.callRecordId)
  if (Number.isFinite(cdrId) && cdrId > 0) {
    const byCdr = items.find((r) => Number(r.call_record_id) === cdrId)
    if (byCdr) return byCdr.id
  }

  const phone = (opts.phoneNumber || '').trim()
  if (!phone) return null
  const candidates = items.filter(
    (r) =>
      (r.phone_number || '').trim() === phone &&
      (r.reception_type === 'agent' || r.reception_type == null) &&
      !hasCompletedWrapup(r.reception_result),
  )
  if (candidates.length === 0) return null
  return candidates[0]!.id
}

function hasCompletedWrapup(receptionResult: unknown): boolean {
  if (!receptionResult || typeof receptionResult !== 'object') return false
  const result = receptionResult as { auto_submitted?: unknown; submitted_by?: unknown }
  if (result.auto_submitted === true) return true
  if (result.submitted_by != null) return true
  return false
}

/** Call-type label: auto outbound vs ordinary inbound/outbound. */
export function callTypeLabel(opts: {
  isAutoOutbound: boolean
  direction?: 'inbound' | 'outbound' | null
  locale: Locale
}): string {
  if (opts.isAutoOutbound) {
    return t('ws.autoOutbound.agent.callType', opts.locale)
  }
  if (opts.direction === 'outbound') {
    return t('ws.call.directionOutbound', opts.locale)
  }
  return t('ws.call.directionInbound', opts.locale)
}
