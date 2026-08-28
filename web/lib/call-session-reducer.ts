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
  /** Present only for auto-outbound agent dispatch offers. */
  source?: 'auto_outbound' | string
  task_id?: number
  /** Optional; when omitted the workspace resolves via call_record_id. */
  record_id?: number
  personal_assignment_type?: 'primary' | 'fallback'
}

export type CallSessionState = {
  phase: CallCenterPhase
  incoming: IncomingCall | null
  callStart: number | null
  /** Bumps on every live (socket/user) mutation — useful for diagnostics. */
  epoch: number
  /** Prevents a late dial response from reviving an already-ended call. */
  lastEndedOutboundCallId: string | null
  /** Business / media / hangup ids of the call that just ended. */
  lastEndedCallIds: string[]
}

export type RetainedCallScreenPop = {
  incoming: IncomingCall
  callStart: number | null
}

export type CallSessionEvent =
  | { type: 'MIC_READY' }
  | { type: 'MIC_DENIED' }
  | {
      type: 'POLL_HYDRATE'
      incoming: IncomingCall
      phase: 'incoming' | 'on_call' | 'wrap_up'
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
  lastEndedOutboundCallId: null,
  lastEndedCallIds: [],
}

function bump(state: CallSessionState, patch: Partial<CallSessionState>): CallSessionState {
  return { ...state, ...patch, epoch: state.epoch + 1 }
}

function collectEndedCallIds(
  state: CallSessionState,
  extra?: string | null,
): string[] {
  const ids = [extra, state.incoming?.call_id, state.incoming?.source_call_id]
  return [...new Set(ids.filter((id): id is string => Boolean(id)))]
}

