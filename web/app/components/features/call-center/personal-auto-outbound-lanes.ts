import type { PersonalAutoOutboundCall, PersonalAutoOutboundSession } from '@/models/personal-auto-outbound'

export type LaneStage = 'empty' | 'dialing' | 'ringing' | 'screening' | 'clearing'

export type LaneSlot = {
  slot: number
  callId?: number
  stage: LaneStage
  customer?: string
  phone?: string
  elapsed?: string
  progress?: number
  result?: string
}

export type LaneAssignment = Record<number, number>

export type ClearingSlot = {
  callId: number
  result: string
  until: number
}

export const LANE_CLEARING_MS = 600

const ACTIVE_STAGES = new Set(['dialing', 'ringing', 'screening'])
const CLEARING_STAGES = new Set(['filtered', 'not_connected', 'cancelled', 'ended', 'no_agent'])

export function maskPhone(phone: string) {
  if (phone.length <= 7) return phone
  return `${phone.slice(0, 3)}${'*'.repeat(phone.length - 7)}${phone.slice(-4)}`
}

export function formatElapsed(startedAt: string, nowMs: number) {
  const elapsed = Math.max(0, Math.floor((nowMs - Date.parse(startedAt)) / 1000))
  const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const seconds = String(elapsed % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

export function laneProgress(startedAt: string, nowMs: number) {
  const elapsed = Math.max(0, nowMs - Date.parse(startedAt))
  return Math.min(100, Math.round((elapsed / 25000) * 100))
}

export function isLaneActiveCall(call: PersonalAutoOutboundCall) {
  return ACTIVE_STAGES.has(call.stage)
}

export function isLaneClearingCall(call: PersonalAutoOutboundCall) {
  return call.ended_at != null || CLEARING_STAGES.has(call.stage)
}

export function displaySlotCount(assignment: LaneAssignment, configuredSlots: number) {
  const occupiedMax = Object.keys(assignment).reduce((max, key) => Math.max(max, Number(key)), 0)
  return Math.max(configuredSlots, occupiedMax, 1)
}

export function assignActiveCallsToSlots(
  previous: LaneAssignment,
  activeCallIds: number[],
  slotCount: number,
): LaneAssignment {
  const next: LaneAssignment = {}
  const used = new Set<number>()
  const previousEntries = Object.entries(previous)
    .map(([slot, callId]) => [Number(slot), callId] as const)
    .sort((a, b) => a[0] - b[0])

  for (const [slot, callId] of previousEntries) {
    if (activeCallIds.includes(callId) && !used.has(callId)) {
      next[slot] = callId
      used.add(callId)
    }
  }

  const emptySlots: number[] = []
  const occupiedMax = Object.keys(next).reduce((max, key) => Math.max(max, Number(key)), 0)
  const span = Math.max(slotCount, occupiedMax)
  for (let slot = 1; slot <= span; slot += 1) {
    if (next[slot] == null) emptySlots.push(slot)
  }

  let extraSlot = Math.max(slotCount, occupiedMax)
  for (const callId of activeCallIds) {
    if (used.has(callId)) continue
    const existing = emptySlots.shift()
    if (existing != null) {
      next[existing] = callId
    } else {
      extraSlot += 1
      next[extraSlot] = callId
    }
    used.add(callId)
  }

  return next
}

export function nextClearingSlots(input: {
  previousAssignment: LaneAssignment
  nextAssignment: LaneAssignment
  previousClearing: Record<number, ClearingSlot>
  callsById: Map<number, PersonalAutoOutboundCall>
  now: number
}): Record<number, ClearingSlot> {
  const next: Record<number, ClearingSlot> = {}
  for (const [slotStr, item] of Object.entries(input.previousClearing)) {
    const slot = Number(slotStr)
    if (item.until > input.now && input.nextAssignment[slot] == null) next[slot] = item
  }
  for (const [slotStr, callId] of Object.entries(input.previousAssignment)) {
    const slot = Number(slotStr)
    if (input.nextAssignment[slot] != null) continue
    if (next[slot] != null) continue
    const call = input.callsById.get(callId)
    if (!call || !isLaneClearingCall(call)) continue
    next[slot] = {
      callId,
      result: call.prescreen_result || call.hangup_reason || call.stage,
      until: input.now + LANE_CLEARING_MS,
    }
  }
  return next
}

export function buildLaneSlots(input: {
  slotCount: number
  assignment: LaneAssignment
  clearing: Record<number, ClearingSlot>
  callsById: Map<number, PersonalAutoOutboundCall>
  now: number
}): LaneSlot[] {
  const count = displaySlotCount(input.assignment, input.slotCount)
  const lanes: LaneSlot[] = []
  for (let slot = 1; slot <= count; slot += 1) {
    const callId = input.assignment[slot]
    const call = callId != null ? input.callsById.get(callId) : undefined
    if (call && isLaneActiveCall(call)) {
      const stage = call.stage === 'screening' ? 'screening' : call.stage === 'dialing' ? 'dialing' : 'ringing'
      const clockStart = stage === 'screening' && call.answered_at ? call.answered_at : call.started_at
      lanes.push({
        slot,
        callId: call.id,
        stage,
        customer: call.target_name || maskPhone(call.phone_number),
        phone: maskPhone(call.phone_number),
        elapsed: formatElapsed(clockStart, input.now),
        progress: laneProgress(call.started_at, input.now),
      })
      continue
    }
    const clearing = input.clearing[slot]
    const clearingCall = clearing ? input.callsById.get(clearing.callId) : undefined
    if (clearing && clearing.until > input.now) {
      lanes.push({
        slot,
        callId: clearing.callId,
        stage: 'clearing',
        customer: clearingCall?.target_name || (clearingCall ? maskPhone(clearingCall.phone_number) : undefined),
        phone: clearingCall ? maskPhone(clearingCall.phone_number) : undefined,
        result: clearing.result,
      })
      continue
    }
    lanes.push({ slot, stage: 'empty' })
  }
  return lanes
}

export function resolveRunningBadge(input: {
  session: Pick<PersonalAutoOutboundSession, 'status' | 'pause_reason' | 'effective_concurrency'>
  ringingCurrent: number
  screeningCurrent: number
  onHumanCall: boolean
}): { key: string; tone: 'muted' | 'info' | 'warning' | 'success'; params?: Record<string, number> } {
  if (input.session.status === 'paused') return { key: 'personalAuto.status.paused', tone: 'muted' }
  if (input.session.status === 'auto_paused') return { key: 'personalAuto.status.auto_paused', tone: 'warning' }
  if (input.session.status === 'stopping') return { key: 'personalAuto.status.stopping', tone: 'muted' }
  if (input.onHumanCall) return { key: 'personalAuto.status.runningOnCall', tone: 'success' }
  if (input.screeningCurrent > 0) return { key: 'personalAuto.status.runningScreening', tone: 'warning' }
  return {
    key: 'personalAuto.status.runningReplenish',
    tone: 'info',
    params: {
      ringingCount: input.ringingCurrent,
      effectiveConcurrency: input.session.effective_concurrency,
    },
  }
}

export function endedCallCount(calls: PersonalAutoOutboundCall[]) {
  return calls.filter((call) => call.ended_at != null).length
}
