import { describe, expect, it } from 'vitest'

import {
  callRecordAnsweredByAgent,
  callRecordBelongsToAgent,
  callRecordCustomerConnected,
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
  it('true when the last serving agent matches the current employee', () => {
    expect(callRecordBelongsToAgent({ last_serving_agent_id: 7 }, 7)).toBe(true)
  })

  it('false when CDR belongs to another agent', () => {
    expect(callRecordBelongsToAgent({ last_serving_agent_id: 1 }, 7)).toBe(false)
  })

  it('false when the last serving agent is null', () => {
    expect(callRecordBelongsToAgent({ last_serving_agent_id: null }, 7)).toBe(false)
  })

  it('false when employee id is unknown', () => {
    expect(callRecordBelongsToAgent({ last_serving_agent_id: 7 }, null)).toBe(false)
    expect(callRecordBelongsToAgent({ last_serving_agent_id: 7 }, undefined)).toBe(false)
  })
})

describe('callRecordAnsweredByAgent', () => {
  const answered = {
    last_serving_agent_id: 1,
    first_agent_connected_at: '2026-01-01T00:00:00Z',
    lifecycle_status: 'active',
  }

  it('true for own answered CDR (SIP handset path)', () => {
    expect(callRecordAnsweredByAgent(answered, 1)).toBe(true)
    expect(
      callRecordAnsweredByAgent(
        { last_serving_agent_id: 1, first_agent_connected_at: null, lifecycle_status: 'active' },
        1,
      ),
    ).toBe(false)
  })

  it('false for another agent\'s answered CDR', () => {
    expect(callRecordAnsweredByAgent(answered, 7)).toBe(false)
  })

  it('false when own CDR is not answered', () => {
    expect(
      callRecordAnsweredByAgent(
        { last_serving_agent_id: 7, first_agent_connected_at: null, lifecycle_status: 'active' },
        7,
      ),
    ).toBe(false)
  })
})

describe('callRecordCustomerConnected', () => {
  it('false while the outbound call is still dialing (started_at only)', () => {
    // A fresh outbound CDR always has started_at — that is the dial time,
    // not answer evidence, and must not upgrade 外呼中 → 通话中.
    expect(
      callRecordCustomerConnected({
        customer_connected_at: null,
      }),
    ).toBe(false)
    expect(callRecordCustomerConnected(null)).toBe(false)
    expect(callRecordCustomerConnected(undefined)).toBe(false)
  })

  it('true once the customer connected', () => {
    expect(
      callRecordCustomerConnected({
        customer_connected_at: '2026-01-01T00:00:05Z',
      }),
    ).toBe(true)
  })

  it('gates the outbound_ringing → on_call upgrade end to end', () => {
    const dialing: CallSessionState = {
      ...initialCallSession,
      phase: 'outbound_ringing',
      incoming: incoming({ direction: 'outbound' }),
      callStart: 5000,
      epoch: 1,
    }
    // Dial-time CDR: the effect returns early, no CDR_ANSWERED is dispatched,
    // so the phase must remain outbound_ringing.
    expect(
      callRecordCustomerConnected({ customer_connected_at: null }),
    ).toBe(false)
    expect(dialing.phase).toBe('outbound_ringing')

    // Customer answered: the reducer upgrade itself is valid evidence-driven.
    const answered = callSessionReducer(dialing, {
      type: 'CDR_ANSWERED',
      callStart: 4000,
    })
    expect(answered.phase).toBe('on_call')
  })
})

describe('queue transfer / SIP answered inference via SOCKET_INCOMING', () => {
  it('other agent\'s answered CDR must stay incoming (queue blind transfer)', () => {
    const otherAgentsCdr = {
      last_serving_agent_id: 1,
      first_agent_connected_at: '2026-01-01T00:00:00Z',
      lifecycle_status: 'active',
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
      last_serving_agent_id: 7,
      first_agent_connected_at: '2026-01-01T00:00:00Z',
      lifecycle_status: 'active',
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
