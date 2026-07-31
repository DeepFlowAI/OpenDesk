import { describe, expect, it } from 'vitest'

import {
  callRecordAnsweredByAgent,
  callRecordBelongsToAgent,
} from '@/lib/call-record-ownership'
import {
  callSessionReducer,
  initialCallSession,
  type CallSessionState,
  type IncomingCall,
} from '@/lib/call-session-reducer'

function incoming(partial: Partial<IncomingCall> = {}): IncomingCall {
  return {
    offer_id: 'o1',
    call_id: 'c1',
    from: '100',
    to: '200',
    queue_id: null,
    startedAt: 1000,
    ...partial,
  }
}

describe('callRecordBelongsToAgent', () => {
  it('true when CDR agent_id matches the current employee', () => {
    expect(callRecordBelongsToAgent({ agent_id: 7 }, 7)).toBe(true)
  })

  it('false when CDR belongs to another agent', () => {
    expect(callRecordBelongsToAgent({ agent_id: 1 }, 7)).toBe(false)
  })

  it('false when CDR agent_id is null', () => {
    expect(callRecordBelongsToAgent({ agent_id: null }, 7)).toBe(false)
  })

  it('false when employee id is unknown', () => {
    expect(callRecordBelongsToAgent({ agent_id: 7 }, null)).toBe(false)
    expect(callRecordBelongsToAgent({ agent_id: 7 }, undefined)).toBe(false)
  })
})

describe('callRecordAnsweredByAgent', () => {
  const answered = {
    agent_id: 1,
    answered_at: '2026-01-01T00:00:00Z',
    state: 'in_progress',
  }

  it('true for own answered CDR (SIP handset path)', () => {
    expect(callRecordAnsweredByAgent(answered, 1)).toBe(true)
    expect(
      callRecordAnsweredByAgent(
        { agent_id: 1, answered_at: null, state: 'in_progress' },
        1,
      ),
    ).toBe(true)
  })

  it('false for another agent\'s answered CDR', () => {
    expect(callRecordAnsweredByAgent(answered, 7)).toBe(false)
  })

  it('false when own CDR is not answered', () => {
    expect(
      callRecordAnsweredByAgent(
        { agent_id: 7, answered_at: null, state: 'ringing' },
        7,
      ),
    ).toBe(false)
  })
})

describe('queue transfer / SIP answered inference via SOCKET_INCOMING', () => {
  it('other agent\'s answered CDR must stay incoming (queue blind transfer)', () => {
    const otherAgentsCdr = {
      agent_id: 1,
      answered_at: '2026-01-01T00:00:00Z',
      state: 'in_progress',
    }
    const myEmployeeId = 7
    const alreadyAnswered = callRecordAnsweredByAgent(otherAgentsCdr, myEmployeeId)
    expect(alreadyAnswered).toBe(false)

    const idle: CallSessionState = { ...initialCallSession, phase: 'idle', epoch: 1 }
    const next = callSessionReducer(idle, {
      type: 'SOCKET_INCOMING',
      incoming: incoming(),
      alreadyAnswered,
      callStart: 1000,
    })
    expect(next.phase).toBe('incoming')
  })

  it('restore: true still enters on_call', () => {
    const idle: CallSessionState = { ...initialCallSession, phase: 'idle', epoch: 1 }
    const next = callSessionReducer(idle, {
      type: 'SOCKET_INCOMING',
      incoming: incoming(),
      restore: true,
      alreadyAnswered: false,
      callStart: 1000,
    })
    expect(next.phase).toBe('on_call')
  })

  it('own answered CDR upgrades incoming → on_call (SIP handset)', () => {
    const myCdr = {
      agent_id: 7,
      answered_at: '2026-01-01T00:00:00Z',
      state: 'in_progress',
    }
    const alreadyAnswered = callRecordAnsweredByAgent(myCdr, 7)
    expect(alreadyAnswered).toBe(true)

    const ringing: CallSessionState = {
      ...initialCallSession,
      phase: 'incoming',
      incoming: incoming(),
      callStart: 5000,
      epoch: 1,
    }
    // SOCKET_INCOMING with alreadyAnswered (page refresh while Redis still ringing)
    const fromSocket = callSessionReducer(
      { ...initialCallSession, phase: 'idle', epoch: 1 },
      {
        type: 'SOCKET_INCOMING',
        incoming: incoming(),
        alreadyAnswered,
        callStart: 4000,
      },
    )
    expect(fromSocket.phase).toBe('on_call')

    // CDR_ANSWERED effect only fires when callRecordAnsweredByAgent is true
    const fromCdr = callSessionReducer(ringing, {
      type: 'CDR_ANSWERED',
      callStart: 4000,
    })
    expect(fromCdr.phase).toBe('on_call')
    expect(fromCdr.callStart).toBe(4000)
  })
})
