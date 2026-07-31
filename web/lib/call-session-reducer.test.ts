import { describe, expect, it } from 'vitest'

import {
  callSessionReducer,
  canPollHydrate,
  hangupMatches,
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

describe('callSessionReducer', () => {
  it('poll hydrate only works from idle', () => {
    const idle = callSessionReducer(initialCallSession, { type: 'MIC_READY' })
    expect(idle.phase).toBe('idle')

    const hydrated = callSessionReducer(idle, {
      type: 'POLL_HYDRATE',
      phase: 'on_call',
      incoming: incoming(),
      callStart: 2000,
    })
    expect(hydrated.phase).toBe('on_call')
    expect(hydrated.incoming?.call_id).toBe('c1')

    // Lagging poll must NOT clear / override live UI.
    const blocked = callSessionReducer(hydrated, {
      type: 'POLL_HYDRATE',
      phase: 'incoming',
      incoming: incoming({ call_id: 'ghost' }),
      callStart: 3000,
    })
    expect(blocked.phase).toBe('on_call')
    expect(blocked.incoming?.call_id).toBe('c1')
    expect(canPollHydrate(hydrated.phase)).toBe(false)
  })

  it('socket incoming restore stays on_call (no flash to ringing)', () => {
    const onCall: CallSessionState = {
      ...initialCallSession,
      phase: 'on_call',
      incoming: incoming(),
      callStart: 1000,
      epoch: 1,
    }
    const next = callSessionReducer(onCall, {
      type: 'SOCKET_INCOMING',
      incoming: incoming({ offer_id: 'o2' }),
      restore: true,
      callStart: 1000,
    })
    expect(next.phase).toBe('on_call')
  })

  it('hangup while ringing returns idle; while on_call goes wrap_up', () => {
    const ringing = callSessionReducer(
      { ...initialCallSession, phase: 'idle', epoch: 1 },
      {
        type: 'SOCKET_INCOMING',
        incoming: incoming(),
      },
    )
    expect(ringing.phase).toBe('incoming')

    const afterRingHangup = callSessionReducer(ringing, {
      type: 'SOCKET_HANGUP',
      callId: 'c1',
      matches: true,
    })
    expect(afterRingHangup.phase).toBe('idle')
    expect(afterRingHangup.incoming).toBeNull()

    const talking = callSessionReducer(ringing, { type: 'SOCKET_ANSWERED' })
    const afterTalkHangup = callSessionReducer(talking, {
      type: 'SOCKET_HANGUP',
      callId: 'c1',
      matches: true,
    })
    expect(afterTalkHangup.phase).toBe('wrap_up')
  })

  it('unmatched hangup is ignored', () => {
    const onCall: CallSessionState = {
      ...initialCallSession,
      phase: 'on_call',
      incoming: incoming(),
      callStart: 1,
      epoch: 2,
    }
    const next = callSessionReducer(onCall, {
      type: 'SOCKET_HANGUP',
      callId: 'other',
      matches: false,
    })
    expect(next.phase).toBe('on_call')
    expect(next.epoch).toBe(2)
  })

  it('cdr answered upgrades incoming → on_call', () => {
    const ringing: CallSessionState = {
      ...initialCallSession,
      phase: 'incoming',
      incoming: incoming(),
      callStart: 5000,
      epoch: 1,
    }
    const next = callSessionReducer(ringing, {
      type: 'CDR_ANSWERED',
      callStart: 4000,
    })
    expect(next.phase).toBe('on_call')
    expect(next.callStart).toBe(4000)
  })
})

describe('hangupMatches', () => {
  it('matches business call, media leg, or source call', () => {
    expect(
      hangupMatches({
        hangupCallId: 'biz',
        businessCallId: 'biz',
      }),
    ).toBe(true)
    expect(
      hangupMatches({
        hangupCallId: 'leg',
        activeLegId: 'leg',
      }),
    ).toBe(true)
    expect(
      hangupMatches({
        hangupCallId: 'src',
        sourceCallId: 'src',
      }),
    ).toBe(true)
    expect(
      hangupMatches({
        hangupCallId: 'x',
        businessCallId: 'y',
      }),
    ).toBe(false)
    expect(hangupMatches({ hangupCallId: '' })).toBe(false)
  })
})
