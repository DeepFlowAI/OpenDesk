'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'

import { agentDeviceKeys, useMyCurrentCallDevice } from '@/service/use-agent-devices'
import { mapOutboundFailure } from '@/app/components/features/call-center/outbound-failure-message'
import { callRecordCustomerNumber } from '@/app/components/features/call-center/call-record-utils'
import { formatWebRtcDeviceError } from '@/lib/call-record-labels'
import { useCallControl, type CallControlApi } from '@/app/components/features/call-center/use-call-control'
import { useMicrophone } from '@/app/components/features/call-center/use-microphone'
import { useRingtone } from '@/app/components/features/call-center/use-ringtone'
import { useAutoAnswerChime } from '@/app/components/features/call-center/use-auto-answer-chime'
import { useWebRTCLeg } from '@/app/components/features/call-center/use-webrtc-leg'
import { useSocketStore } from '@/context/socket-store'
import {
  callCenterQueryKeys,
  cancelOutboundCall,
  hangupCurrentCall,
  rejectCurrentCall,
  useCallRecords,
  useCloseWebRTCSession,
  useMyAgentStatus,
  useSetAgentStatus,
} from '@/service/use-call-center'
import { useSystemSettings } from '@/service/use-system-settings'
import type {
  AgentStatus,
  AgentStatusResponse,
  CallRecordListItem,
  CallRecordListResponse,
} from '@/models/call-center'
import { CcSocketEvent } from '@/lib/call-center-events'
import { trackCallCenter } from '@/lib/call-center-telemetry'
import { callRecordAnsweredByAgent, callRecordCustomerConnected } from '@/lib/call-record-ownership'
import {
  autoOutboundBusinessTabForIncoming,
  restoredAutoOutboundContext,
  shouldAutoAcceptAutoOutbound,
  shouldKeepAutoAnswerChime,
} from '@/lib/auto-outbound-incoming'
import {
  callSessionReducer,
  canPollHydrate,
  hangupMatches,
  initialCallSession,
  isRecentlyEndedCall,
  isRecentlyEndedIncoming,
  retainConnectedCallScreenPop,
  shouldHydrateMediaReconnect,
  shouldLeaveOnCallFromPoll,
  shouldLeaveOutboundRingingFromPoll,
  shouldPollHydrateOnCall,
  shouldUpgradeOutboundRingingFromPoll,
  type CallCenterPhase,
  type CallSessionEvent,
  type IncomingCall,
} from '@/lib/call-session-reducer'

export type { CallCenterPhase, IncomingCall }

/** SIP desk-phone media lives on the handset — never rebuild in the browser. */
function browserOwnsMedia(deviceType?: string | null): boolean {
  return deviceType !== 'sip_phone'
}

type DialStartedInfo = {
  callId: string
  destination: string
  outboundNumber: string
}

export const CALL_STATUS_OPTIONS: {
  value: AgentStatus
  label: string
  dotClass: string
  textClass: string
}[] = [
  { value: 'ready', label: '就绪', dotClass: 'bg-[#22C55E]', textClass: 'text-[#22C55E]' },
  { value: 'busy', label: '忙碌', dotClass: 'bg-red-500', textClass: 'text-red-500' },
  { value: 'break', label: '小休', dotClass: 'bg-amber-500', textClass: 'text-amber-500' },
  { value: 'after_call_work', label: '整理中', dotClass: 'bg-amber-500', textClass: 'text-amber-500' },
  { value: 'offline', label: '离线', dotClass: 'bg-neutral-400', textClass: 'text-[#737373]' },
]

