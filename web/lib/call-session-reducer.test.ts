import { describe, expect, it } from 'vitest'

import {
  callSessionReducer,
  canPollHydrate,
  hangupMatches,
  initialCallSession,
  retainConnectedCallScreenPop,
  shouldHydrateMediaReconnect,
  shouldLeaveOnCallFromPoll,
  shouldLeaveOutboundRingingFromPoll,
  shouldPollHydrateOnCall,
  shouldUpgradeOutboundRingingFromPoll,
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
  it('leaves outbound ringing only when a later poll proves the call was released', () => {
    const base = {
      phase: 'outbound_ringing' as const,
      ringingCallId: 'out-1',
      callStart: 2000,
    }
    expect(
      shouldLeaveOutboundRingingFromPoll({
        ...base,
        currentCallId: 'out-1',
        resourceState: 'ringing',
        resourceUpdatedAtMs: 2500,
      }),
    ).toBe(false)
    expect(
      shouldLeaveOutboundRingingFromPoll({
        ...base,
        currentCallId: null,
        resourceState: 'idle',
        resourceUpdatedAtMs: 1500,
      }),
    ).toBe(false)
    expect(
      shouldLeaveOutboundRingingFromPoll({
        ...base,
        currentCallId: null,
        resourceState: 'idle',
        resourceUpdatedAtMs: 2600,
      }),
    ).toBe(true)
  })

  it('upgrades outbound ringing when a later poll shows this call in_call', () => {
    expect(
      shouldUpgradeOutboundRingingFromPoll({
        phase: 'outbound_ringing',
        ringingCallId: 'sip-1',
        currentCallId: 'sip-1',
        resourceState: 'in_call',
      }),
    ).toBe(true)
    expect(
      shouldUpgradeOutboundRingingFromPoll({
        phase: 'outbound_ringing',
        ringingCallId: 'webrtc-1',
        sourceCallId: 'sip-1',
        currentCallId: 'sip-1',
        resourceState: 'in_call',
      }),
    ).toBe(true)
    expect(
      shouldUpgradeOutboundRingingFromPoll({
        phase: 'outbound_ringing',
        ringingCallId: 'sip-1',
        currentCallId: 'sip-1',
        resourceState: 'ringing',
      }),
    ).toBe(false)
    expect(
      shouldUpgradeOutboundRingingFromPoll({
        phase: 'on_call',
        ringingCallId: 'sip-1',
        currentCallId: 'sip-1',
        resourceState: 'in_call',
      }),
    ).toBe(false)
  })

  it('leaves on_call only when a fresh poll shows the resource freed', () => {
    expect(
      shouldLeaveOnCallFromPoll({
        phase: 'on_call',
        callStart: 1_000,
        resourceState: 'idle',
        resourceUpdatedAtMs: 2_000,
      }),
    ).toBe(true)
    expect(
      shouldLeaveOnCallFromPoll({
        phase: 'on_call',
        callStart: 1_000,
        resourceState: 'after_call_work',
        resourceUpdatedAtMs: 2_000,
      }),
    ).toBe(true)
    // Live call: still in_call, or re-keyed by a consult / media reconnect.
    expect(
      shouldLeaveOnCallFromPoll({
        phase: 'on_call',
        callStart: 1_000,
        resourceState: 'in_call',
        resourceUpdatedAtMs: 2_000,
      }),
    ).toBe(false)
    // Snapshot predates this call — must not end a call it never saw.
    expect(
      shouldLeaveOnCallFromPoll({
        phase: 'on_call',
        callStart: 5_000,
        resourceState: 'idle',
        resourceUpdatedAtMs: 2_000,
      }),
    ).toBe(false)
    expect(
      shouldLeaveOnCallFromPoll({
        phase: 'on_call',
        callStart: 1_000,
        resourceState: 'idle',
        resourceUpdatedAtMs: null,
      }),
    ).toBe(false)
    expect(
      shouldLeaveOnCallFromPoll({
        phase: 'outbound_ringing',
        callStart: 1_000,
        resourceState: 'idle',
        resourceUpdatedAtMs: 2_000,
      }),
    ).toBe(false)
  })

  it('does not treat visible busy outbound ringing as answered', () => {
    expect(shouldPollHydrateOnCall('ringing', false)).toBe(false)
    expect(shouldPollHydrateOnCall('reserved', false)).toBe(false)
    expect(shouldPollHydrateOnCall('in_call', false)).toBe(true)
    expect(shouldPollHydrateOnCall('ringing', true)).toBe(true)
  })

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
    expect(afterTalkHangup.lastEndedCallIds).toContain('c1')
  })

  it('does not revive the ended call after wrap-up via poll or socket restore', () => {
    const onCall: CallSessionState = {
      ...initialCallSession,
      phase: 'on_call',
      incoming: incoming({ call_id: 'sip-1', source_call_id: undefined }),
      callStart: 1000,
      epoch: 2,
    }
    const wrapUp = callSessionReducer(onCall, {
      type: 'SOCKET_HANGUP',
      callId: 'sip-1',
      matches: true,
    })
    const idle = callSessionReducer(wrapUp, { type: 'USER_WRAP_UP_DONE' })
    expect(idle.phase).toBe('idle')
    expect(idle.incoming).toBeNull()
    expect(idle.lastEndedCallIds).toContain('sip-1')

    const polled = callSessionReducer(idle, {
      type: 'POLL_HYDRATE',
      phase: 'on_call',
      incoming: incoming({ call_id: 'sip-1' }),
      callStart: 2000,
    })
    expect(polled.phase).toBe('idle')
    expect(polled.incoming).toBeNull()
    expect(polled.epoch).toBe(idle.epoch)

    const restored = callSessionReducer(idle, {
      type: 'SOCKET_INCOMING',
      incoming: incoming({ call_id: 'sip-1' }),
      restore: true,
      alreadyAnswered: true,
      callStart: 2000,
    })
    expect(restored.phase).toBe('idle')

    const nextCall = callSessionReducer(idle, {
      type: 'POLL_HYDRATE',
      phase: 'on_call',
      incoming: incoming({ call_id: 'sip-2' }),
      callStart: 3000,
    })
    expect(nextCall.phase).toBe('on_call')
    expect(nextCall.incoming?.call_id).toBe('sip-2')
    expect(nextCall.lastEndedCallIds).toEqual([])
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

  it('cdr answered on an already-live call is a no-op when callStart does not move', () => {
    const onCall: CallSessionState = {
      ...initialCallSession,
      phase: 'on_call',
      incoming: incoming(),
      callStart: 4000,
      epoch: 9,
    }
    const same = callSessionReducer(onCall, {
      type: 'CDR_ANSWERED',
      callStart: 4000,
    })
    expect(same).toBe(onCall)
    expect(same.epoch).toBe(9)

    const later = callSessionReducer(onCall, {
      type: 'CDR_ANSWERED',
      callStart: 5000,
    })
    expect(later).toBe(onCall)

    const earlier = callSessionReducer(onCall, {
      type: 'CDR_ANSWERED',
      callStart: 3000,
    })
    expect(earlier.callStart).toBe(3000)
    expect(earlier.epoch).toBe(10)
  })

  it('cdr answered upgrades outbound ringing → on_call', () => {
    const dialing: CallSessionState = {
      ...initialCallSession,
      phase: 'outbound_ringing',
      incoming: incoming({ direction: 'outbound' }),
      callStart: 5000,
      epoch: 1,
    }
    const next = callSessionReducer(dialing, {
      type: 'CDR_ANSWERED',
      callStart: 4000,
    })
    expect(next.phase).toBe('on_call')
    expect(next.callStart).toBe(4000)
  })

  it('clears outbound ringing when hangup matches the source call id', () => {
    const ringing: CallSessionState = {
      ...initialCallSession,
      phase: 'outbound_ringing',
      incoming: incoming({
        call_id: 'webrtc-leg',
        source_call_id: 'sip-leg',
        direction: 'outbound',
      }),
      callStart: 5000,
      epoch: 1,
    }
    const next = callSessionReducer(ringing, {
      type: 'SOCKET_OUTBOUND_HANGUP',
      callId: 'sip-leg',
    })
    expect(next.phase).toBe('idle')
    expect(next.incoming).toBeNull()
  })

  it('does not revive an outbound call when its dial response arrives after hangup', () => {
    const idle = callSessionReducer(initialCallSession, { type: 'MIC_READY' })
    const ended = callSessionReducer(idle, {
      type: 'SOCKET_OUTBOUND_HANGUP',
      callId: 'failed-before-dial-response',
    })

    const lateStart = callSessionReducer(ended, {
      type: 'USER_DIAL_STARTED',
      incoming: incoming({
        call_id: 'failed-before-dial-response',
        direction: 'outbound',
      }),
      callStart: 5000,
    })

    expect(lateStart.phase).toBe('idle')
    expect(lateStart.incoming).toBeNull()
    expect(lateStart.epoch).toBe(ended.epoch)

    const nextCall = callSessionReducer(ended, {
      type: 'USER_DIAL_STARTED',
      incoming: incoming({ call_id: 'new-call', direction: 'outbound' }),
      callStart: 6000,
    })
    expect(nextCall.phase).toBe('outbound_ringing')
    expect(nextCall.incoming?.call_id).toBe('new-call')
  })

  it('media leg swap keeps business call id for hangup matching', () => {
    const onCall: CallSessionState = {
      ...initialCallSession,
      phase: 'on_call',
      incoming: incoming({ call_id: 'customer-leg' }),
      callStart: 1000,
      epoch: 1,
    }
    const swapped = callSessionReducer(onCall, {
      type: 'MEDIA_LEG_UPDATED',
      callId: 'new-webrtc-leg',
    })
    expect(swapped.incoming?.call_id).toBe('new-webrtc-leg')
    expect(swapped.incoming?.source_call_id).toBe('customer-leg')

    // Backend call-ended events reference the customer leg — must still match.
    expect(
      hangupMatches({
        hangupCallId: 'customer-leg',
        activeLegId: 'new-webrtc-leg',
        businessCallId: swapped.incoming?.call_id,
        sourceCallId: swapped.incoming?.source_call_id,
      }),
    ).toBe(true)

    // An existing source_call_id (consult target) is never clobbered.
    const consultOnCall: CallSessionState = {
      ...onCall,
      incoming: incoming({ call_id: 'old-leg', source_call_id: 'host-customer' }),
    }
    const consultSwapped = callSessionReducer(consultOnCall, {
      type: 'MEDIA_LEG_UPDATED',
      callId: 'new-leg',
    })
    expect(consultSwapped.incoming?.source_call_id).toBe('host-customer')

    // Idempotent update with the same id adds no source_call_id.
    const same = callSessionReducer(onCall, {
      type: 'MEDIA_LEG_UPDATED',
      callId: 'customer-leg',
    })
    expect(same.incoming?.source_call_id).toBeUndefined()
  })
})

