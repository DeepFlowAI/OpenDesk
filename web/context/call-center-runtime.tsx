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

import { mapOutboundFailure } from '@/app/components/features/call-center/outbound-failure-message'
import { callRecordCustomerNumber } from '@/app/components/features/call-center/call-record-utils'
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
  startedAt: number
  direction?: 'inbound' | 'outbound'
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

export function CallCenterProvider({ children }: { children: ReactNode }) {
  const mic = useMicrophone({ autoRequestOnGranted: false })
  const { data: status, refetch: refetchStatus } = useMyAgentStatus()
  const setStatusMutation = useSetAgentStatus()
  const closeSession = useCloseWebRTCSession()
  const leg = useWebRTCLeg()
  const ringtone = useRingtone()
  const { socket } = useSocketStore()
  const { data: records, refetch: refetchRecords } = useCallRecords({ page: 1, per_page: 20 })

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
    }) => {
      setIncoming({
        offer_id: data.offer_id,
        call_id: data.call_id,
        from: data.from || '',
        to: data.to || '',
        queue_id: data.queue_id ?? null,
        startedAt: Date.now(),
      })
      setCallStart(Date.now())
      setSelectedRecordId(null)
      setPhase('incoming')
      ringtone.start()
      void refetchRecords()
    }

    const onRemoteIce = (data: { call_id: string; candidate: RTCIceCandidateInit }) => {
      void leg.applyRemoteIce(data.candidate)
    }

    const onHangup = (data: { call_id: string; reason?: string }) => {
      void data
      ringtone.stop()
      leg.goOffline()
      setPhase('wrap_up')
      void refetchStatus()
      void refetchRecords()
    }

    const onOutboundRinging = (data: { call_id: string }) => {
      setIncoming((prev) => {
        if (prev?.call_id !== data.call_id) return prev
        return { ...prev }
      })
      void refetchRecords()
    }

    const onOutboundAnswered = (data: { call_id: string }) => {
      void data
      ringtone.stop()
      setPhase((curr) => (curr === 'outbound_ringing' ? 'on_call' : curr))
      void refetchRecords()
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
      void refetchRecords()
    }

    socket.on('cc.call_incoming', onIncoming)
    socket.on('cc.webrtc.ice', onRemoteIce)
    socket.on('cc.call_hangup', onHangup)
    socket.on('cc.outbound_ringing', onOutboundRinging)
    socket.on('cc.outbound_answered', onOutboundAnswered)
    socket.on('cc.outbound_hangup', onOutboundHangup)
    return () => {
      socket.off('cc.call_incoming', onIncoming)
      socket.off('cc.webrtc.ice', onRemoteIce)
      socket.off('cc.call_hangup', onHangup)
      socket.off('cc.outbound_ringing', onOutboundRinging)
      socket.off('cc.outbound_answered', onOutboundAnswered)
      socket.off('cc.outbound_hangup', onOutboundHangup)
    }
  }, [socket, leg, ringtone, refetchRecords, refetchStatus])

  useEffect(() => {
    if (leg.state !== 'failed') return
    closeSession.mutate(undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leg.state])

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
      if (newStatus === 'ready') toast.success('已就绪 — 等待来电')
      else if (newStatus === 'offline') toast.success('已离线')
    } catch {
      toast.error('状态切换失败')
    }
  }, [leg, setStatusMutation])

  const accept = useCallback(async () => {
    if (!incoming) return
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
        void refetchRecords()
      }
    }
  }, [incoming, leg, refetchRecords, ringtone])

  const completeWrapUp = useCallback(() => {
    setIncoming(null)
    setCallStart(null)
    setPhase('idle')
    setStatusMutation.mutate(
      { status: 'ready' },
      { onSettled: () => void refetchStatus() },
    )
    void refetchRecords()
  }, [refetchRecords, refetchStatus, setStatusMutation])

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
    void refetchRecords()
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
  }, [leg, mic, refetchRecords, ringtone])

  const screenPopNumber = selectedRecord
    ? callRecordCustomerNumber(selectedRecord) || ''
    : incoming?.direction === 'outbound'
      ? incoming.to || draftDialNumber.trim()
      : incoming?.from || draftDialNumber.trim()
  const showEmptyCallState = !selectedRecord && !incoming

  const value = useMemo<CallCenterRuntimeValue>(() => ({
    mic,
    leg,
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