export function formatCallDuration(ms: number | null): string {
  if (!ms || ms <= 0) return '00:00'
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function callStartMsFromIso(raw?: string | null): number | null {
  if (!raw) return null
  const ms = Date.parse(raw)
  return Number.isFinite(ms) ? ms : null
}

/** Prefer the first agent bridge, then customer connection and call start. */
function callStartMsFromRecord(rec?: {
  first_agent_connected_at?: string | null
  customer_connected_at?: string | null
  started_at?: string | null
} | null): number | null {
  return callStartMsFromIso(
    rec?.first_agent_connected_at || rec?.customer_connected_at || rec?.started_at,
  )
}

type CallCenterRuntimeValue = {
  mic: ReturnType<typeof useMicrophone>
  leg: ReturnType<typeof useWebRTCLeg>
  callControl: CallControlApi
  phase: CallCenterPhase
  incoming: IncomingCall | null
  callStart: number | null
  screenPopIncoming: IncomingCall | null
  screenPopCallStart: number | null
  now: number
  status: AgentStatusResponse | undefined
  records: CallRecordListResponse | undefined
  recordsPage: number
  setRecordsPage: (page: number) => void
  selectedRecordId: number | null
  setSelectedRecordId: (id: number | null) => void
  draftDialNumber: string
  setDraftDialNumber: (value: string) => void
  draftOutboundNumber: string
  setDraftOutboundNumber: (value: string) => void
  callSummaryTab: 'summary' | 'ticket' | 'auto_outbound' | 'personal_auto_outbound'
  setCallSummaryTab: (tab: 'summary' | 'ticket' | 'auto_outbound' | 'personal_auto_outbound') => void
  selectedRecord: CallRecordListItem | null
  currentRecord: CallRecordListItem | null
  callSummaryRecordId: number | null
  callRecordForTicket: CallRecordListItem | null
  screenPopNumber: string
  showEmptyCallState: boolean
  statusChangePending: boolean
  /** Epoch ms when the session entered wrap_up (for auto-outbound countdown). */
  wrapUpStartedAt: number | null
  /** Server-side wrap-up deadline (epoch ms) from agent-status; null when unknown. */
  wrapUpUntil: number | null
  /** Remaining wrap-up time (ms); null when not in wrap_up or manual-only wrap-up. */
  wrapUpRemainingMs: number | null
  setAgentStatus: (status: AgentStatus) => Promise<void>
  accept: () => Promise<boolean>
  reject: () => Promise<void>
  hangup: () => Promise<void>
  completeWrapUp: () => void
  handleDialStarted: (info: DialStartedInfo) => Promise<void>
}

/**
 * Events that are expected to move the desk forward. If one of these leaves
 * the session untouched, the desk is out of sync with the server and that is
 * worth a warning — unlike, say, a mic event that is routinely a no-op.
 */
const PHASE_ADVANCING_EVENTS = new Set<CallSessionEvent['type']>([
  'POLL_HYDRATE',
  'CDR_ANSWERED',
  'SOCKET_INCOMING',
  'SOCKET_ANSWERED',
  'SOCKET_HANGUP',
  'SOCKET_OUTBOUND_ANSWERED',
  'SOCKET_OUTBOUND_HANGUP',
  'USER_DIAL_STARTED',
  'USER_TRANSFER_ENDED',
])

const CallCenterRuntimeContext = createContext<CallCenterRuntimeValue | null>(null)

type CallCenterProviderProps = {
  children: ReactNode
  recordsEnabled?: boolean
  controlEnabled?: boolean
}

export function CallCenterProvider({
  children,
  recordsEnabled = true,
  controlEnabled = true,
}: CallCenterProviderProps) {
  const mic = useMicrophone({ autoRequestOnGranted: false })
  const { data: status, dataUpdatedAt: statusFetchedAtMs, refetch: refetchStatus } = useMyAgentStatus()
  const { data: systemSettings } = useSystemSettings()
  const { data: currentDevice } = useMyCurrentCallDevice()
  const queryClient = useQueryClient()
  const setStatusMutation = useSetAgentStatus()
  const closeSession = useCloseWebRTCSession()
  const leg = useWebRTCLeg()
  const callControl = useCallControl(leg.setMuted)
  // Stable references to the two control-result handlers so the socket effect
  // (which subscribes to cc.consult_result / cc.transfer_result) doesn't
  // re-run on every render — callControl itself is a fresh object each render.
  const handleConsultResult = callControl.onConsultResult
  const handleTransferResult = callControl.onTransferResult
  const handleConferenceResult = callControl.onConferenceResult
  const handleConferenceParticipantLeft = callControl.onConferenceParticipantLeft
  const exposedCallControl = useMemo<CallControlApi>(() => {
    if (controlEnabled) return callControl
    return {
      ...callControl,
      toggleMute: () => undefined,
      toggleHold: async () => undefined,
      sendDtmf: async () => undefined,
      submitTransfer: async () => false,
      beginConsult: async () => false,
      finishConsult: async () => undefined,
      addParticipant: async () => false,
      mergeConference: async () => undefined,
      removeParticipant: async () => undefined,
      leaveConference: async () => false,
      endAll: async () => false,
    }
  }, [callControl, controlEnabled])
  const ringtone = useRingtone()
  const autoAnswerChime = useAutoAnswerChime()
  const { socket } = useSocketStore()
  const [recordsPage, setRecordsPage] = useState(1)
  const recordsQueryParams = useMemo(
    () => ({
      page: recordsPage,
      per_page: 20,
      // Workspace sidebar: last 24 hours (not a fixed "today" calendar day).
      start_time: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    }),
    [recordsPage],
  )
  const { data: records, refetch: refetchRecords } = useCallRecords(
    recordsQueryParams,
    { enabled: recordsEnabled },
  )

  const refetchCallRecords = useCallback(() => {
    if (!recordsEnabled) return
    void refetchRecords()
    // A call ending also changes rows on the full records page (different
    // query key than the sidebar's), so invalidate the shared records root.
    void queryClient.invalidateQueries({ queryKey: callCenterQueryKeys.recordsRoot() })
  }, [recordsEnabled, refetchRecords, queryClient])

  const [session, dispatchRaw] = useReducer(callSessionReducer, initialCallSession)
  const { phase, incoming, callStart } = session
  const [retainedScreenPop, setRetainedScreenPop] = useState<{
    incoming: IncomingCall
    callStart: number | null
  } | null>(null)
  const [now, setNow] = useState<number>(Date.now())
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null)
  const [draftDialNumber, setDraftDialNumber] = useState('')
  const [draftOutboundNumber, setDraftOutboundNumber] = useState('')
  const [callSummaryTab, setCallSummaryTab] = useState<'summary' | 'ticket' | 'auto_outbound' | 'personal_auto_outbound'>('summary')
  const [wrapUpStartedAt, setWrapUpStartedAt] = useState<number | null>(null)
  // Deadline pushed by the server via cc.wrap_up_started at the moment the
  // agent enters after-call work — the countdown must not wait for the next
  // agent-status poll (which can land near the deadline itself).
  const [wrapUpUntilLocal, setWrapUpUntilLocal] = useState<number | null>(null)
  // Server-authoritative wrap-up deadline (epoch ms), fixed at hangup time.
  // The polled value wins once it catches up; until then the socket-pushed
  // local deadline drives the countdown.
  const wrapUpUntilMs = useMemo(() => {
    const iso = status?.wrap_up_until
    if (iso) {
      const ms = Date.parse(iso)
      if (Number.isFinite(ms)) return ms
    }
    return wrapUpUntilLocal
  }, [status?.wrap_up_until, wrapUpUntilLocal])
  const wrapUpRemainingMs = useMemo(() => {
    if (phase !== 'wrap_up') return null
    if (wrapUpUntilMs != null) {
      return Math.max(0, wrapUpUntilMs - now)
    }
    const configuredSeconds = systemSettings?.call_wrapup_seconds ?? 30
    if (wrapUpStartedAt != null && configuredSeconds > 0) {
      return Math.max(0, wrapUpStartedAt + configuredSeconds * 1000 - now)
    }
    return null
  }, [phase, wrapUpUntilMs, wrapUpStartedAt, systemSettings?.call_wrapup_seconds, now])
  // Deadline (ms) for which the expiry refetch already fired — fire once per
  // wrap-up, not on every 1s tick past the deadline.
  const wrapUpExpiredFiredRef = useRef<number | null>(null)
  // Dedup socket hangup toast vs dial-webrtc 410 toast for the same failure.
  const lastOutboundFailToastRef = useRef<string | null>(null)
  // A fast callee can answer before POST /dial returns and USER_DIAL_STARTED
  // establishes the local session. Keep those call-scoped events until the
  // matching dial response arrives instead of dropping them in idle phase.
  const earlyOutboundAnsweredRef = useRef<Set<string>>(new Set())
  // A carrier failure can arrive before POST /dial returns. Remember that
  // terminal event so the late response cannot start UI/media for a dead call.
  const earlyOutboundEndedRef = useRef<Set<string>>(new Set())
  // Prevent overlapping media-reconnect attempts after refresh / consult end.
  const mediaReconnectInFlightRef = useRef(false)
  // Hangup / originate in flight — hydrate must not POST media-reconnect.
  const endingCallRef = useRef(false)
  const originatingRef = useRef(false)
  // Restore 结束咨询 UI at most once per on_call session from server state.
  const consultUiRestoredRef = useRef(false)
  // Dedup auto-accept for the same offer_id (push redelivery / re-render).
  const autoAcceptedOfferIdsRef = useRef<Set<string>>(new Set())
  const acceptRef = useRef<() => Promise<boolean>>(async () => false)
  // Offer this tab is accepting or has accepted. Two triggers for one ring (a
  // double click, or the panel and the call bar) both see the pre-render leg
  // state, and a second accept rebuilds the leg and then tears down the media
  // the first one connected.
  const acceptingOfferRef = useRef<string | null>(null)
  const sessionRef = useRef(session)
  sessionRef.current = session
  // Dedupe keys for the repeat-prone diagnostics: a no-op event and a state
  // drift both recur on every poll tick, and one report per situation is
  // enough to diagnose it.
  const reportedNoEffectRef = useRef<Set<string>>(new Set())
  const reportedDriftRef = useRef<Set<string>>(new Set())

  // Between calls there is nothing left to suppress, so drop the keys instead
  // of growing them for the lifetime of a desk tab that is never reloaded.
  useEffect(() => {
    if (phase !== 'idle') return
    reportedNoEffectRef.current.clear()
    reportedDriftRef.current.clear()
  }, [phase])

  // A window that does not hold call control registers no socket handlers, so
  // it legitimately sees none of the events below. Record which kind of window
  // this is, or its silence looks like a lost event.
  useEffect(() => {
    trackCallCenter('runtime_ready', {
      control_enabled: controlEnabled,
      records_enabled: recordsEnabled,
      device_type: currentDevice?.device_type,
    })
  }, [controlEnabled, recordsEnabled, currentDevice?.device_type])

  useEffect(() => {
    setRetainedScreenPop((current) =>
      retainConnectedCallScreenPop(current, phase, incoming, callStart),
    )
  }, [phase, incoming, callStart])

  const screenPopIncoming = incoming ?? retainedScreenPop?.incoming ?? null
  const screenPopCallStart = incoming ? callStart : (retainedScreenPop?.callStart ?? null)

  useEffect(() => {
    if (controlEnabled) return
    ringtone.stop()
    autoAnswerChime.stop()
    leg.goOffline()
    mic.stop()
  }, [controlEnabled, leg, mic, ringtone, autoAnswerChime])

  /** Single write path for session state — logs every dispatched event. */
  const dispatch = useCallback((event: CallSessionEvent) => {
    const before = sessionRef.current
    console.debug('[cc-session]', {
      event: event.type,
      from: before.phase,
      callId: before.incoming?.call_id ?? null,
      epoch: before.epoch,
      ts: Date.now(),
      detail: event,
    })
    // The reducer is pure, so replaying it here reveals what this event will
    // actually do. An event that leaves state untouched is the signature of a
    // desk stuck on the wrong phase, and it is otherwise invisible in logs.
    const after = callSessionReducer(before, event)
    const eventCallId = 'callId' in event
      ? event.callId
      : 'incoming' in event
        ? event.incoming.call_id
        : undefined
    if (after === before) {
      if (PHASE_ADVANCING_EVENTS.has(event.type)) {
        // Keying on the call keeps one desk's recurring problem to a single
        // report without silencing the same problem on the next call.
        const callKey = eventCallId ?? before.incoming?.call_id ?? ''
        const dedupeKey = `${event.type}:${callKey}:${before.phase}`
        if (!reportedNoEffectRef.current.has(dedupeKey)) {
          reportedNoEffectRef.current.add(dedupeKey)
          trackCallCenter(
            'event_no_effect',
            {
              event: event.type,
              phase: before.phase,
              session_call_id: before.incoming?.call_id,
              session_source_call_id: before.incoming?.source_call_id,
              event_call_id: eventCallId,
            },
            'warn',
          )
        }
      }
    } else if (after.phase !== before.phase) {
      trackCallCenter('phase_changed', {
        event: event.type,
        from: before.phase,
        to: after.phase,
        call_id: after.incoming?.call_id ?? before.incoming?.call_id,
        source_call_id: after.incoming?.source_call_id,
        direction: after.incoming?.direction ?? before.incoming?.direction,
      })
    }
    dispatchRaw(event)
  }, [])

  const selectedRecord =
    selectedRecordId != null
      ? (records?.items ?? []).find((r) => r.id === selectedRecordId) ?? null
      : null
  // A transferred/consult leg carries the media leg id in `call_id`; the CDR
  // lives under the customer `source_call_id` — match both so transcript
  // history and the summary panel still resolve for the receiving agent.
  const currentRecord =
    screenPopIncoming?.call_id || screenPopIncoming?.source_call_id
      ? (records?.items ?? []).find(
          (r) =>
            r.call_id === screenPopIncoming?.call_id ||
            (screenPopIncoming?.source_call_id != null &&
              r.call_id === screenPopIncoming.source_call_id),
        ) ?? null
      : null
  const callSummaryRecordId = selectedRecord?.id ?? currentRecord?.id ?? null
  const callRecordForTicket = selectedRecord ?? currentRecord

  const defaultBusinessTab = autoOutboundBusinessTabForIncoming(screenPopIncoming)
  const defaultCallSummaryTab = selectedRecord ? 'summary' : (defaultBusinessTab ?? 'summary')
  const callSummaryContextKey = selectedRecord
    ? `record:${selectedRecord.id}`
    : screenPopIncoming?.call_id
      ? `call:${screenPopIncoming.call_id}:${defaultCallSummaryTab}`
      : 'empty'

  useEffect(() => {
    setCallSummaryTab(defaultCallSummaryTab)
  }, [callSummaryContextKey, defaultCallSummaryTab])

  useEffect(() => {
    if (
      phase !== 'on_call' &&
      phase !== 'incoming' &&
      phase !== 'outbound_ringing' &&
      phase !== 'wrap_up'
    ) {
      return
    }
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [phase])

  useEffect(() => {
    if (mic.state === 'denied' || mic.state === 'error') {
      dispatch({ type: 'MIC_DENIED' })
    } else if (mic.state === 'granted' || mic.state === 'prompt') {
      dispatch({ type: 'MIC_READY' })
    }
  }, [mic.state, dispatch])

  // Backup hydrate: if Socket re-push is missed, recover ringing / in-call from
  // the polled agent-status resource snapshot after a page refresh.
  // Reducer enforces: poll never overrides a live (non-idle) session.
  useEffect(() => {
    if (!status) return
    if (!canPollHydrate(phase)) return
    // Refresh during after-call work: restore the wrap-up panel while the
    // server-side deadline is still in the future. Expired (or deadline-less)
    // wrap-ups are left to the sweep / next poll, which flips the agent ready.
    if (status.status === 'after_call_work') {
      const wrapCallId = status.wrap_up_call_id
      const untilMs = status.wrap_up_until ? Date.parse(status.wrap_up_until) : NaN
      if (
        wrapCallId &&
        Number.isFinite(untilMs) &&
        untilMs > Date.now() &&
        !isRecentlyEndedCall(session.lastEndedCallIds, wrapCallId)
      ) {
        const rec = (records?.items ?? []).find((r) => r.call_id === wrapCallId)
        const startMs = callStartMsFromRecord(rec) ?? Date.now()
        setSelectedRecordId(null)
        dispatch({
          type: 'POLL_HYDRATE',
          phase: 'wrap_up',
          callStart: startMs,
          incoming: {
            offer_id: '',
            call_id: wrapCallId,
            from: rec?.direction === 'inbound' ? rec.customer_number || '' : rec?.service_number || '',
            to: rec?.direction === 'inbound' ? rec.service_number || '' : rec?.customer_number || '',
            queue_id: status.queue_id ?? null,
            direction: status.direction ?? 'inbound',
            device_type: currentDevice?.device_type || undefined,
            startedAt: startMs,
            ...restoredAutoOutboundContext(status),
          },
        })
      }
      return
    }
    const callId = status.current_call_id
    if (!callId) return
    if (isRecentlyEndedCall(session.lastEndedCallIds, callId)) return
    const rec = (records?.items ?? []).find((r) => r.call_id === callId)
    const deviceType = currentDevice?.device_type || undefined
    // Ringing anchors to resource_updated_at (when this agent's resource
    // entered ringing) — the CDR started_at is the customer's dial time and
    // would count queue wait into the ring timer; Date.now() would reset the
    // timer on refresh. Consult targets have no CDR — fall back to Redis
    // in_call_since.
    const startMs =
      status.resource_state === 'ringing'
        ? (callStartMsFromIso(status.resource_updated_at) ??
          callStartMsFromRecord(rec) ??
          Date.now())
        : (callStartMsFromRecord(rec) ??
          callStartMsFromIso(status.in_call_since) ??
          Date.now())
    // Still ringing in Redis — but this agent's own CDR already answered
    // (SIP handset off-hook before mark_in_call) must hydrate as 通话中,
    // not a second 来电. Another agent's answered CDR (queue transfer) must not.
    const ringingButAnswered =
      status.resource_state === 'ringing' &&
      !!status.offer_id &&
      callRecordAnsweredByAgent(rec, status.employee_id)
    if (status.resource_state === 'ringing' && status.offer_id && !ringingButAnswered) {
      setSelectedRecordId(null)
      dispatch({
        type: 'POLL_HYDRATE',
        phase: 'incoming',
        callStart: startMs,
        incoming: {
          offer_id: status.offer_id,
          call_id: callId,
          from: rec?.direction === 'inbound' ? rec.customer_number || '' : rec?.service_number || '',
          to: rec?.direction === 'inbound' ? rec.service_number || '' : rec?.customer_number || '',
          queue_id: status.queue_id ?? null,
          direction: status.direction ?? 'inbound',
          device_type: deviceType,
          startedAt: startMs,
          ...restoredAutoOutboundContext(status),
        },
      })
      if (controlEnabled) ringtone.start()
      refetchCallRecords()
      return
    }
    // Visible busy is derived from reserved/ringing/in_call resources. It is
    // not proof that the remote party answered, so only hydrate on an explicit
    // in-call resource or an answered CDR owned by this agent.
    if (shouldPollHydrateOnCall(status.resource_state, ringingButAnswered)) {
      setSelectedRecordId(null)
      dispatch({
        type: 'POLL_HYDRATE',
        phase: 'on_call',
        callStart: startMs,
        incoming: {
          offer_id: status.offer_id || '',
          call_id: callId,
          from: rec?.direction === 'inbound' ? rec.customer_number || '' : rec?.service_number || '',
          to: rec?.direction === 'inbound' ? rec.service_number || '' : rec?.customer_number || '',
          queue_id: status.queue_id ?? null,
          direction: status.direction ?? 'inbound',
          device_type: deviceType,
          startedAt: startMs,
          ...restoredAutoOutboundContext(status),
        },
      })
      refetchCallRecords()
    }
  }, [status, phase, records, ringtone, refetchCallRecords, currentDevice?.device_type, dispatch, controlEnabled, session.lastEndedCallIds])

  // Outbound ringing is short-lived and its outcome is uncertain. Socket.IO
  // replays nothing after a dropped connection, and the regular status poll
  // (30s) routinely outlasts the whole call — long enough to strand the desk
  // on 外呼中 for its entire duration. Reconcile against the server quickly
  // while ringing, and stop as soon as the phase resolves.
  useEffect(() => {
    if (phase !== 'outbound_ringing') return
    const timer = setInterval(() => {
      void refetchStatus()
    }, 3_000)
    return () => clearInterval(timer)
  }, [phase, refetchStatus])

  // Missed cc.outbound_answered: poll shows this outbound already in_call.
  useEffect(() => {
    if (
      !shouldUpgradeOutboundRingingFromPoll({
        phase,
        ringingCallId: incoming?.call_id,
        sourceCallId: incoming?.source_call_id,
        currentCallId: status?.current_call_id,
        resourceState: status?.resource_state,
      })
    ) {
      return
    }
    trackCallCenter(
      'poll_reconcile',
      {
        kind: 'outbound_answered',
        call_id: incoming?.call_id,
        source_call_id: incoming?.source_call_id,
        current_call_id: status?.current_call_id,
        resource_state: status?.resource_state,
      },
      'warn',
    )
    ringtone.stop()
    dispatch({ type: 'SOCKET_OUTBOUND_ANSWERED' })
    refetchCallRecords()
  }, [
    phase,
    incoming?.call_id,
    incoming?.source_call_id,
    status?.current_call_id,
    status?.resource_state,
    ringtone,
    dispatch,
    refetchCallRecords,
  ])

  // Missed cc.outbound_hangup: poll shows this outbound already released.
  useEffect(() => {
    if (
      !shouldLeaveOutboundRingingFromPoll({
        phase,
        ringingCallId: incoming?.call_id,
        callStart: callStart ?? incoming?.startedAt,
        currentCallId: status?.current_call_id,
        resourceState: status?.resource_state,
        resourceUpdatedAtMs: callStartMsFromIso(status?.resource_updated_at),
        statusFetchedAtMs,
      })
    ) {
      return
    }
    const callId = incoming?.call_id
    if (!callId) return
    trackCallCenter(
      'poll_reconcile',
      {
        kind: 'outbound_released',
        call_id: callId,
        current_call_id: status?.current_call_id,
        resource_state: status?.resource_state,
      },
      'warn',
    )
    endingCallRef.current = true
    ringtone.stop()
    leg.goOffline()
    mic.stop()
    dispatch({ type: 'SOCKET_OUTBOUND_HANGUP', callId })
    void refetchStatus()
    refetchCallRecords()
  }, [
    phase,
    incoming?.call_id,
    incoming?.startedAt,
    callStart,
    status?.current_call_id,
    status?.resource_state,
    status?.resource_updated_at,
    statusFetchedAtMs,
    ringtone,
    leg,
    mic,
    dispatch,
    refetchStatus,
    refetchCallRecords,
  ])

  // Missed cc.call_hangup / cc.outbound_hangup: poll shows this agent's call
  // resource is already free, so the call is over and the desk must not stay
  // on 通话中 until someone clicks hang up.
  useEffect(() => {
    if (
      !shouldLeaveOnCallFromPoll({
        phase,
        callStart: callStart ?? incoming?.startedAt,
        sessionStartedAt: incoming?.startedAt,
        resourceState: status?.resource_state,
        resourceUpdatedAtMs: callStartMsFromIso(status?.resource_updated_at),
        statusFetchedAtMs,
      })
    ) {
      return
    }
    const callId = incoming?.call_id
    if (!callId) return
    trackCallCenter(
      'poll_reconcile',
      {
        kind: 'on_call_released',
        call_id: callId,
        resource_state: status?.resource_state,
      },
      'warn',
    )
    endingCallRef.current = true
    leg.goOffline()
    mic.stop()
    dispatch({ type: 'SOCKET_HANGUP', callId, matches: true })
    refetchCallRecords()
  }, [
    phase,
    incoming?.call_id,
    incoming?.startedAt,
    callStart,
    status?.resource_state,
    status?.resource_updated_at,
    statusFetchedAtMs,
    leg,
    mic,
    dispatch,
    refetchCallRecords,
  ])

  // The backstops above only cover the mismatches we anticipated. When the
  // server and the desk simply disagree about which call is active, report it
  // so an unforeseen combination still leaves a trace to diagnose.
  useEffect(() => {
    if (phase !== 'incoming' && phase !== 'outbound_ringing' && phase !== 'on_call') {
      return
    }
    const localCallId = incoming?.call_id
    const currentCallId = status?.current_call_id
    if (!localCallId || !currentCallId) return
    if (currentCallId === localCallId || currentCallId === incoming?.source_call_id) {
      return
    }
    // A snapshot taken before this call started proves nothing.
    const resourceUpdatedAtMs = callStartMsFromIso(status?.resource_updated_at)
    const startedAt = callStart ?? incoming?.startedAt ?? null
    if (resourceUpdatedAtMs == null || startedAt == null) return
    if (resourceUpdatedAtMs < startedAt) return
    const key = `${phase}:${localCallId}:${currentCallId}:${status?.resource_state ?? ''}`
    if (reportedDriftRef.current.has(key)) return
    reportedDriftRef.current.add(key)
    trackCallCenter(
      'state_drift',
      {
        phase,
        call_id: localCallId,
        source_call_id: incoming?.source_call_id,
        current_call_id: currentCallId,
        resource_state: status?.resource_state,
        agent_status: status?.status,
      },
      'warn',
    )
  }, [
    phase,
    incoming?.call_id,
    incoming?.source_call_id,
    incoming?.startedAt,
    callStart,
    status?.current_call_id,
    status?.resource_state,
    status?.resource_updated_at,
    status?.status,
  ])

  // After restore/hydrate, CDR list may arrive a tick later — pull the real
  // answered_at so the live timer continues instead of restarting at 00:00.
  // If hydrate showed 来电 before CDR loaded, upgrade once answered_at is known.
  useEffect(() => {
    if (phase !== 'on_call' && phase !== 'outbound_ringing' && phase !== 'incoming') {
      return
    }
    const callId = incoming?.call_id
    if (!callId) return
    const rec =
      (records?.items ?? []).find((r) => r.call_id === callId) ??
      (incoming?.source_call_id
        ? (records?.items ?? []).find((r) => r.call_id === incoming.source_call_id)
        : undefined)
    if (phase === 'incoming') {
      // Only upgrade when *this* agent answered — a transferred call keeps the
      // prior agent's answered_at on the same call_id.
      if (!callRecordAnsweredByAgent(rec, status?.employee_id)) return
      ringtone.stop()
      dispatch({
        type: 'CDR_ANSWERED',
        callStart: callStartMsFromRecord(rec),
      })
      return
    }
    if (phase === 'outbound_ringing') {
      // An outbound CDR carries started_at from creation (the dial time), so
      // its presence is not answer evidence — only a connected customer is.
      // cc.outbound_answered owns the normal transition; this is the backstop
      // for a missed socket event.
      if (!callRecordCustomerConnected(rec)) return
      ringtone.stop()
      dispatch({ type: 'CDR_ANSWERED', callStart: callStartMsFromRecord(rec) })
      return
    }
    const startMs =
      callStartMsFromRecord(rec) ?? callStartMsFromIso(status?.in_call_since)
    if (startMs == null) return
    if (callStart != null && startMs >= callStart) return
    dispatch({ type: 'CDR_ANSWERED', callStart: startMs })
  }, [
    phase,
    incoming?.call_id,
    incoming?.source_call_id,
    records,
    callStart,
    ringtone.stop,
    status?.employee_id,
    status?.in_call_since,
    dispatch,
  ])

  useEffect(() => {
    if (!socket || !controlEnabled) return
    // Fresh socket after refresh — pull latest resource state promptly.
    void refetchStatus()
    // Events emitted while the connection was down are lost for good, and a
    // reconnect reuses the same socket instance so this effect would not run
    // again on its own. Re-sync on every reconnect, otherwise the desk keeps
    // whatever phase it was in when the events went missing.
    const onReconnect = () => {
      trackCallCenter(
        'socket_reconnected',
        { phase: sessionRef.current.phase, call_id: sessionRef.current.incoming?.call_id },
        'warn',
      )
      void refetchStatus()
      refetchCallRecords()
    }
    socket.on('connect', onReconnect)
    return () => {
      socket.off('connect', onReconnect)
    }
  }, [socket, refetchStatus, refetchCallRecords, controlEnabled])

  // Session state is the source of truth for audible call progress. Events and
  // polling can race during a fast outbound answer, so entering an established
  // or terminal phase must always silence any ringback started by an earlier
  // transition.
  useEffect(() => {
    if (phase !== 'incoming' && phase !== 'outbound_ringing') {
      ringtone.stop()
    }
    if (!shouldKeepAutoAnswerChime(phase)) {
      autoAnswerChime.stop()
    }
  }, [phase, ringtone, autoAnswerChime])

  useEffect(() => {
    if (!socket || !controlEnabled) return

    // Records that a call-lifecycle event actually reached this browser, plus
    // the phase it landed in. Without this, a lost event and an event that was
    // received but filtered out look identical in the logs.
    const trackSocket = (
      event: string,
      callId?: string | null,
      extra: Record<string, string | number | boolean | null | undefined> = {},
    ) => {
      trackCallCenter('socket_event', {
        event,
        call_id: callId,
        phase: sessionRef.current.phase,
        session_call_id: sessionRef.current.incoming?.call_id,
        session_source_call_id: sessionRef.current.incoming?.source_call_id,
        ...extra,
      })
    }

    const onIncoming = (data: {
      offer_id: string
      call_id: string
      from: string
      to: string
      queue_id: number | null
      call_type?: string
      device_type?: string
      direction?: 'inbound' | 'outbound'
      source_call_id?: string
      customer_from?: string
      customer_to?: string
      user_id?: number
      user_public_id?: string
      restore?: boolean
      answered_at?: string
      source?: string
      task_id?: number
      record_id?: number
    }) => {
      const rec =
        (records?.items ?? []).find((r) => r.call_id === data.call_id) ??
        (data.source_call_id
          ? (records?.items ?? []).find((r) => r.call_id === data.source_call_id)
          : undefined)
      const restoredStart = data.restore
        ? callStartMsFromIso(data.answered_at) ??
          // Still-ringing restore: anchor the ring timer to when this agent's
          // resource entered ringing — the CDR started_at is the customer's
          // dial time and would count queue wait; Date.now() would reset it.
          (status?.resource_state === 'ringing'
            ? callStartMsFromIso(status.resource_updated_at)
            : null) ??
          callStartMsFromRecord(rec) ??
          callStartMsFromIso(status?.in_call_since)
        : null
      const startMs = restoredStart ?? Date.now()
      // Queue blind-transfer reuses the customer's call_id (already answered by
      // the prior agent). Only this agent's own CDR counts as alreadyAnswered.
      const alreadyAnswered = callRecordAnsweredByAgent(
        rec,
        status?.employee_id,
      )
      const recentlyEnded = isRecentlyEndedIncoming(
        sessionRef.current.lastEndedCallIds,
        data,
      )
      trackSocket('call_incoming', data.call_id, {
        matched: !recentlyEnded,
        skip_reason: recentlyEnded ? 'recently_ended' : undefined,
        direction: data.direction,
        restore: data.restore,
        already_answered: alreadyAnswered,
        source: data.source,
      })
      if (recentlyEnded) {
        return
      }
      setSelectedRecordId(null)
      const wasOnCall = sessionRef.current.phase === 'on_call'
      const autoAccept = shouldAutoAcceptAutoOutbound({
        source: data.source,
        deviceType: data.device_type,
        restore: data.restore,
        alreadyAnswered,
      })
      dispatch({
        type: 'SOCKET_INCOMING',
        restore: data.restore,
        alreadyAnswered,
        callStart: restoredStart ?? startMs,
        incoming: {
          offer_id: data.offer_id,
          call_id: data.call_id,
          from: data.from || '',
          to: data.to || '',
          queue_id: data.queue_id ?? null,
          call_type: data.call_type,
          device_type: data.device_type,
          direction: data.direction,
          source_call_id: data.source_call_id,
          customer_from: data.customer_from,
          customer_to: data.customer_to,
          user_id: data.user_id,
          user_public_id: data.user_public_id,
          startedAt: startMs,
          ...restoredAutoOutboundContext(data),
        },
      })
      // Auto-outbound Web phone: no ringtone / no manual answer UX.
      if (data.restore || alreadyAnswered || wasOnCall || autoAccept) {
        ringtone.stop()
      } else {
        ringtone.start()
      }
      refetchCallRecords()
    }

    // SIP-phone inbound: the call is answered on the physical handset, so the
    // backend tells the browser to move to 通话中 (no browser "接听" click).
    // Also used after page-refresh restore (server emits incoming then answered).
    const onCallAnswered = (data: { call_id: string }) => {
      trackSocket('call_answered', data?.call_id)
      ringtone.stop()
      dispatch({ type: 'SOCKET_ANSWERED' })
    }

    // SIP-phone registration went up/down (kernel event or reconnect reconcile)
    // — refresh the device list so the heartbeat dot updates live, not on the
    // 15s poll.
    const onDeviceRegistrationChanged = () => {
      void queryClient.invalidateQueries({ queryKey: agentDeviceKeys.list() })
    }

    const onRemoteIce = (data: { call_id: string; candidate: RTCIceCandidateInit }) => {
      void leg.applyRemoteIce(data.candidate)
    }

    const onHangup = (data: { call_id: string; reason?: string }) => {
      const matches = hangupMatches({
        hangupCallId: data?.call_id,
        activeLegId: leg.callId,
        businessCallId: sessionRef.current.incoming?.call_id,
        sourceCallId: sessionRef.current.incoming?.source_call_id,
      })
      trackSocket('call_hangup', data?.call_id, {
        matched: matches,
        reason: data?.reason,
        active_leg_id: leg.callId,
      })
      if (!matches) return
      endingCallRef.current = true
      ringtone.stop()
      leg.goOffline()
      // Release the permission-probe mic stream too, or the browser mic
      // indicator stays on after the call ends.
      mic.stop()
      dispatch({
        type: 'SOCKET_HANGUP',
        callId: data.call_id,
        matches: true,
      })
      void refetchStatus()
      refetchCallRecords()
    }

    const onOutboundRinging = (data: { call_id: string }) => {
      trackSocket('outbound_ringing', data?.call_id)
      refetchCallRecords()
    }

    const onOutboundAnswered = (data: { call_id: string }) => {
      const incoming = sessionRef.current.incoming
      const matchesActiveOutbound =
        sessionRef.current.phase === 'outbound_ringing' &&
        (incoming?.call_id === data.call_id ||
          incoming?.source_call_id === data.call_id)
      trackSocket('outbound_answered', data.call_id, {
        matched: matchesActiveOutbound,
      })
      if (!matchesActiveOutbound) {
        earlyOutboundAnsweredRef.current.add(data.call_id)
        return
      }
      ringtone.stop()
      dispatch({ type: 'SOCKET_OUTBOUND_ANSWERED' })
      refetchCallRecords()
    }

    const onOutboundHangup = (data: {
      call_id: string
      reason?: string
      sip_status?: number
    }) => {
      const incoming = sessionRef.current.incoming
      const matchesActiveOutbound =
        sessionRef.current.phase === 'outbound_ringing' &&
        (incoming?.call_id === data.call_id ||
          incoming?.source_call_id === data.call_id)
      const forOtherCall =
        !!incoming &&
        incoming.call_id !== data.call_id &&
        incoming.source_call_id !== data.call_id
      trackSocket('outbound_hangup', data.call_id, {
        matched: matchesActiveOutbound,
        other_call: forOtherCall,
        reason: data.reason,
        sip_status: data.sip_status,
      })
      // An earlier call ending late (e.g. after its satisfaction survey) must
      // not toast over, or tear down the media of, the call on the desk now.
      if (forOtherCall) {
        refetchCallRecords()
        return
      }
      if (!matchesActiveOutbound) {
        earlyOutboundEndedRef.current.add(data.call_id)
      }
      earlyOutboundAnsweredRef.current.delete(data.call_id)
      endingCallRef.current = true
      ringtone.stop()
      leg.goOffline()
      // Release the permission-probe mic stream too, or the browser mic
      // indicator stays on after the call ends.
      mic.stop()
      const failure = mapOutboundFailure({
        reason: data.reason,
        sip_status: data.sip_status,
      })
      // Always toast failures — hangup can beat outbound_ringing when the
      // carrier rejects in <50ms (phase still idle). Dedup against dial-webrtc.
      const toastKey = `${data.call_id}:${data.reason ?? ''}:${data.sip_status ?? ''}`
      if (failure.message && lastOutboundFailToastRef.current !== toastKey) {
        lastOutboundFailToastRef.current = toastKey
        if (failure.level === 'info') toast(failure.message)
        else toast.error(failure.message)
      }
      dispatch({ type: 'SOCKET_OUTBOUND_HANGUP', callId: data.call_id })
      void refetchStatus()
      refetchCallRecords()
    }

    // Result of a browser-ring consult to a Web-phone colleague. Drives the
    // initiator's UI out of "咨询呼叫中": active on accept, or back to the
    // single-customer call (with a toast) on decline / no-answer / error.
    const onConsultResult = (data: {
      ok: boolean
      reason?: string
      target_name?: string
      ended?: boolean
      resumed?: boolean
    }) => {
      handleConsultResult(data)
    }

    const onMediaReconnectRequired = (data: {
      customer_call_id?: string
      reason?: string
    }) => {
      trackSocket('media_reconnect_required', data?.customer_call_id, {
        reason: data?.reason,
      })
      // SIP desk-phone media lives on the handset — a browser WebRTC rebuild
      // would steal the customer bridge and leave the mobile silent.
      if (
        !browserOwnsMedia(sessionRef.current.incoming?.device_type) ||
        !browserOwnsMedia(currentDevice?.device_type)
      ) {
        return
      }
      if (endingCallRef.current || sessionRef.current.phase !== 'on_call') return
      if (mediaReconnectInFlightRef.current) return
      mediaReconnectInFlightRef.current = true
      void (async () => {
        try {
          if (endingCallRef.current || sessionRef.current.phase !== 'on_call') return
          if (mic.state !== 'granted') {
            const ok = await mic.request()
            if (!ok) {
              toast.error('请先授权麦克风以恢复通话')
              return
            }
          }
          const newCallId = await leg.reconnectMedia()
          if (newCallId === 'ended') return
          if (newCallId) {
            dispatch({ type: 'MEDIA_LEG_UPDATED', callId: newCallId })
            dispatch({ type: 'FORCE_ON_CALL' })
            void refetchStatus()
            toast.success('已恢复通话媒体')
          } else {
            toast.error('恢复客户通话失败，请刷新页面后重试')
          }
        } finally {
          mediaReconnectInFlightRef.current = false
        }
      })()
    }

    // Transfer outcome. On success the customer is handed over — leave the call
    // UI immediately (do not wait for a possibly-missing media hangup event).
    const onTransferResult = (data: { ok: boolean; reason?: string }) => {
      const ok = handleTransferResult(data)
      if (!ok) return
      endingCallRef.current = true
      ringtone.stop()
      leg.goOffline()
      dispatch({ type: 'USER_TRANSFER_ENDED' })
      void refetchStatus()
      refetchCallRecords()
    }

    // A ringing conference participant answered (→ live) or failed to connect.
    const onConferenceResult = (data: { ok: boolean; reason?: string }) => {
      handleConferenceResult(data)
    }

    // The added participant left/hung up → collapse the 3-way to the 1:1 call.
    const onConferenceParticipantLeft = () => {
      handleConferenceParticipantLeft()
    }

    // Server entered this agent into after-call work and pushed the deadline
    // with the event — start the countdown now, not on the next status poll.
    // The event can arrive while the phase is still on_call (the server writes
    // the deadline before notifying the hangup), so accept both phases.
    const onWrapUpStarted = (data: { call_id?: string; wrap_up_until?: string }) => {
      const ms = data?.wrap_up_until ? Date.parse(data.wrap_up_until) : NaN
      trackSocket('wrap_up_started', data?.call_id, {
        has_deadline: Number.isFinite(ms),
      })
      if (!Number.isFinite(ms)) return
      const current = sessionRef.current
      if (current.phase !== 'on_call' && current.phase !== 'wrap_up') return
      if (data?.call_id && current.incoming?.call_id && data.call_id !== current.incoming.call_id) {
        return
      }
      setWrapUpUntilLocal(ms)
    }

    // Server-side wrap-up sweep flipped the agent ready — leave the wrap-up
    // panel immediately instead of waiting for the next status poll.
    const onWrapUpTimeout = () => {
      trackSocket('wrap_up_timeout')
      if (sessionRef.current.phase !== 'wrap_up') return
      dispatch({ type: 'USER_STATUS_ENDS_WRAP_UP' })
      void refetchStatus()
      refetchCallRecords()
    }

    const onCallRecordUpdated = () => {
      refetchCallRecords()
    }

    socket.on(CcSocketEvent.CALL_INCOMING, onIncoming)
    socket.on(CcSocketEvent.CALL_ANSWERED, onCallAnswered)
    socket.on(CcSocketEvent.DEVICE_REGISTRATION_CHANGED, onDeviceRegistrationChanged)
    socket.on(CcSocketEvent.WEBRTC_ICE, onRemoteIce)
    socket.on(CcSocketEvent.CALL_HANGUP, onHangup)
    socket.on(CcSocketEvent.OUTBOUND_RINGING, onOutboundRinging)
    socket.on(CcSocketEvent.OUTBOUND_ANSWERED, onOutboundAnswered)
    socket.on(CcSocketEvent.OUTBOUND_HANGUP, onOutboundHangup)
    socket.on(CcSocketEvent.CONSULT_RESULT, onConsultResult)
    socket.on(CcSocketEvent.MEDIA_RECONNECT_REQUIRED, onMediaReconnectRequired)
    socket.on(CcSocketEvent.TRANSFER_RESULT, onTransferResult)
    socket.on(CcSocketEvent.CONFERENCE_RESULT, onConferenceResult)
    socket.on(CcSocketEvent.CONFERENCE_PARTICIPANT_LEFT, onConferenceParticipantLeft)
    socket.on(CcSocketEvent.WRAP_UP_STARTED, onWrapUpStarted)
    socket.on(CcSocketEvent.WRAP_UP_TIMEOUT, onWrapUpTimeout)
    socket.on(CcSocketEvent.CALL_RECORD_UPDATED, onCallRecordUpdated)
    return () => {
      socket.off(CcSocketEvent.CALL_INCOMING, onIncoming)
      socket.off(CcSocketEvent.CALL_ANSWERED, onCallAnswered)
      socket.off(CcSocketEvent.DEVICE_REGISTRATION_CHANGED, onDeviceRegistrationChanged)
      socket.off(CcSocketEvent.WEBRTC_ICE, onRemoteIce)
      socket.off(CcSocketEvent.CALL_HANGUP, onHangup)
      socket.off(CcSocketEvent.OUTBOUND_RINGING, onOutboundRinging)
      socket.off(CcSocketEvent.OUTBOUND_ANSWERED, onOutboundAnswered)
      socket.off(CcSocketEvent.OUTBOUND_HANGUP, onOutboundHangup)
      socket.off(CcSocketEvent.CONSULT_RESULT, onConsultResult)
      socket.off(CcSocketEvent.MEDIA_RECONNECT_REQUIRED, onMediaReconnectRequired)
      socket.off(CcSocketEvent.TRANSFER_RESULT, onTransferResult)
      socket.off(CcSocketEvent.CONFERENCE_RESULT, onConferenceResult)
      socket.off(CcSocketEvent.CONFERENCE_PARTICIPANT_LEFT, onConferenceParticipantLeft)
      socket.off(CcSocketEvent.WRAP_UP_STARTED, onWrapUpStarted)
      socket.off(CcSocketEvent.WRAP_UP_TIMEOUT, onWrapUpTimeout)
      socket.off(CcSocketEvent.CALL_RECORD_UPDATED, onCallRecordUpdated)
    }
  }, [
    socket,
    leg,
    currentDevice?.device_type,
    mic,
    ringtone,
    handleConsultResult,
    handleTransferResult,
    handleConferenceResult,
    handleConferenceParticipantLeft,
    refetchCallRecords,
    refetchStatus,
    queryClient,
    dispatch,
    status?.employee_id,
    status?.in_call_since,
    records,
    controlEnabled,
  ])

  useEffect(() => {
    if (phase !== 'on_call') endingCallRef.current = false
  }, [phase])

  // Page refresh / socket republish leaves phase=on_call with no live PC —
  // rebuild media against the still-active customer leg.
  // SIP desk-phone media lives on the handset — never create a browser leg.
  useEffect(() => {
    if (!controlEnabled) return
    if (
      !shouldHydrateMediaReconnect({
        phase,
        legState: leg.state,
        endingCall: endingCallRef.current,
        originating: originatingRef.current,
        browserOwnsMedia:
          browserOwnsMedia(incoming?.device_type) &&
          browserOwnsMedia(currentDevice?.device_type),
      })
    ) {
      return
    }
    if (mediaReconnectInFlightRef.current) return
    mediaReconnectInFlightRef.current = true
    void (async () => {
      try {
        if (
          endingCallRef.current ||
          originatingRef.current ||
          sessionRef.current.phase !== 'on_call'
        ) {
          return
        }
        if (mic.state !== 'granted') {
          const ok = await mic.request()
          if (!ok) return
        }
        if (
          endingCallRef.current ||
          originatingRef.current ||
          sessionRef.current.phase !== 'on_call'
        ) {
          return
        }
        const newCallId = await leg.reconnectMedia()
        if (newCallId === 'ended') return
        if (newCallId) {
          // Keep hangup matching in sync when consult-target rebuilds a new leg.
          dispatch({ type: 'MEDIA_LEG_UPDATED', callId: newCallId })
          void refetchStatus()
          toast.success('已恢复通话媒体')
        } else {
          toast.error('恢复通话媒体失败，可点「重置通话状态」清理')
        }
      } finally {
        mediaReconnectInFlightRef.current = false
      }
    })()
  }, [
    phase,
    leg.state,
    leg.reconnectMedia,
    incoming?.device_type,
    currentDevice?.device_type,
    mic,
    refetchStatus,
    dispatch,
    controlEnabled,
  ])

  useEffect(() => {
    if (leg.state !== 'failed') return
    closeSession.mutate(undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leg.state])

  // Any in-call control state (hold/consult/conference/mute) only makes sense
  // during an active call; clear it once the call leaves the on_call phase.
  // While on_call, restore consult_active from Redis InCallLegs after refresh
  // (SIP keeps the handset consult; Web rebuilds media then hydrates UI).
  // If a restored consult is not confirmed by the server, drop the false
  // 「结束咨询」button — never interrupt a local consult_ringing the agent started.
  useEffect(() => {
    if (phase !== 'on_call') {
      callControl.reset()
      consultUiRestoredRef.current = false
      return
    }
    if (status?.consult_active) {
      if (consultUiRestoredRef.current) return
      consultUiRestoredRef.current = true
      callControl.restoreConsult({
        target_id: status.consult_target_employee_id ?? undefined,
        state: status.consult_state === 'ringing' ? 'ringing' : 'active',
      })
      return
    }
    if (
      consultUiRestoredRef.current &&
      (callControl.mode === 'consult_active' || callControl.mode === 'consult_ringing')
    ) {
      consultUiRestoredRef.current = false
      callControl.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    phase,
    status?.consult_active,
    status?.consult_state,
    status?.consult_target_employee_id,
    callControl.mode,
  ])

  // Sync transfer (non-WebRTC ring) sets callControl.mode to "ended" without a
  // socket event — advance the workspace phase the same way as transfer_result.
  useEffect(() => {
    if (phase !== 'on_call') return
    if (callControl.mode !== 'ended') return
    endingCallRef.current = true
    ringtone.stop()
    leg.goOffline()
    mic.stop()
    dispatch({ type: 'USER_TRANSFER_ENDED' })
    refetchCallRecords()
    void refetchStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [callControl.mode, phase, dispatch])

  useEffect(() => {
    if (leg.state === 'failed') {
      toast.error(
        `通话服务连接失败${leg.error ? `：${formatWebRtcDeviceError(leg.error)}` : ''}`,
      )
    }
  }, [leg.state, leg.error])

  const setAgentStatus = useCallback(async (newStatus: AgentStatus) => {
    if (!controlEnabled) return
    const currentPhase = sessionRef.current.phase
    if (
      currentPhase === 'incoming' ||
      currentPhase === 'outbound_ringing' ||
      currentPhase === 'on_call'
    ) {
      return
    }
    if (newStatus === 'offline' && (leg.state === 'ready' || leg.state === 'connecting')) {
      leg.goOffline()
    }
    try {
      await setStatusMutation.mutateAsync({ status: newStatus })
      // Manually choosing a status ends the post-call wrap-up, so the status
      // pill (which is pinned to "整理中"/after_call_work while phase === 'wrap_up')
      // and the wrap-up panel reflect the new status immediately instead of
      // staying on "整理中" until the page is refreshed.
      if (sessionRef.current.phase === 'wrap_up') {
        dispatch({ type: 'USER_STATUS_ENDS_WRAP_UP' })
        refetchCallRecords()
      }
      if (newStatus === 'ready') toast.success('已就绪 — 等待来电')
      else if (newStatus === 'offline') toast.success('已离线')
    } catch {
      toast.error('状态切换失败')
    }
  }, [leg, setStatusMutation, refetchCallRecords, dispatch, controlEnabled])

  const accept = useCallback(async (): Promise<boolean> => {
    if (!controlEnabled) return false
    const current = sessionRef.current.incoming
    if (!current) return false
    // SIP-phone calls are answered on the physical handset; there is no browser
    // WebRTC leg to accept. The backend's cc.call_answered moves us to 通话中.
    if (!browserOwnsMedia(current.device_type)) return false
    if (acceptingOfferRef.current === current.offer_id) return false
    acceptingOfferRef.current = current.offer_id
    ringtone.stop()
    if (mic.state !== 'granted') {
      const ok = await mic.request()
      if (!ok) {
        acceptingOfferRef.current = null
        toast.error('请先授权麦克风')
        return false
      }
    }
    const ok = await leg.acceptOffer(current.offer_id)
    if (!ok) acceptingOfferRef.current = null
    if (ok) {
      trackCallCenter('action', {
        action: 'accept',
        stage: 'succeeded',
        call_id: current.call_id,
      })
      dispatch({ type: 'USER_ACCEPT_OK', callStart: Date.now() })
      return true
    }
    // Another tab can win the server-side accept lock and bridge the call
    // (offer_accept_in_progress / offer_expired). Losing that race must not
    // clear the call UI: resync the agent snapshot and let the poll-hydrate
    // effect restore on_call / wrap_up from the server. Toast only when the
    // server confirms the call is really gone.
    const { data: fresh } = await refetchStatus()
    const callSurvived =
      fresh?.resource_state === 'ringing' ||
      fresh?.resource_state === 'in_call' ||
      fresh?.status === 'after_call_work'
    trackCallCenter(
      'action',
      {
        action: 'accept',
        stage: 'failed',
        call_id: current.call_id,
        call_survived: callSurvived,
        resource_state: fresh?.resource_state,
        agent_status: fresh?.status,
      },
      'warn',
    )
    if (!callSurvived) {
      toast.error('接听失败，请稍后重试')
      dispatch({ type: 'USER_ACCEPT_FAIL' })
      return false
    }
    // Reset the failed leg to a reconnectable state so the on_call hydrate
    // rebuilds the media in this tab.
    leg.goOffline()
    dispatch({ type: 'USER_ACCEPT_FAIL' })
    return false
  }, [leg, mic, ringtone, dispatch, controlEnabled, refetchStatus])
  acceptRef.current = accept

  // Auto-outbound + Web phone: acceptOffer without showing manual answer UI.
  useEffect(() => {
    if (!controlEnabled || phase !== 'incoming' || !incoming?.offer_id) return
    if (
      !shouldAutoAcceptAutoOutbound({
        source: incoming.source,
        deviceType: incoming.device_type,
      })
    ) {
      return
    }
    const offerId = incoming.offer_id
    if (autoAcceptedOfferIdsRef.current.has(offerId)) return
    autoAcceptedOfferIdsRef.current.add(offerId)
    autoAnswerChime.play()
    void (async () => {
      const ok = await acceptRef.current()
      // Only a failed accept may retry on a later push of the same offer.
      // sessionRef.phase still reads pre-dispatch at this point, so it cannot
      // tell success from failure — use the returned flag instead.
      if (!ok) {
        autoAnswerChime.stop()
        autoAcceptedOfferIdsRef.current.delete(offerId)
      }
    })()
  }, [phase, incoming?.offer_id, incoming?.source, incoming?.device_type, controlEnabled, autoAnswerChime])

  // Track wrap-up start for auto-outbound countdown; open business-record tab.
  useEffect(() => {
    if (phase === 'wrap_up') {
      setWrapUpStartedAt((prev) => prev ?? Date.now())
      // Pull wrap_up_until promptly when the socket push is missed or races hangup.
      void refetchStatus()
      if (incoming?.source === 'auto_outbound' && incoming.task_id) {
        setCallSummaryTab('auto_outbound')
      } else if (incoming?.source === 'personal_auto_outbound' && incoming.record_id) {
        setCallSummaryTab('personal_auto_outbound')
      }
      return
    }
    if (phase === 'idle' || phase === 'mic_check' || phase === 'mic_denied') {
      setWrapUpStartedAt(null)
      setWrapUpUntilLocal(null)
    }
  }, [phase, incoming?.source, incoming?.task_id, incoming?.record_id, refetchStatus])

  // Wrap-up deadline reached: ask the server once — the sweep may already
  // have flipped the agent ready (the socket event is the fast path).
  useEffect(() => {
    if (phase !== 'wrap_up' || wrapUpUntilMs == null) return
    if (now < wrapUpUntilMs) return
    if (wrapUpExpiredFiredRef.current === wrapUpUntilMs) return
    wrapUpExpiredFiredRef.current = wrapUpUntilMs
    void refetchStatus()
  }, [phase, wrapUpUntilMs, now, refetchStatus])

  // Fallback exit: a poll written at/after the deadline that no longer shows
  // after_call_work means the server ended the wrap-up. The timestamp guard
  // rejects the pre-hangup busy snapshot racing in right after hangup.
  useEffect(() => {
    if (phase !== 'wrap_up') return
    if (wrapUpUntilMs == null) return
    if (!status || status.status === 'after_call_work') return
    const writtenMs = callStartMsFromIso(status.resource_updated_at)
    if (writtenMs == null || writtenMs < wrapUpUntilMs) return
    dispatch({ type: 'USER_STATUS_ENDS_WRAP_UP' })
    refetchCallRecords()
  }, [
    phase,
    status,
    wrapUpUntilMs,
    dispatch,
    refetchCallRecords,
  ])

  const reject = useCallback(async () => {
    if (!controlEnabled) return
    const current = sessionRef.current.incoming
    if (!current) return
    ringtone.stop()
    try {
      await rejectCurrentCall(current.offer_id)
      trackCallCenter('action', {
        action: 'reject',
        stage: 'succeeded',
        call_id: current.call_id,
      })
    } catch (error) {
      trackCallCenter(
        'action',
        {
          action: 'reject',
          stage: 'failed',
          call_id: current.call_id,
          error: error instanceof Error ? error.message.slice(0, 200) : 'unknown',
        },
        'error',
      )
      toast.error('拒接失败，请稍后重试')
    }
    dispatch({ type: 'USER_REJECT' })
    // Rejecting puts the agent on busy server-side; pull that in now instead of
    // leaving the sidebar claiming 就绪 until the next poll.
    void refetchStatus()
  }, [ringtone, refetchStatus, dispatch, controlEnabled])

  const hangup = useCallback(async () => {
    if (!controlEnabled) {
      trackCallCenter(
        'action',
        { action: 'hangup', stage: 'blocked', reason: 'control_disabled' },
        'warn',
      )
      return
    }
    ringtone.stop()
    const current = sessionRef.current.incoming
    const phaseNow = sessionRef.current.phase
    const isOutboundRinging =
      current?.direction === 'outbound' && phaseNow === 'outbound_ringing'
    const requestedAtMs = Date.now()
    trackCallCenter('action', {
      action: 'hangup',
      stage: 'requested',
      phase: phaseNow,
      call_id: current?.call_id,
      source_call_id: current?.source_call_id,
      outbound_ringing: isOutboundRinging,
    })
    endingCallRef.current = true
    if (phaseNow === 'on_call') {
      // Leave 通话中 immediately so hydrate cannot POST media-reconnect
      // against a CDR that hangupCurrentCall is about to close.
      leg.goOffline()
      mic.stop()
      dispatch({
        type: 'SOCKET_HANGUP',
        callId: current?.call_id ?? '',
        matches: true,
      })
      refetchCallRecords()
      void refetchStatus()
    }
    try {
      if (isOutboundRinging && current?.call_id) {
        await cancelOutboundCall(current.call_id)
      } else {
        const result = await hangupCurrentCall()
        if (result.note === 'satisfaction_started') {
          toast.success('人工服务已结束，客户已进入满意度调查')
        } else if (result.note === 'satisfaction_fallback_hangup') {
          toast.error('满意度调查启动失败，通话已正常结束')
        }
      }
      trackCallCenter('action', {
        action: 'hangup',
        stage: 'succeeded',
        call_id: current?.call_id,
        duration_ms: Date.now() - requestedAtMs,
      })
    } catch (error) {
      trackCallCenter(
        'action',
        {
          action: 'hangup',
          stage: 'failed',
          call_id: current?.call_id,
          duration_ms: Date.now() - requestedAtMs,
          error: error instanceof Error ? error.message.slice(0, 200) : 'unknown',
        },
        'error',
      )
      toast.error('挂断失败，请稍后重试')
    } finally {
      if (isOutboundRinging) {
        leg.goOffline()
        mic.stop()
        dispatch({ type: 'USER_OUTBOUND_FAIL' })
        refetchCallRecords()
      }
    }
  }, [leg, mic, refetchCallRecords, refetchStatus, ringtone, dispatch, controlEnabled])

  const completeWrapUp = useCallback(() => {
    if (!controlEnabled) return
    dispatch({ type: 'USER_WRAP_UP_DONE' })
    setStatusMutation.mutate(
      { status: 'ready' },
      { onSettled: () => void refetchStatus() },
    )
    refetchCallRecords()
  }, [refetchCallRecords, refetchStatus, setStatusMutation, dispatch, controlEnabled])

  const handleDialStarted = useCallback(async ({ callId, destination, outboundNumber }: DialStartedInfo) => {
    if (!controlEnabled) {
      trackCallCenter(
        'action',
        { action: 'dial', stage: 'blocked', reason: 'control_disabled', call_id: callId },
        'warn',
      )
      return
    }
    // The carrier already released the call before the dial response landed.
    if (earlyOutboundEndedRef.current.delete(callId)) {
      trackCallCenter('action', {
        action: 'dial',
        stage: 'ended_before_start',
        call_id: callId,
      })
      refetchCallRecords()
      return
    }
    trackCallCenter('action', {
      action: 'dial',
      stage: 'started',
      call_id: callId,
      device_type: currentDevice?.device_type,
      browser_media: browserOwnsMedia(currentDevice?.device_type),
    })
    setSelectedRecordId(null)
    const startedAt = Date.now()
    dispatch({
      type: 'USER_DIAL_STARTED',
      callStart: startedAt,
      incoming: {
        offer_id: '',
        call_id: callId,
        from: outboundNumber,
        to: destination,
        queue_id: null,
        startedAt,
        direction: 'outbound',
      },
    })
    const alreadyAnswered = earlyOutboundAnsweredRef.current.delete(callId)
    if (alreadyAnswered) {
      ringtone.stop()
      dispatch({ type: 'SOCKET_OUTBOUND_ANSWERED' })
    }
    refetchCallRecords()
    // A desk-phone outbound is dialled from the handset's own extension, so
    // there is no browser leg to originate. Going further would pop a pointless
    // microphone prompt and then report a WebRTC failure for a call that is
    // ringing perfectly well. No browser ringback either: the handset plays its
    // own, and hearing one here suggests the call lives in the browser — which
    // makes the audio then arriving on the handset look like a fault.
    if (!browserOwnsMedia(currentDevice?.device_type)) return
    if (!alreadyAnswered) ringtone.start()
    if (mic.state !== 'granted') {
      await mic.request()
    }
    originatingRef.current = true
    let failMessage: string | null
    try {
      failMessage = await leg.originateOffer(callId)
    } finally {
      originatingRef.current = false
    }
    const endedDuringOriginate = earlyOutboundEndedRef.current.delete(callId)
    if (failMessage || endedDuringOriginate || endingCallRef.current) {
      trackCallCenter(
        'action',
        {
          action: 'dial',
          stage: 'aborted',
          call_id: callId,
          webrtc_error: failMessage ?? undefined,
          ended_during_originate: endedDuringOriginate,
          ending: endingCallRef.current,
        },
        'warn',
      )
      ringtone.stop()
      leg.goOffline()
      mic.stop()
      if (failMessage) {
        const toastKey = `${callId}:webrtc:${failMessage}`
        if (lastOutboundFailToastRef.current !== toastKey) {
          // Prefer the socket toast key shape when message already shown.
          const alreadyToasted =
            lastOutboundFailToastRef.current?.startsWith(`${callId}:`) ?? false
          if (!alreadyToasted) {
            lastOutboundFailToastRef.current = toastKey
            toast.error(failMessage)
          }
        }
      }
      dispatch({ type: 'USER_OUTBOUND_FAIL' })
      return
    }
    trackCallCenter('action', {
      action: 'dial',
      stage: 'originated',
      call_id: callId,
    })
    void refetchStatus()
  }, [leg, mic, refetchCallRecords, refetchStatus, ringtone, dispatch, currentDevice?.device_type, controlEnabled])

  const screenPopNumber = selectedRecord
    ? callRecordCustomerNumber(selectedRecord) || ''
    : screenPopIncoming?.customer_from
      ? screenPopIncoming.customer_from
      : screenPopIncoming?.direction === 'outbound'
        ? screenPopIncoming.to || draftDialNumber.trim()
        : screenPopIncoming?.from || draftDialNumber.trim()
  const showEmptyCallState = !selectedRecord && !screenPopIncoming

  const value = useMemo<CallCenterRuntimeValue>(() => ({
    mic,
    leg,
    callControl: exposedCallControl,
    phase,
    incoming,
    callStart,
    screenPopIncoming,
    screenPopCallStart,
    now,
    status,
    records,
    recordsPage,
    setRecordsPage,
    selectedRecordId,
    setSelectedRecordId,
    draftDialNumber,
    setDraftDialNumber,
    draftOutboundNumber,
    setDraftOutboundNumber,
    callSummaryTab,
    setCallSummaryTab,
    selectedRecord,
    currentRecord,
    callSummaryRecordId,
    callRecordForTicket,
    screenPopNumber,
    showEmptyCallState,
    statusChangePending: setStatusMutation.isPending,
    wrapUpStartedAt,
    wrapUpUntil: wrapUpUntilMs,
    wrapUpRemainingMs,
    setAgentStatus,
    accept,
    reject,
    hangup,
    completeWrapUp,
    handleDialStarted,
  }), [
    mic,
    leg,
    exposedCallControl,
    phase,
    incoming,
    callStart,
    screenPopIncoming,
    screenPopCallStart,
    now,
    status,
    records,
    recordsPage,
    selectedRecordId,
    draftDialNumber,
    draftOutboundNumber,
    callSummaryTab,
    selectedRecord,
    currentRecord,
    callSummaryRecordId,
    callRecordForTicket,
    screenPopNumber,
    showEmptyCallState,
    wrapUpStartedAt,
    wrapUpUntilMs,
    wrapUpRemainingMs,
    setStatusMutation.isPending,
    setAgentStatus,
    accept,
    reject,
    hangup,
    completeWrapUp,
    handleDialStarted,
  ])

  return (
    <CallCenterRuntimeContext.Provider value={value}>
      {children}
    </CallCenterRuntimeContext.Provider>
  )
}

export function useCallCenterRuntime() {
  const ctx = useContext(CallCenterRuntimeContext)
  if (!ctx) {
    throw new Error('useCallCenterRuntime must be used within CallCenterProvider')
  }
  return ctx
}
