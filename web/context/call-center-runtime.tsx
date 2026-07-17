'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'

import { agentDeviceKeys } from '@/service/use-agent-devices'
import { mapOutboundFailure } from '@/app/components/features/call-center/outbound-failure-message'
import { callRecordCustomerNumber } from '@/app/components/features/call-center/call-record-utils'
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
  /** 'internal_consult' / 'internal_transfer' for agent-to-agent calls; absent for real inbound. */
  call_type?: string
  startedAt: number
  direction?: 'inbound' | 'outbound'
  /** Current call device: 'sip_phone' rings/answers on the physical handset (no browser accept). */
  device_type?: string
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
  const { data: records, refetch: refetchRecords } = useCallRecords(
    { page: 1, per_page: 20 },
    { enabled: recordsEnabled },
  )

  const refetchCallRecords = useCallback(() => {
    if (!recordsEnabled) return
    void refetchRecords()
  }, [recordsEnabled, refetchRecords])

  const [phase, setPhase] = useState<CallCenterPhase>('mic_check')
  const [incoming, setIncoming] = useState<IncomingCall | null>(null)
  const [callStart, setCallStart] = useState<number | null>(null)
  const [now, setNow] = useState<number>(Date.now())
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null)
  const [draftDialNumber, setDraftDialNumber] = useState('')
  const [draftOutboundNumber, setDraftOutboundNumber] = useState('')
  const [callSummaryTab, setCallSummaryTab] = useState<'summary' | 'ticket'>('summary')

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
      setPhase((curr) => (curr === 'mic_check' ? 'mic_denied' : curr))
    } else if (mic.state === 'granted' || mic.state === 'prompt') {
      setPhase((curr) => (curr === 'mic_check' ? 'idle' : curr))
    }
  }, [mic.state])

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
    }) => {
      setIncoming({
        offer_id: data.offer_id,
        call_id: data.call_id,
        from: data.from || '',
        to: data.to || '',
        queue_id: data.queue_id ?? null,
        call_type: data.call_type,
        device_type: data.device_type,
        startedAt: Date.now(),
      })
      setCallStart(Date.now())
      setSelectedRecordId(null)
      setPhase('incoming')
      ringtone.start()
      refetchCallRecords()
    }

    // SIP-phone inbound: the call is answered on the physical handset, so the
    // backend tells the browser to move to 通话中 (no browser "接听" click).
    const onCallAnswered = (data: { call_id: string }) => {
      void data
      ringtone.stop()
      setPhase((curr) => (curr === 'incoming' ? 'on_call' : curr))
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
      void data
      ringtone.stop()
      leg.goOffline()
      // A hangup while the call was only ringing (never answered — e.g. a SIP
      // handset that didn't pick up, or the caller giving up) returns to idle;
      // wrap-up is only for a call that was actually on air.
      setPhase((curr) => {
        if (curr === 'incoming' || curr === 'outbound_ringing') {
          setIncoming(null)
          return 'idle'
        }
        return 'wrap_up'
      })
      void refetchStatus()
      refetchCallRecords()
    }

    const onOutboundRinging = (data: { call_id: string }) => {
      setIncoming((prev) => {
        if (prev?.call_id !== data.call_id) return prev
        return { ...prev }
      })
      refetchCallRecords()
    }

    const onOutboundAnswered = (data: { call_id: string }) => {
      void data
      ringtone.stop()
      setPhase((curr) => (curr === 'outbound_ringing' ? 'on_call' : curr))
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
      const showFailureToast = () => {
        if (!failure.message) return
        if (failure.level === 'info') toast(failure.message)
        else toast.error(failure.message)
      }
      setPhase((curr) => {
        if (curr === 'outbound_ringing') {
          showFailureToast()
          setIncoming(null)
          setCallStart(null)
          return 'idle'
        }
        if (curr === 'on_call') {
          showFailureToast()
          return 'wrap_up'
        }
        return curr
      })
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
    }) => {
      handleConsultResult(data)
    }

    // Result of a browser-ring transfer to a Web-phone colleague. On failure
    // the initiator returns to "单人通话" (customer preserved); on success the
    // customer is handed over and the initiator's own leg hangs up (which the
    // cc.call_hangup handler turns into wrap-up), so here we only clear state.
    const onTransferResult = (data: { ok: boolean; reason?: string }) => {
      handleTransferResult(data)
    }

    // A ringing conference participant answered (→ live) or failed to connect.
    const onConferenceResult = (data: { ok: boolean; reason?: string }) => {
      handleConferenceResult(data)
    }

    // The added participant left/hung up → collapse the 3-way to the 1:1 call.
    const onConferenceParticipantLeft = () => {
      handleConferenceParticipantLeft()
    }

    socket.on('cc.call_incoming', onIncoming)
    socket.on('cc.call_answered', onCallAnswered)
    socket.on('cc.device_registration_changed', onDeviceRegistrationChanged)
    socket.on('cc.webrtc.ice', onRemoteIce)
    socket.on('cc.call_hangup', onHangup)
    socket.on('cc.outbound_ringing', onOutboundRinging)
    socket.on('cc.outbound_answered', onOutboundAnswered)
    socket.on('cc.outbound_hangup', onOutboundHangup)
    socket.on('cc.consult_result', onConsultResult)
    socket.on('cc.transfer_result', onTransferResult)
    socket.on('cc.conference_result', onConferenceResult)
    socket.on('cc.conference_participant_left', onConferenceParticipantLeft)
    return () => {
      socket.off('cc.call_incoming', onIncoming)
      socket.off('cc.call_answered', onCallAnswered)
      socket.off('cc.device_registration_changed', onDeviceRegistrationChanged)
      socket.off('cc.webrtc.ice', onRemoteIce)
      socket.off('cc.call_hangup', onHangup)
      socket.off('cc.outbound_ringing', onOutboundRinging)
      socket.off('cc.outbound_answered', onOutboundAnswered)
      socket.off('cc.outbound_hangup', onOutboundHangup)
      socket.off('cc.consult_result', onConsultResult)
      socket.off('cc.transfer_result', onTransferResult)
      socket.off('cc.conference_result', onConferenceResult)
      socket.off('cc.conference_participant_left', onConferenceParticipantLeft)
    }
  }, [
    socket,
    leg,
    ringtone,
    handleConsultResult,
    handleTransferResult,
    handleConferenceResult,
    handleConferenceParticipantLeft,
    refetchCallRecords,
    refetchStatus,
    queryClient,
  ])

  useEffect(() => {
    if (leg.state !== 'failed') return
    closeSession.mutate(undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leg.state])

  // Any in-call control state (hold/consult/conference/mute) only makes sense
  // during an active call; clear it once the call leaves the on_call phase.
  useEffect(() => {
    if (phase !== 'on_call') callControl.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase])

  useEffect(() => {
    if (leg.state === 'failed') {
      toast.error(`通话服务连接失败${leg.error ? `：${leg.error}` : ''}`)
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
      if (phase === 'wrap_up') {
        setIncoming(null)
        setCallStart(null)
        setPhase('idle')
        refetchCallRecords()
      }
      if (newStatus === 'ready') toast.success('已就绪 — 等待来电')
      else if (newStatus === 'offline') toast.success('已离线')
    } catch {
      toast.error('状态切换失败')
    }
  }, [leg, setStatusMutation, phase, refetchCallRecords])

  const accept = useCallback(async () => {
    if (!incoming) return
    // SIP-phone calls are answered on the physical handset; there is no browser
    // WebRTC leg to accept. The backend's cc.call_answered moves us to 通话中.
    if (incoming.device_type === 'sip_phone') return
    ringtone.stop()
    if (mic.state !== 'granted') {
      const ok = await mic.request()
      if (!ok) {
        toast.error('请先授权麦克风')
        return
      }
    }
    const ok = await leg.acceptOffer(incoming.offer_id)
    if (ok) {
      setPhase('on_call')
      setCallStart(Date.now())
    } else {
      toast.error('接听失败，请稍后重试')
      setPhase('idle')
      setIncoming(null)
    }
  }, [incoming, leg, mic, ringtone])

  const reject = useCallback(async () => {
    if (!incoming) return
    ringtone.stop()
    try {
      await rejectCurrentCall(incoming.offer_id)
    } catch {
      toast.error('拒接失败，请稍后重试')
    }
    setPhase('idle')
    setIncoming(null)
  }, [incoming, ringtone])

  const hangup = useCallback(async () => {
    ringtone.stop()
    const isOutbound = incoming?.direction === 'outbound'
    try {
      if (isOutbound && incoming?.call_id) {
        await cancelOutboundCall(incoming.call_id)
      } else {
        await hangupCurrentCall()
      }
    } catch {
      toast.error('挂断失败，请稍后重试')
    } finally {
      if (isOutbound) {
        leg.goOffline()
        setIncoming(null)
        setCallStart(null)
        setPhase('idle')
        refetchCallRecords()
      }
    }
  }, [incoming, leg, refetchCallRecords, ringtone])

  const completeWrapUp = useCallback(() => {
    setIncoming(null)
    setCallStart(null)
    setPhase('idle')
    setStatusMutation.mutate(
      { status: 'ready' },
      { onSettled: () => void refetchStatus() },
    )
    refetchCallRecords()
  }, [refetchCallRecords, refetchStatus, setStatusMutation])

  const handleDialStarted = useCallback(async ({ callId, destination, outboundNumber }: DialStartedInfo) => {
    setSelectedRecordId(null)
    setIncoming({
      offer_id: '',
      call_id: callId,
      from: outboundNumber,
      to: destination,
      queue_id: null,
      startedAt: Date.now(),
      direction: 'outbound',
    })
    setCallStart(Date.now())
    setPhase('outbound_ringing')
    refetchCallRecords()
    ringtone.start()
    if (mic.state !== 'granted') {
      await mic.request()
    }
    const ok = await leg.originateOffer(callId)
    if (!ok) {
      if (leg.error) toast.error(leg.error)
      ringtone.stop()
      leg.goOffline()
      setIncoming(null)
      setCallStart(null)
      setPhase('idle')
    }
  }, [leg, mic, refetchCallRecords, ringtone])

  const screenPopNumber = selectedRecord
    ? callRecordCustomerNumber(selectedRecord) || ''
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