function outboundEndedCallId(state: CallSessionState, extra?: string | null): string | null {
  if (extra) return extra
  if (state.incoming?.direction !== 'outbound') return state.lastEndedOutboundCallId
  return state.incoming.source_call_id ?? state.incoming.call_id
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
      // Stale in_call status after wrap-up must not revive the same bar.
      if (
        isRecentlyEndedCall(
          state.lastEndedCallIds,
          event.incoming.call_id,
          event.incoming.source_call_id,
        )
      ) {
        return state
      }
      return bump(state, {
        phase: event.phase,
        incoming: event.incoming,
        callStart: event.callStart,
        lastEndedCallIds: [],
      })

    case 'CDR_ANSWERED': {
      if (
        state.phase !== 'on_call' &&
        state.phase !== 'outbound_ringing' &&
        state.phase !== 'incoming'
      ) {
        return state
      }
      const nextStart = minCallStart(state.callStart, event.callStart)
      if (state.phase === 'incoming' || state.phase === 'outbound_ringing') {
        return bump(state, {
          phase: 'on_call',
          callStart: nextStart,
        })
      }
      // Already on_call: only write when the timestamp actually moves.
      // A no-op bump here re-renders the whole workspace on every tick and
      // was observed to spin epoch into the hundreds of thousands.
      if (nextStart === state.callStart) return state
      return bump(state, { callStart: nextStart })
    }

    case 'SOCKET_INCOMING': {
      if (
        isRecentlyEndedCall(
          state.lastEndedCallIds,
          event.incoming.call_id,
          event.incoming.source_call_id,
        )
      ) {
        return state
      }
      const toOnCall =
        !!event.restore || !!event.alreadyAnswered || state.phase === 'on_call'
      return bump(state, {
        incoming: event.incoming,
        callStart: event.callStart != null
          ? minCallStart(state.callStart, event.callStart) ?? event.callStart
          : state.callStart ?? event.incoming.startedAt,
        phase: toOnCall ? 'on_call' : 'incoming',
        lastEndedCallIds: [],
      })
    }

    case 'SOCKET_ANSWERED':
      if (state.phase !== 'incoming' && state.phase !== 'on_call') return state
      return bump(state, { phase: 'on_call' })

    case 'SOCKET_HANGUP': {
      if (!event.matches) return state
      const ended = collectEndedCallIds(state, event.callId)
      if (state.phase === 'incoming' || state.phase === 'outbound_ringing') {
        return bump(state, {
          phase: 'idle',
          incoming: null,
          callStart: null,
          lastEndedCallIds: ended,
          lastEndedOutboundCallId: outboundEndedCallId(state, event.callId),
        })
      }
      if (state.phase === 'on_call') {
        return bump(state, {
          phase: 'wrap_up',
          lastEndedCallIds: ended,
          lastEndedOutboundCallId: outboundEndedCallId(state, event.callId),
        })
      }
      return state
    }

    case 'SOCKET_OUTBOUND_ANSWERED':
      if (state.phase !== 'outbound_ringing') return state
      return bump(state, { phase: 'on_call' })

    case 'SOCKET_OUTBOUND_HANGUP': {
      const ended = collectEndedCallIds(state, event.callId)
      if (
        state.phase === 'outbound_ringing' ||
        state.phase === 'idle' ||
        state.phase === 'mic_check'
      ) {
        const sameCall =
          !state.incoming ||
          state.incoming.call_id === event.callId ||
          state.incoming.source_call_id === event.callId
        return bump(state, {
          phase: 'idle',
          incoming: sameCall ? null : state.incoming,
          callStart: sameCall ? null : state.callStart,
          lastEndedOutboundCallId: event.callId,
          lastEndedCallIds: ended,
        })
      }
      if (state.phase === 'on_call') {
        return bump(state, {
          phase: 'wrap_up',
          lastEndedOutboundCallId: event.callId,
          lastEndedCallIds: ended,
        })
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
      // Mark the wrapped-up call as ended so a slow in-flight poll cannot
      // re-hydrate the wrap-up panel right after the agent finished it.
      return bump(state, {
        phase: 'idle',
        incoming: null,
        callStart: null,
        lastEndedCallIds: collectEndedCallIds(state),
      })

    case 'USER_TRANSFER_ENDED':
      if (state.phase !== 'on_call' && state.phase !== 'outbound_ringing') {
        return state
      }
      return bump(state, {
        phase: 'wrap_up',
        lastEndedCallIds: collectEndedCallIds(state),
      })

    case 'USER_DIAL_STARTED':
      if (state.lastEndedOutboundCallId === event.incoming.call_id) return state
      if (isRecentlyEndedCall(state.lastEndedCallIds, event.incoming.call_id)) {
        return state
      }
      return bump(state, {
        phase: 'outbound_ringing',
        incoming: event.incoming,
        callStart: event.callStart,
        lastEndedOutboundCallId: null,
        lastEndedCallIds: [],
      })

    case 'USER_OUTBOUND_FAIL':
      return bump(state, { phase: 'idle', incoming: null, callStart: null })

    case 'MEDIA_LEG_UPDATED':
      if (!state.incoming) return state
      return bump(state, {
        incoming: {
          ...state.incoming,
          // Backend call-ended events reference the business (customer) call
          // id, not the rebuilt WebRTC leg. Keep it as source_call_id so
          // hangup matching still works after a media reconnect.
          source_call_id:
            state.incoming.source_call_id ??
            (state.incoming.call_id !== event.callId
              ? state.incoming.call_id
              : undefined),
          call_id: event.callId,
        },
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

export function isRecentlyEndedCall(
  endedIds: string[],
  ...candidates: Array<string | null | undefined>
): boolean {
  if (endedIds.length === 0) return false
  return candidates.some((id) => Boolean(id) && endedIds.includes(id as string))
}

export function shouldPollHydrateOnCall(
  resourceState: string | null | undefined,
  ringingButAnswered: boolean,
): boolean {
  return resourceState === 'in_call' || ringingButAnswered
}

/**
 * Upgrade 外呼中 → 通话中 when a later poll proves the customer already
 * answered. Poll hydrate is idle-only, so a missed cc.outbound_answered
 * would otherwise leave the desk on 外呼中 for the whole connected call.
 */
export function shouldUpgradeOutboundRingingFromPoll(opts: {
  phase: CallCenterPhase
  ringingCallId?: string | null
  sourceCallId?: string | null
  currentCallId?: string | null
  resourceState?: string | null
}): boolean {
  if (opts.phase !== 'outbound_ringing') return false
  if (opts.resourceState !== 'in_call') return false
  if (!opts.currentCallId) return false
  return (
    opts.currentCallId === opts.ringingCallId ||
    opts.currentCallId === opts.sourceCallId
  )
}

/**
 * Leave outbound ringing when a later status poll proves the server already
 * released this call. A stale pre-dial snapshot (ready/idle, older
 * resource_updated_at) must not cancel a live ring.
 */
export function shouldLeaveOutboundRingingFromPoll(opts: {
  phase: CallCenterPhase
  ringingCallId?: string | null
  callStart?: number | null
  currentCallId?: string | null
  resourceState?: string | null
  resourceUpdatedAtMs?: number | null
}): boolean {
  if (opts.phase !== 'outbound_ringing') return false
  if (!opts.ringingCallId) return false
  if (opts.currentCallId === opts.ringingCallId) return false
  if (opts.resourceUpdatedAtMs == null || opts.callStart == null) return false
  if (opts.resourceUpdatedAtMs < opts.callStart) return false
  const rs = opts.resourceState
  if (rs === 'reserved' || rs === 'ringing' || rs === 'in_call') return false
  return true
}

/**
 * Leave 通话中 when a later status poll proves this agent's call resource was
 * already released. Only an explicitly free resource counts as proof: consult
 * and media reconnects re-key current_call_id while the call is still live, so
 * a call-id mismatch on its own must never end the call.
 */
export function shouldLeaveOnCallFromPoll(opts: {
  phase: CallCenterPhase
  callStart?: number | null
  resourceState?: string | null
  resourceUpdatedAtMs?: number | null
}): boolean {
  if (opts.phase !== 'on_call') return false
  if (opts.resourceUpdatedAtMs == null || opts.callStart == null) return false
  if (opts.resourceUpdatedAtMs < opts.callStart) return false
  const rs = opts.resourceState
  return rs === 'idle' || rs === 'after_call_work'
}

export type WebRtcLegState = 'idle' | 'connecting' | 'ready' | 'failed' | 'closed'

/**
 * Whether the on_call hydrate effect should POST media-reconnect.
 * Skip while the agent is hanging up or still originating the outbound leg —
 * those races 404 after a short answered call and toast a fake WebRTC error.
 */
export function shouldHydrateMediaReconnect(opts: {
  phase: CallCenterPhase
  legState: WebRtcLegState
  endingCall: boolean
  originating: boolean
  browserOwnsMedia: boolean
}): boolean {
  if (opts.endingCall || opts.originating) return false
  if (opts.phase !== 'on_call') return false
  if (!opts.browserOwnsMedia) return false
  return opts.legState === 'idle' || opts.legState === 'closed'
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

/** Keep the latest connected call available to the screen pop after wrap-up. */
export function retainConnectedCallScreenPop(
  current: RetainedCallScreenPop | null,
  phase: CallCenterPhase,
  incoming: IncomingCall | null,
  callStart: number | null,
): RetainedCallScreenPop | null {
  if (!incoming || (phase !== 'on_call' && phase !== 'wrap_up')) return current
  return { incoming, callStart }
}