describe('shouldHydrateMediaReconnect', () => {
  const base = {
    phase: 'on_call' as const,
    legState: 'idle' as const,
    endingCall: false,
    originating: false,
    browserOwnsMedia: true,
  }

  it('runs only for on_call idle/closed browser legs', () => {
    expect(shouldHydrateMediaReconnect(base)).toBe(true)
    expect(shouldHydrateMediaReconnect({ ...base, legState: 'closed' })).toBe(true)
    expect(shouldHydrateMediaReconnect({ ...base, legState: 'ready' })).toBe(false)
    expect(shouldHydrateMediaReconnect({ ...base, phase: 'wrap_up' })).toBe(false)
    expect(shouldHydrateMediaReconnect({ ...base, browserOwnsMedia: false })).toBe(false)
  })

  it('skips while hanging up or originating the outbound leg', () => {
    expect(shouldHydrateMediaReconnect({ ...base, endingCall: true })).toBe(false)
    expect(shouldHydrateMediaReconnect({ ...base, originating: true })).toBe(false)
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

describe('retainConnectedCallScreenPop', () => {
  it('retains the last connected call after the active session is cleared', () => {
    const connected = incoming({ call_id: 'connected-1' })
    const retained = retainConnectedCallScreenPop(null, 'on_call', connected, 1000)

    expect(retained).toEqual({ incoming: connected, callStart: 1000 })
    expect(retainConnectedCallScreenPop(retained, 'idle', null, null)).toBe(retained)
  })

  it('does not replace a connected screen pop with an unanswered ringing call', () => {
    const previous = {
      incoming: incoming({ call_id: 'connected-1' }),
      callStart: 1000,
    }

    expect(
      retainConnectedCallScreenPop(
        previous,
        'incoming',
        incoming({ call_id: 'ringing-2' }),
        2000,
      ),
    ).toBe(previous)
  })
})
