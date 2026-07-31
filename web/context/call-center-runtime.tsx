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
import { useWebRTCLeg } from '@/app/components/features/call-center/use-webrtc-leg'
import { useSocketStore } from '@/context/socket-store'
import {
  cancelOutboundCall,
  hangupCurrentCall,
  rejectCurrentCall,
  useCallRecords,
  useCloseWebRTCSession,
  useMyAgentStatus,
  useSetAgentStatus,
} from '@/service/use-call-center'
import type {
  AgentStatus,
  AgentStatusResponse,
  CallRecordListItem,
  CallRecordListResponse,
} from '@/models/call-center'
import { CcSocketEvent } from '@/lib/call-center-events'
import { callRecordAnsweredByAgent } from '@/lib/call-record-ownership'
import {
  callSessionReducer,
  canPollHydrate,
  hangupMatches,
  initialCallSession,
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

/** Prefer answered_at (talk clock) then started_at so a refresh continues the timer. */
function callStartMsFromRecord(rec?: {
  answered_at?: string | null
  started_at?: string | null
} | null): number | null {
  return callStartMsFromIso(rec?.answered_at || rec?.started_at)
}

type CallCenterRuntimeValue = {
  mic: ReturnType<typeof useMicrophone>
  leg: ReturnType<typeof useWebRTCLeg>
  callControl: CallControlApi
  phase: CallCenterPhase
  incoming: IncomingCall | null
  callStart: number | null
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
  callSummaryTab: 'summary' | 'ticket'
  setCallSummaryTab: (tab: 'summary' | 'ticket') => void
  selectedRecord: CallRecordListItem | null
  currentRecord: CallRecordListItem | null
  callSummaryRecordId: number | null
  callRecordForTicket: CallRecordListItem | null
  screenPopNumber: string
  showEmptyCallState: boolean
  statusChangePending: boolean
  setAgentStatus: (status: AgentStatus) => Promise<void>
  accept: () => Promise<void>
  reject: () => Promise<void>
  hangup: () => Promise<void>
  completeWrapUp: () => void
  handleDialStarted: (info: DialStartedInfo) => Promise<void>
}

const CallCenterRuntimeContext = createContext<CallCenterRuntimeValue | null>(null)

type CallCenterProviderProps = {
  children: ReactNode
  recordsEnabled?: boolean
}

export function CallCenterProvider({
  children,
  recordsEnabled = true,
}: CallCenterProviderProps) {
  const mic = useMicrophone({ autoRequestOnGranted: false })
  const { data: status, refetch: refetchStatus } = useMyAgentStatus()
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
  const ringtone = useRingtone()
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
  }, [recordsEnabled, refetchRecords])

  const [session, dispatchRaw] = useReducer(callSessionReducer, initialCallSession)
  const { phase, incoming, callStart } = session
  const [now, setNow] = useState<number>(Date.now())
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null)
  const [draftDialNumber, setDraftDialNumber] = useState('')
  const [draftOutboundNumber, setDraftOutboundNumber] = useState('')
  const [callSummaryTab, setCallSummaryTab] = useState<'summary' | 'ticket'>('summary')
  // Dedup socket hangup toast vs dial-webrtc 410 toast for the same failure.
  const lastOutboundFailToastRef = useRef<string | null>(null)
  // Prevent overlapping media-reconnect attempts after refresh / consult end.
  const mediaReconnectInFlightRef = useRef(false)
  // Restore 结束咨询 UI at most once per on_call session from server state.
  const consultUiRestoredRef = useRef(false)
  const sessionRef = useRef(session)
  sessionRef.current = session

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
    dispatchRaw(event)
  }, [])

  const selectedRecord =
    selectedRecordId != null
      ? (records?.items ?? []).find((r) => r.id === selectedRecordId) ?? null
      : null
  const currentRecord =
    incoming?.call_id
      ? (records?.items ?? []).find((r) => r.call_id === incoming.call_id) ?? null
      : null
  const callSummaryRecordId = selectedRecord?.id ?? currentRecord?.id ?? null
  const callRecordForTicket = selectedRecord ?? currentRecord

  useEffect(() => {
    setCallSummaryTab('summary')
  }, [callSummaryRecordId])

  useEffect(() => {
    if (phase !== 'on_call' && phase !== 'incoming' && phase !== 'outbound_ringing') return
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
    const callId = status.current_call_id
    if (!callId) return
    const rec = (records?.items ?? []).find((r) => r.call_id === callId)
    const deviceType = currentDevice?.device_type || undefined
    // Consult targets have no CDR — fall back to Redis in_call_since.
    const startMs =
      callStartMsFromRecord(rec) ??
      callStartMsFromIso(status.in_call_since) ??
      Date.now()
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
          from: rec?.from_number || '',
          to: rec?.to_number || '',
          queue_id: status.queue_id ?? null,
          direction: status.direction ?? 'inbound',
          device_type: deviceType,
          startedAt: startMs,
        },
      })
      ringtone.start()
      refetchCallRecords()
      return
    }
    // in_call, answered-but-still-ringing Redis, or busy+current_call_id when
    // Redis resource drifted mid-consult (SIP desk-phone after refresh).
    if (
      status.resource_state === 'in_call' ||
      ringingButAnswered ||
      (status.status === 'busy' && !!status.current_call_id)
    ) {
      setSelectedRecordId(null)
      dispatch({
        type: 'POLL_HYDRATE',
        phase: 'on_call',
        callStart: startMs,
        incoming: {
          offer_id: status.offer_id || '',
          call_id: callId,
          from: rec?.from_number || '',
          to: rec?.to_number || '',
          queue_id: status.queue_id ?? null,
          direction: status.direction ?? 'inbound',
          device_type: deviceType,
          startedAt: startMs,
        },
      })
      refetchCallRecords()
    }
  }, [status, phase, records, ringtone, refetchCallRecords, currentDevice?.device_type, dispatch])

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
    const startMs =
      callStartMsFromRecord(rec) ?? callStartMsFromIso(status?.in_call_since)
    if (startMs == null) return
    dispatch({ type: 'CDR_ANSWERED', callStart: startMs })
  }, [
    phase,
    incoming?.call_id,
    incoming?.source_call_id,
    records,
    ringtone,
    status?.employee_id,
    status?.in_call_since,
    dispatch,
  ])

  useEffect(() => {
    if (!socket) return
    // Fresh socket after refresh — pull latest resource state promptly.
    void refetchStatus()
  }, [socket, refetchStatus])

  useEffect(() => {
    if (!socket) return

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
    }) => {
      const rec =
        (records?.items ?? []).find((r) => r.call_id === data.call_id) ??
        (data.source_call_id
          ? (records?.items ?? []).find((r) => r.call_id === data.source_call_id)
          : undefined)
      const restoredStart = data.restore
        ? callStartMsFromIso(data.answered_at) ??
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
      setSelectedRecordId(null)
      const wasOnCall = sessionRef.current.phase === 'on_call'
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
        },
      })
      if (data.restore || alreadyAnswered || wasOnCall) {
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
      void data
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
      if (!matches) return
      ringtone.stop()
      leg.goOffline()
      dispatch({
        type: 'SOCKET_HANGUP',
        callId: data.call_id,
        matches: true,
      })
      void refetchStatus()
      refetchCallRecords()
    }

    const onOutboundRinging = (data: { call_id: string }) => {
      void data
      refetchCallRecords()
    }

    const onOutboundAnswered = (data: { call_id: string }) => {
      void data
      ringtone.stop()
      dispatch({ type: 'SOCKET_OUTBOUND_ANSWERED' })
      refetchCallRecords()
    }

    const onOutboundHangup = (data: {
      call_id: string
      reason?: string
      sip_status?: number
    }) => {
      ringtone.stop()
      leg.goOffline()
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
      void data
      // SIP desk-phone media lives on the handset — a browser WebRTC rebuild
      // would steal the customer bridge and leave the mobile silent.
      if (
        !browserOwnsMedia(sessionRef.current.incoming?.device_type) ||
        !browserOwnsMedia(currentDevice?.device_type)
      ) {
        return
      }
      if (mediaReconnectInFlightRef.current) return
      mediaReconnectInFlightRef.current = true
      void (async () => {
        try {
          if (mic.state !== 'granted') {
            const ok = await mic.request()
            if (!ok) {
              toast.error('请先授权麦克风以恢复通话')
              return
            }
          }
          const newCallId = await leg.reconnectMedia()
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
  ])

  // Page refresh / socket republish leaves phase=on_call with no live PC —
  // rebuild media against the still-active customer leg.
  // SIP desk-phone media lives on the handset — never create a browser leg.
  useEffect(() => {
    if (phase !== 'on_call') return
    if (
      !browserOwnsMedia(incoming?.device_type) ||
      !browserOwnsMedia(currentDevice?.device_type)
    ) {
      return
    }
    if (leg.state !== 'idle' && leg.state !== 'closed') return
    if (mediaReconnectInFlightRef.current) return
    mediaReconnectInFlightRef.current = true
    void (async () => {
      try {
        if (mic.state !== 'granted') {
          const ok = await mic.request()
          if (!ok) return
        }
        const newCallId = await leg.reconnectMedia()
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
    ringtone.stop()
    leg.goOffline()
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
  }, [leg, setStatusMutation, refetchCallRecords, dispatch])

  const accept = useCallback(async () => {
    const current = sessionRef.current.incoming
    if (!current) return
    // SIP-phone calls are answered on the physical handset; there is no browser
    // WebRTC leg to accept. The backend's cc.call_answered moves us to 通话中.
    if (!browserOwnsMedia(current.device_type)) return
    ringtone.stop()
    if (mic.state !== 'granted') {
      const ok = await mic.request()
      if (!ok) {
        toast.error('请先授权麦克风')
        return
      }
    }
    const ok = await leg.acceptOffer(current.offer_id)
    if (ok) {
      dispatch({ type: 'USER_ACCEPT_OK', callStart: Date.now() })
    } else {
      toast.error('接听失败，请稍后重试')
      dispatch({ type: 'USER_ACCEPT_FAIL' })
    }
  }, [leg, mic, ringtone, dispatch])

  const reject = useCallback(async () => {
    const current = sessionRef.current.incoming
    if (!current) return
    ringtone.stop()
    try {
      await rejectCurrentCall(current.offer_id)
    } catch {
      toast.error('拒接失败，请稍后重试')
    }
    dispatch({ type: 'USER_REJECT' })
  }, [ringtone, dispatch])

  const hangup = useCallback(async () => {
    ringtone.stop()
    const current = sessionRef.current.incoming
    const isOutbound = current?.direction === 'outbound'
    try {
      if (isOutbound && current?.call_id) {
        await cancelOutboundCall(current.call_id)
      } else {
        await hangupCurrentCall()
      }
    } catch {
      toast.error('挂断失败，请稍后重试')
    } finally {
      if (isOutbound) {
        leg.goOffline()
        dispatch({ type: 'USER_OUTBOUND_FAIL' })
        refetchCallRecords()
      }
    }
  }, [leg, refetchCallRecords, ringtone, dispatch])

  const completeWrapUp = useCallback(() => {
    dispatch({ type: 'USER_WRAP_UP_DONE' })
    setStatusMutation.mutate(
      { status: 'ready' },
      { onSettled: () => void refetchStatus() },
    )
    refetchCallRecords()
  }, [refetchCallRecords, refetchStatus, setStatusMutation, dispatch])

  const handleDialStarted = useCallback(async ({ callId, destination, outboundNumber }: DialStartedInfo) => {
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
    refetchCallRecords()
    // A desk-phone outbound is dialled from the handset's own extension, so
    // there is no browser leg to originate. Going further would pop a pointless
    // microphone prompt and then report a WebRTC failure for a call that is
    // ringing perfectly well. No browser ringback either: the handset plays its
    // own, and hearing one here suggests the call lives in the browser — which
    // makes the audio then arriving on the handset look like a fault.
    if (!browserOwnsMedia(currentDevice?.device_type)) return
    ringtone.start()
    if (mic.state !== 'granted') {
      await mic.request()
    }
    const failMessage = await leg.originateOffer(callId)
    if (failMessage) {
      ringtone.stop()
      leg.goOffline()
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
      dispatch({ type: 'USER_OUTBOUND_FAIL' })
    }
  }, [leg, mic, refetchCallRecords, ringtone, dispatch, currentDevice?.device_type])

  const screenPopNumber = selectedRecord
    ? callRecordCustomerNumber(selectedRecord) || ''
    : incoming?.customer_from
      ? incoming.customer_from
      : incoming?.direction === 'outbound'
        ? incoming.to || draftDialNumber.trim()
        : incoming?.from || draftDialNumber.trim()
  const showEmptyCallState = !selectedRecord && !incoming

  const value = useMemo<CallCenterRuntimeValue>(() => ({
    mic,
    leg,
    callControl,
    phase,
    incoming,
    callStart,
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
    setAgentStatus,
    accept,
    reject,
    hangup,
    completeWrapUp,
    handleDialStarted,
  }), [
    mic,
    leg,
    callControl,
    phase,
    incoming,
    callStart,
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
