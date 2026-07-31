/**
 * Call-center UI session reducer — single owner of phase / incoming / callStart.
 *
 * Event priority (encoded in handlers, not by race):
 *   socket / user actions  >  poll hydrate
 * Poll may only hydrate when phase === 'idle'. It must never clear a live call
 * (that was the 17:09 / 17:14 patch-pong root cause).
 */

export type CallCenterPhase =
  | 'mic_check'
  | 'mic_denied'
  | 'idle'
  | 'incoming'
  | 'outbound_ringing'
  | 'on_call'
  | 'wrap_up'

export type IncomingCall = {
  offer_id: string
  call_id: string
  from: string
  to: string
  queue_id: number | null
  call_type?: string
  startedAt: number
  direction?: 'inbound' | 'outbound'
  device_type?: string
  source_call_id?: string
  customer_from?: string
  customer_to?: string
  user_id?: number
  user_public_id?: string
}

export type CallSessionState = {
  phase: CallCenterPhase
  incoming: IncomingCall | null
  callStart: number | null
  /** Bumps on every live (socket/user) mutation — useful for diagnostics. */
  epoch: number
}

export type CallSessionEvent =
  | { type: 'MIC_READY' }
  | { type: 'MIC_DENIED' }
  | {
      type: 'POLL_HYDRATE'
      incoming: IncomingCall
      phase: 'incoming' | 'on_call'
      callStart: number
    }
  | { type: 'CDR_ANSWERED'; callStart?: number | null }
  | {
      type: 'SOCKET_INCOMING'
      incoming: IncomingCall
      restore?: boolean
      alreadyAnswered?: boolean
      callStart?: number | null
    }
  | { type: 'SOCKET_ANSWERED' }
  | {
      type: 'SOCKET_HANGUP'
      callId: string
      activeLegId?: string | null
      matches: boolean
    }
  | { type: 'SOCKET_OUTBOUND_ANSWERED' }
  | {
      type: 'SOCKET_OUTBOUND_HANGUP'
      callId: string
    }
  | { type: 'USER_ACCEPT_OK'; callStart: number }
  | { type: 'USER_ACCEPT_FAIL' }
  | { type: 'USER_REJECT' }
  | { type: 'USER_WRAP_UP_DONE' }
  | { type: 'USER_STATUS_ENDS_WRAP_UP' }
  | { type: 'USER_TRANSFER_ENDED' }
  | {
      type: 'USER_DIAL_STARTED'
      incoming: IncomingCall
      callStart: number
    }
  | { type: 'USER_OUTBOUND_FAIL' }
  | { type: 'MEDIA_LEG_UPDATED'; callId: string }
  | { type: 'FORCE_ON_CALL' }

export const initialCallSession: CallSessionState = {
  phase: 'mic_check',
  incoming: null,
  callStart: null,
  epoch: 0,
}

function bump(state: CallSessionState, patch: Partial<CallSessionState>): CallSessionState {
  return { ...state, ...patch, epoch: state.epoch + 1 }
}

function minCallStart(
  prev: number | null,
  next: number | null | undefined,
): number | null {
  if (next == null) return prev
  if (prev == null || next < prev) return next
  return prev
}

