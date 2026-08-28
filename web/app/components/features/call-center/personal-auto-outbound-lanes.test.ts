import { describe, expect, it } from 'vitest'

import type { PersonalAutoOutboundCall } from '@/models/personal-auto-outbound'

import {
  assignActiveCallsToSlots,
  buildLaneSlots,
  endedCallCount,
  maskPhone,
  nextClearingSlots,
  resolveRunningBadge,
} from './personal-auto-outbound-lanes'

function call(partial: Partial<PersonalAutoOutboundCall> & Pick<PersonalAutoOutboundCall, 'id' | 'stage'>): PersonalAutoOutboundCall {
  return {
    target_id: partial.id,
    call_record_id: null,
    phone_number: '13800138000',
    prescreen_result: null,
    intent_key: null,
    similarity: null,
    degraded_reason: null,
    assigned_agent_id: null,
    assignment_type: null,
    hangup_reason: null,
    started_at: '2026-08-18T04:00:00.000Z',
    answered_at: null,
    ended_at: null,
    ...partial,
  }
}

describe('assignActiveCallsToSlots', () => {
  it('fills empty slots from the top and keeps a stable mapping', () => {
    const first = assignActiveCallsToSlots({}, [11, 12], 4)
    expect(first).toEqual({ 1: 11, 2: 12 })
    expect(assignActiveCallsToSlots(first, [11, 12, 13], 4)).toEqual({ 1: 11, 2: 12, 3: 13 })
  })

  it('reuses a freed slot for the next call', () => {
    const previous = { 1: 11, 2: 12, 3: 13 }
    expect(assignActiveCallsToSlots(previous, [12, 13, 14], 4)).toEqual({ 1: 14, 2: 12, 3: 13 })
  })

  it('does not evict an occupied row when effective concurrency shrinks', () => {
    expect(assignActiveCallsToSlots({ 1: 11, 2: 12, 3: 13, 4: 14 }, [11, 12, 13, 14], 2)).toEqual({
      1: 11,
      2: 12,
      3: 13,
      4: 14,
    })
  })
})

describe('nextClearingSlots and buildLaneSlots', () => {
  it('keeps an ended call in the same slot while it is clearing', () => {
    const callsById = new Map([
      [11, call({ id: 11, stage: 'filtered', prescreen_result: 'explicit_rejection', ended_at: '2026-08-18T04:00:20.000Z' })],
      [12, call({ id: 12, stage: 'ringing' })],
    ])
    const previousAssignment = { 1: 11, 2: 12 }
    const nextAssignment = assignActiveCallsToSlots(previousAssignment, [12], 4)
    const clearing = nextClearingSlots({
      previousAssignment,
      nextAssignment,
      previousClearing: {},
      callsById,
      now: 1_000,
    })
    expect(clearing[1]?.result).toBe('explicit_rejection')
    const lanes = buildLaneSlots({
      slotCount: 4,
      assignment: nextAssignment,
      clearing,
      callsById,
      now: 1_000,
    })
    expect(lanes).toHaveLength(4)
    expect(lanes[0]).toMatchObject({ slot: 1, stage: 'clearing', result: 'explicit_rejection' })
    expect(lanes[1]).toMatchObject({ slot: 2, stage: 'ringing' })
    expect(lanes[2]?.stage).toBe('empty')
  })
})

describe('resolveRunningBadge', () => {
  const session = { status: 'running', pause_reason: null, effective_concurrency: 4 }

  it('uses replenish copy while ringing', () => {
    expect(resolveRunningBadge({ session, ringingCurrent: 3, screeningCurrent: 0, onHumanCall: false })).toEqual({
      key: 'personalAuto.status.runningReplenish',
      tone: 'info',
      params: { ringingCount: 3, effectiveConcurrency: 4 },
    })
  })

  it('uses screening and on-call copy', () => {
    expect(resolveRunningBadge({ session, ringingCurrent: 2, screeningCurrent: 1, onHumanCall: false }).key).toBe(
      'personalAuto.status.runningScreening',
    )
    expect(resolveRunningBadge({ session, ringingCurrent: 0, screeningCurrent: 0, onHumanCall: true }).key).toBe(
      'personalAuto.status.runningOnCall',
    )
  })
})

describe('helpers', () => {
  it('masks phone numbers and counts ended calls', () => {
    expect(maskPhone('13800138000')).toBe('138****8000')
    expect(endedCallCount([call({ id: 1, stage: 'ended', ended_at: '2026-08-18T04:00:20.000Z' }), call({ id: 2, stage: 'ringing' })])).toBe(1)
  })
})
