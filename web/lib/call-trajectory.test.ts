import { describe, expect, it } from 'vitest'

import {
  formatTrajectoryDuration,
  isBusinessTrajectoryEvent,
  trajectoryEventDescription,
  trajectoryEventLabel,
  trajectoryOperationStepDescription,
  trajectoryOperationStepLabel,
  trajectoryOperationTitle,
  trajectoryParticipantNames,
  trajectoryResultLabel,
} from './call-trajectory'
import type { CallTrajectoryEvent } from '@/models/call-center'

const baseEvent: CallTrajectoryEvent = {
  id: 1,
  event_id: 'evt-1',
  tenant_id: 1,
  call_record_id: 2,
  root_call_id: 'call-root',
  event_type: 'transfer_started',
  event_category: 'transfer',
  schema_version: 1,
  occurred_at: '2026-08-09T01:00:00.000Z',
  sequence_no: 1,
  operation_id: 'transfer-1',
  call_leg_id: 'leg-123456789',
  parent_leg_id: null,
  participant_role: null,
  actor_type: 'agent',
  actor_id: '42',
  actor_name_snapshot: 'Alice',
  target_type: 'employee',
  target_id: '99',
  target_name_snapshot: 'Bob',
  queue_type: null,
  queue_id: null,
  queue_name_snapshot: null,
  result: 'succeeded',
  reason_code: null,
  reason_detail: null,
  duration_ms: 12_640,
  source: 'opendesk',
  source_event_id: null,
  trace_id: null,
  is_synthetic: false,
  details: {},
  created_at: '2026-08-09T01:00:00.000Z',
}

describe('call trajectory formatting', () => {
  it('keeps business events and filters technical-only events', () => {
    expect(isBusinessTrajectoryEvent(baseEvent)).toBe(true)
    expect(isBusinessTrajectoryEvent({ ...baseEvent, event_type: 'media_disconnected' })).toBe(false)
  })

  it('localizes known event labels with a readable fallback', () => {
    expect(trajectoryEventLabel('transfer_started', true)).toBe('发起转接')
    expect(trajectoryEventLabel('transfer_started', false)).toBe('Transfer started')
    expect(trajectoryEventLabel('custom_event', false)).toBe('custom event')
  })

  it('formats duration', () => {
    expect(formatTrajectoryDuration(12_640)).toBe('12.6 s')
    expect(formatTrajectoryDuration(2_400, true)).toBe('2.4 秒')
    expect(formatTrajectoryDuration(90_000)).toBe('1:30')
  })

  it('builds a concise localized event description', () => {
    expect(trajectoryEventDescription(baseEvent, true, false)).toBe('Alice → Bob')
    expect(trajectoryEventDescription(baseEvent, false, false)).toBe('Alice → Bob')
  })

  it('only includes the event source in technical descriptions', () => {
    expect(trajectoryEventDescription(baseEvent, true, false)).not.toContain('来源 opendesk')
    expect(trajectoryEventDescription(baseEvent, true, true)).toContain('来源 opendesk')
  })

  it('shows the serving agent once for business reception events', () => {
    const receptionEvent = {
      ...baseEvent,
      event_type: 'reception_started',
      target_id: baseEvent.actor_id,
      target_name_snapshot: baseEvent.actor_name_snapshot,
    }

    expect(trajectoryEventDescription(receptionEvent, true, false)).toBe('客服 Alice')
    expect(trajectoryEventDescription(receptionEvent, true, true)).toContain('发起方 Alice · 目标 Alice')
  })

  it('uses names from other snapshots instead of showing employee ids', () => {
    const offerStarted = {
      ...baseEvent,
      event_type: 'agent_offer_started',
      actor_id: null,
      actor_name_snapshot: null,
      target_id: '99',
      target_name_snapshot: null,
    }
    const names = trajectoryParticipantNames([baseEvent])

    expect(trajectoryEventDescription(offerStarted, true, false, names)).toBe('客服 Bob')
    expect(trajectoryEventDescription(offerStarted, true, true, names)).toContain('目标 99')
    expect(trajectoryOperationTitle([offerStarted], true, names)).toBe('呼叫客服 Bob')
  })

  it('localizes operation status and step semantics', () => {
    const names = trajectoryParticipantNames([baseEvent])
    expect(trajectoryResultLabel('succeeded', true)).toBe('成功')
    expect(trajectoryOperationStepLabel('transfer_completed', true)).toBe('转接完成')
    expect(trajectoryOperationStepDescription(baseEvent, true, names)).toBe('Alice → Bob')
    expect(trajectoryOperationTitle([baseEvent], true, names)).toBe('Alice 转接给 Bob')
  })
})