/** Pure reducer — no I/O, no ringtone, no toast. */
export function callSessionReducer(
  state: CallSessionState,
  event: CallSessionEvent,
): CallSessionState {
  switch (event.type) {
    case 'MIC_DENIED':
      if (state.phase !== 'mic_check') return state
      return bump(state, { phase: 'mic_denied' })

    case 'MIC_READY':
      if (state.phase !== 'mic_check') return state
      return bump(state, { phase: 'idle' })

    case 'POLL_HYDRATE':
      // Hard rule: poll never overrides a live session.
      if (state.phase !== 'idle') return state
      return bump(state, {
        phase: event.phase,
        incoming: event.incoming,
        callStart: event.callStart,
      })

    case 'CDR_ANSWERED': {
      if (
        state.phase !== 'on_call' &&
        state.phase !== 'outbound_ringing' &&
        state.phase !== 'incoming'
      ) {
        return state
      }
      if (state.phase === 'incoming') {
        return bump(state, {
          phase: 'on_call',
          callStart: minCallStart(state.callStart, event.callStart),
        })
      }
      return bump(state, {
        callStart: minCallStart(state.callStart, event.callStart),
      })
    }

    case 'SOCKET_INCOMING': {
      const toOnCall =
        !!event.restore || !!event.alreadyAnswered || state.phase === 'on_call'
      return bump(state, {
        incoming: event.incoming,
        callStart: event.callStart != null
          ? minCallStart(state.callStart, event.callStart) ?? event.callStart
          : state.callStart ?? event.incoming.startedAt,
        phase: toOnCall ? 'on_call' : 'incoming',
      })
    }

    case 'SOCKET_ANSWERED':
      if (state.phase !== 'incoming' && state.phase !== 'on_call') return state
      return bump(state, { phase: 'on_call' })

    case 'SOCKET_HANGUP': {
      if (!event.matches) return state
      if (state.phase === 'incoming' || state.phase === 'outbound_ringing') {
        return bump(state, { phase: 'idle', incoming: null, callStart: null })
      }
      if (state.phase === 'on_call') {
        return bump(state, { phase: 'wrap_up' })
      }
      return state
    }

    case 'SOCKET_OUTBOUND_ANSWERED':
      if (state.phase !== 'outbound_ringing') return state
      return bump(state, { phase: 'on_call' })

    case 'SOCKET_OUTBOUND_HANGUP': {
      if (
        state.phase === 'outbound_ringing' ||
        state.phase === 'idle' ||
        state.phase === 'mic_check'
      ) {
        const sameCall =
          !state.incoming || state.incoming.call_id === event.callId
        return bump(state, {
          phase: 'idle',
          incoming: sameCall ? null : state.incoming,
          callStart: sameCall ? null : state.callStart,
        })
      }
      if (state.phase === 'on_call') {
        return bump(state, { phase: 'wrap_up' })
      }
      return state
    }

    case 'USER_ACCEPT_OK':
      return bump(state, { phase: 'on_call', callStart: event.callStart })

    case 'USER_ACCEPT_FAIL':
    case 'USER_REJECT':
      return bump(state, { phase: 'idle', incoming: null, callStart: null })

    case 'USER_WRAP_UP_DONE':
    case 'USER_STATUS_ENDS_WRAP_UP':
      return bump(state, { phase: 'idle', incoming: null, callStart: null })

    case 'USER_TRANSFER_ENDED':
      if (state.phase !== 'on_call' && state.phase !== 'outbound_ringing') {
        return state
      }
      return bump(state, { phase: 'wrap_up' })

    case 'USER_DIAL_STARTED':
      return bump(state, {
        phase: 'outbound_ringing',
        incoming: event.incoming,
        callStart: event.callStart,
      })

    case 'USER_OUTBOUND_FAIL':
      return bump(state, { phase: 'idle', incoming: null, callStart: null })

    case 'MEDIA_LEG_UPDATED':
      if (!state.incoming) return state
      return bump(state, {
        incoming: { ...state.incoming, call_id: event.callId },
      })

    case 'FORCE_ON_CALL':
      return bump(state, { phase: 'on_call' })

    default:
      return state
  }
}

/** Whether poll hydrate is allowed for the current phase. */
export function canPollHydrate(phase: CallCenterPhase): boolean {
  return phase === 'idle'
}

/** Hangup call_id match — same rules as previous runtime onHangup. */
export function hangupMatches(opts: {
  hangupCallId?: string | null
  activeLegId?: string | null
  businessCallId?: string | null
  sourceCallId?: string | null
}): boolean {
  const cid = opts.hangupCallId
  if (!cid) return false
  return (
    cid === opts.activeLegId ||
    cid === opts.businessCallId ||
    cid === opts.sourceCallId
  )
}
