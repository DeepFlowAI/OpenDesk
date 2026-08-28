'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  IconAlertTriangle,
  IconArrowsExchange,
  IconCheck,
  IconChevronDown,
  IconDeviceDesktop,
  IconDeviceLandlinePhone,
  IconDialpad,
  IconDots,
  IconHeadset,
  IconMicrophone,
  IconMicrophoneOff,
  IconMinus,
  IconPhone,
  IconPhoneCall,
  IconPhoneIncoming,
  IconPhoneOff,
  IconPhoneOutgoing,
  IconPlayerPause,
  IconPlayerPlay,
  IconSparkles,
  IconSwitchHorizontal,
  IconUsers,
  IconUsersGroup,
} from '@tabler/icons-react'
import { toast } from 'sonner'

import {
  CallTargetPickerDialog,
  type CallTargetPickerMode,
  type PickedTarget,
} from '@/app/components/features/call-center/call-target-picker-dialog'
import {
  CALL_STATUS_OPTIONS,
  formatCallDuration,
  useCallCenterRuntime,
} from '@/context/call-center-runtime'
import { cn } from '@/lib/utils'
import type { EmbedSession, EmbeddedDialPayload } from '@/models/embedded-call'
import type { AgentStatus } from '@/models/call-center'
import type { AgentCallDevice, CallDeviceType } from '@/models/call-device'
import {
  useMyCallDevices,
  useMyCurrentCallDevice,
  useSetMyCurrentCallDevice,
} from '@/service/use-agent-devices'
import { useEmbeddedOutboundNumbers } from '@/service/use-embedded-call'


type EmbeddedCallPanelProps = {
  session: EmbedSession
  locale: 'zh' | 'en'
  connected: boolean
  isOwner: boolean
  ownerInstanceId: string | null
  expanded: boolean
  activated: boolean
  prefill: EmbeddedDialPayload | null
  onExpandedChange: (expanded: boolean) => void
  onActivatedChange: (activated: boolean) => void
  onDial: (payload: EmbeddedDialPayload & { outboundNumberId: string }) => Promise<unknown>
  onTakeover: () => Promise<void>
}

export function EmbeddedCallPanel({
  session,
  locale,
  connected,
  isOwner,
  ownerInstanceId,
  expanded,
  activated,
  prefill,
  onExpandedChange,
  onActivatedChange,
  onDial,
  onTakeover,
}: EmbeddedCallPanelProps) {
  const isZh = locale === 'zh'
  const runtime = useCallCenterRuntime()
  const { data: currentDevice, isLoading: currentDeviceLoading } = useMyCurrentCallDevice()
  const { data: devicesData } = useMyCallDevices({ refetchInterval: 15_000 })
  const setCurrentDevice = useSetMyCurrentCallDevice()
  const { data: phoneNumbers } = useEmbeddedOutboundNumbers()
  const outboundNumbers = useMemo(
    () => (phoneNumbers?.items ?? []).filter((item) => item.call_types.includes('outbound')),
    [phoneNumbers],
  )
  const [number, setNumber] = useState('')
  const [outboundNumberId, setOutboundNumberId] = useState('')
  const [context, setContext] = useState<EmbeddedDialPayload['externalContext']>()
  const [businessInfo, setBusinessInfo] = useState<string | undefined>()
  const [dialing, setDialing] = useState(false)
  const [dtmfOpen, setDtmfOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const [takeoverPending, setTakeoverPending] = useState(false)
  const [unsupportedSize, setUnsupportedSize] = useState(false)
  const autoWebRtcRef = useRef(false)

  useEffect(() => {
    const checkSize = () => setUnsupportedSize(
      window.innerWidth < 320 || (expanded && window.innerHeight < 420),
    )
    checkSize()
    window.addEventListener('resize', checkSize)
    return () => window.removeEventListener('resize', checkSize)
  }, [expanded])

  useEffect(() => {
    if (outboundNumberId || outboundNumbers.length === 0) return
    setOutboundNumberId(outboundNumbers[0].id)
  }, [outboundNumberId, outboundNumbers])

  useEffect(() => {
    if (!prefill) return
    setNumber(prefill.number)
    setOutboundNumberId(prefill.outboundNumberId || outboundNumbers[0]?.id || '')
    setContext(prefill.externalContext)
    setBusinessInfo(prefill.customBusinessInfo)
  }, [prefill, outboundNumbers])

  useEffect(() => {
    if (!isOwner || currentDeviceLoading || autoWebRtcRef.current) return
    if (currentDevice === undefined) return
    if (currentDevice.device_type) return
    autoWebRtcRef.current = true
    void setCurrentDevice.mutateAsync('webrtc')
  }, [currentDevice, currentDeviceLoading, isOwner, setCurrentDevice])

  const phase = runtime.phase
  const callNumber = runtime.incoming?.direction === 'outbound'
    ? runtime.incoming.to
    : runtime.incoming?.from
  const duration = runtime.callStart ? formatCallDuration(runtime.now - runtime.callStart) : '00:00'
  const customerName = context?.display_name || callNumber || ''
  const selectedOutbound = outboundNumbers.find((item) => item.id === outboundNumberId)
  const devices = devicesData?.items ?? []
  const currentType = currentDevice?.device_type ?? null
  const currentListed = devices.find((item) => item.device_type === currentType) ?? null
  const deviceLabel = currentListed
    ? formatDeviceLabel(currentListed, isZh)
    : (isZh ? 'Web 电话' : 'Web phone')
  const headerStatus = resolveHeaderStatus({
    isOwner,
    phase,
    agentStatus: runtime.status?.status ?? 'offline',
    isZh,
  })
  const deviceHint = resolveDeviceHint({
    isOwner,
    activated,
    phase,
    prefill: Boolean(prefill),
    duration,
    isZh,
  })

  const activate = async () => {
    if (currentType === 'sip_phone') {
      onActivatedChange(true)
      return
    }
    const granted = runtime.mic.state === 'granted' || await runtime.mic.request()
    onActivatedChange(granted)
  }

  const dial = async () => {
    if (!number.trim() || !outboundNumberId || dialing || !isOwner) return
    setDialing(true)
    try {
      await onDial({
        number: number.trim(),
        outboundNumberId,
        externalContext: context,
        customBusinessInfo: businessInfo,
      })
    } finally {
      setDialing(false)
    }
  }

  const takeover = async () => {
    if (!window.confirm(isZh ? '确认在此窗口接管通话控制？' : 'Take control in this window?')) return
    setTakeoverPending(true)
    try {
      await onTakeover()
    } finally {
      setTakeoverPending(false)
    }
  }

  const switchDevice = async (device: AgentCallDevice) => {
    if (device.device_type === currentType || !device.available) return
    try {
      await setCurrentDevice.mutateAsync(device.device_type)
    } catch {
      toast.error(isZh ? '设备切换失败，请重试' : 'Failed to switch device')
    }
  }

  if (unsupportedSize) {
    return (
      <main className="flex h-dvh w-full items-center justify-center bg-background p-4 text-center text-foreground">
        <div role="alert">
          <IconAlertTriangle className="mx-auto text-warning" size={28} />
          <p className="mt-3 text-sm font-semibold">
            {isZh ? '通话组件空间不足' : 'The call panel is too small'}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {isZh ? '请将容器调整到至少 320 × 420 像素' : 'Resize the container to at least 320 × 420 pixels'}
          </p>
        </div>
      </main>
    )
  }

  return (
    <main className={cn(
      'flex h-dvh w-full min-w-[320px] flex-col overflow-hidden bg-background text-foreground',
      expanded ? 'min-h-[420px]' : 'min-h-14',
    )}>
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div className="flex min-w-0 items-center gap-2">
          <span className="grid h-8 w-8 shrink-0 place-items-center text-foreground">
            <IconHeadset size={22} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">
              {expanded ? `OpenDesk ${isZh ? '通话' : 'Call'}` : headerStatus.label}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <span className={cn('h-1.5 w-1.5 rounded-full', connected ? 'bg-success' : 'bg-warning')} />
              {expanded
                ? (connected ? (isZh ? '连接正常' : 'Connected') : (isZh ? '连接中' : 'Connecting'))
                : duration}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {expanded ? (
            <StatusPill
              {...headerStatus}
              options={CALL_STATUS_OPTIONS}
              disabled={!isOwner || runtime.statusChangePending || !headerStatus.dropdown}
              isZh={isZh}
              onChange={(status) => void runtime.setAgentStatus(status)}
            />
          ) : null}
          <button
            type="button"
            className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => onExpandedChange(!expanded)}
            aria-label={expanded ? (isZh ? '收起' : 'Collapse') : (isZh ? '展开' : 'Expand')}
          >
            {expanded ? <IconMinus size={15} /> : <IconPhone size={15} />}
          </button>
        </div>
      </header>

      {expanded ? (
        <>
          <div className="flex h-11 shrink-0 items-center justify-between border-b border-border bg-muted/40 px-4 text-xs">
            {isOwner ? (
              <DeviceMenu
                devices={devices}
                currentType={currentType}
                label={deviceLabel}
                locked={phase !== 'idle' && phase !== 'wrap_up'}
                pending={setCurrentDevice.isPending}
                isZh={isZh}
                onSelect={(device) => void switchDevice(device)}
              />
            ) : (
              <span className="flex items-center gap-2 text-muted-foreground">
                <IconPhoneCall size={15} />
                {deviceLabel}
              </span>
            )}
            <span className="text-muted-foreground">{deviceHint}</span>
          </div>

          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            {!isOwner ? (
              <ObserverBody
                isZh={isZh}
                customerName={customerName}
                duration={duration}
                pending={takeoverPending}
                ownerInstanceId={ownerInstanceId}
                onTakeover={() => void takeover()}
              />
            ) : !activated ? (
              <ActivateBody
                isZh={isZh}
                sip={currentType === 'sip_phone'}
                micDenied={runtime.mic.state === 'denied'}
                onActivate={() => void activate()}
              />
            ) : phase === 'incoming' ? (
              <IncomingBody
                isZh={isZh}
                name={customerName}
                number={callNumber}
                duration={duration}
                sip={runtime.incoming?.device_type === 'sip_phone'}
                onAccept={() => void runtime.accept()}
                onReject={() => void runtime.reject()}
              />
            ) : phase === 'outbound_ringing' ? (
              <OutboundBody
                isZh={isZh}
                name={customerName}
                number={callNumber || number}
                outboundNumber={selectedOutbound?.phone_number || runtime.incoming?.from}
                duration={duration}
                recordId={context?.record_id}
                onCancel={() => void runtime.hangup()}
              />
            ) : phase === 'on_call' ? (
              <OnCallBody
                isZh={isZh}
                name={customerName}
                number={callNumber}
                duration={duration}
                recordLabel={context?.display_name || context?.record_id}
                dtmfOpen={dtmfOpen}
                moreOpen={moreOpen}
                permissions={session.agent.permissions}
                onToggleDtmf={() => setDtmfOpen((value) => !value)}
                onToggleMore={() => setMoreOpen((value) => !value)}
                onHangup={() => void runtime.hangup()}
              />
            ) : phase === 'wrap_up' ? (
              <WrapUpBody
                isZh={isZh}
                name={customerName}
                number={callNumber}
                duration={duration}
                remaining={
                  runtime.wrapUpUntil != null
                    ? formatCallDuration(Math.max(0, runtime.wrapUpUntil - runtime.now))
                    : null
                }
                outbound={runtime.incoming?.direction === 'outbound'}
                onComplete={runtime.completeWrapUp}
              />
            ) : (
              <IdleBody
                isZh={isZh}
                prefill={Boolean(prefill)}
                name={context?.display_name}
                company={context?.attributes?.company || context?.record_type}
                number={number}
                outboundNumberId={outboundNumberId}
                outboundNumbers={outboundNumbers}
                recordId={context?.record_id}
                dialing={dialing}
                onNumberChange={setNumber}
                onOutboundChange={setOutboundNumberId}
                onDial={() => void dial()}
              />
            )}
          </div>

          <footer className="flex h-9 shrink-0 items-center justify-center gap-1.5 border-t border-border bg-muted/30 text-[10px] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            {isZh ? '安全连接' : 'Secure connection'}
          </footer>
        </>
      ) : null}
      <div className="sr-only" aria-live="polite">{headerStatus.label}</div>
    </main>
  )
}

function IdleBody({
  isZh,
  prefill,
  name,
  company,
  number,
  outboundNumberId,
  outboundNumbers,
  recordId,
  dialing,
  onNumberChange,
  onOutboundChange,
  onDial,
}: {
  isZh: boolean
  prefill: boolean
  name?: string
  company?: string
  number: string
  outboundNumberId: string
  outboundNumbers: { id: string; phone_number: string }[]
  recordId?: string
  dialing: boolean
  onNumberChange: (value: string) => void
  onOutboundChange: (value: string) => void
  onDial: () => void
}) {
  return (
    <div className="flex flex-1 flex-col px-5 py-5">
      {prefill ? (
        <div className="flex items-start gap-3 rounded-lg border border-info/20 bg-info/8 p-3">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-info/15 text-info">
            <IconSparkles size={15} />
          </span>
          <div>
            <p className="text-xs font-medium">{isZh ? '号码已从客户资料带入' : 'Number filled from the host record'}</p>
            <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
              {isZh ? '尚未发起外呼，请核对号码后确认。' : 'Review the number, then confirm to start the call.'}
            </p>
          </div>
        </div>
      ) : null}

      <div className={prefill ? 'mt-6 text-center' : 'text-center'}>
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-secondary text-lg font-semibold">
          {initialsOf(name, isZh ? '呼' : 'C')}
        </span>
        <h2 className="mt-3 text-lg font-semibold">{name || (isZh ? '外呼' : 'Outbound')}</h2>
        {company ? <p className="mt-1 text-xs text-muted-foreground">{company}</p> : null}
      </div>

      <div className="mt-6 space-y-4">
        <label className="block">
          <span className="text-xs font-medium">{isZh ? '被叫号码' : 'Phone number'}</span>
          <input
            value={number}
            inputMode="tel"
            onChange={(event) => onNumberChange(event.target.value)}
            className="mt-2 h-10 w-full rounded-lg border border-border bg-background px-3 font-mono text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder={isZh ? '输入用户号码' : 'Enter a phone number'}
          />
        </label>
        <label className="block">
          <span className="text-xs font-medium">{isZh ? '外显号码' : 'Caller ID'}</span>
          <div className="relative mt-2">
            <select
              value={outboundNumberId}
              onChange={(event) => onOutboundChange(event.target.value)}
              className="h-10 w-full appearance-none rounded-lg border border-border bg-background px-3 pr-8 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="">{isZh ? '选择外呼号码' : 'Select outbound number'}</option>
              {outboundNumbers.map((item) => (
                <option key={item.id} value={item.id}>{item.phone_number}</option>
              ))}
            </select>
            <IconChevronDown size={15} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          </div>
        </label>
      </div>

      <button
        type="button"
        onClick={onDial}
        disabled={!number.trim() || !outboundNumberId || dialing}
        className="mt-auto flex h-11 items-center justify-center gap-2 rounded-lg bg-primary text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
      >
        <IconPhone size={18} />
        {dialing
          ? (isZh ? '正在呼叫…' : 'Calling…')
          : (prefill ? (isZh ? '确认外呼' : 'Confirm call') : (isZh ? '确认外呼' : 'Place call'))}
      </button>
      {recordId ? (
        <p className="mt-3 text-center text-[10px] text-muted-foreground">
          {isZh ? `将关联客户记录 ${recordId}` : `Will link record ${recordId}`}
        </p>
      ) : null}
    </div>
  )
}

function OutboundBody({
  isZh,
  name,
  number,
  outboundNumber,
  duration,
  recordId,
  onCancel,
}: {
  isZh: boolean
  name: string
  number?: string
  outboundNumber?: string
  duration: string
  recordId?: string
  onCancel: () => void
}) {
  return (
    <div className="flex flex-1 flex-col px-5 py-5">
      <div className="text-center">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-secondary text-lg font-semibold">
          {initialsOf(name, isZh ? '客' : 'C')}
        </span>
        <h2 className="mt-3 text-lg font-semibold">{name || number || '—'}</h2>
      </div>
      <div className="mt-5 rounded-xl bg-muted/60 px-4 py-3">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{isZh ? '被叫号码' : 'Called number'}</span>
          <span className="font-mono font-medium">{number || '—'}</span>
        </div>
        {outboundNumber ? (
          <div className="mt-2 flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{isZh ? '外显号码' : 'Caller ID'}</span>
            <span className="font-medium">{outboundNumber}</span>
          </div>
        ) : null}
      </div>
      <div className="mt-5 flex flex-col items-center">
        <span className="grid h-12 w-12 place-items-center rounded-full bg-primary/10 text-primary">
          <IconPhoneOutgoing size={22} />
        </span>
        <p className="mt-3 text-sm font-semibold">{isZh ? '正在呼叫…' : 'Calling…'}</p>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{duration}</p>
      </div>
      <button
        type="button"
        onClick={onCancel}
        className="mt-auto flex h-11 items-center justify-center gap-2 rounded-lg bg-destructive/10 text-sm font-medium text-destructive"
      >
        <IconPhoneOff size={18} />
        {isZh ? '取消外呼' : 'Cancel call'}
      </button>
      {recordId ? (
        <p className="mt-3 text-center text-[10px] text-muted-foreground">
          {isZh ? `已关联客户记录 ${recordId}` : `Linked record ${recordId}`}
        </p>
      ) : null}
    </div>
  )
}

function IncomingBody({
  isZh,
  name,
  number,
  duration,
  sip,
  onAccept,
  onReject,
}: {
  isZh: boolean
  name: string
  number?: string
  duration: string
  sip: boolean
  onAccept: () => void
  onReject: () => void
}) {
  return (
    <div className="flex flex-1 flex-col px-5 py-5">
      <div className="flex items-center justify-between">
        <span className="rounded-full bg-success/10 px-2.5 py-1 text-[11px] font-medium text-success">
          {isZh ? '呼入电话' : 'Incoming'}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{duration}</span>
      </div>
      <div className="mt-8 text-center">
        <div className="relative mx-auto w-fit">
          <span className="grid h-20 w-20 place-items-center rounded-full bg-secondary text-2xl font-semibold">
            {initialsOf(name, isZh ? '客' : 'C')}
          </span>
          <span className="absolute -bottom-1 -right-1 grid h-7 w-7 place-items-center rounded-full border-2 border-background bg-success text-white">
            <IconPhone size={13} />
          </span>
        </div>
        <h2 className="mt-4 text-xl font-semibold">{name || number || '—'}</h2>
        {name && number && name !== number ? (
          <p className="mt-1 font-mono text-sm text-muted-foreground">{number}</p>
        ) : null}
        {sip ? (
          <p className="mt-3 text-xs text-muted-foreground">
            {isZh ? '请在话机上摘机接听' : 'Answer on the SIP phone'}
          </p>
        ) : null}
      </div>
      <div className="mt-8 grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={onReject}
          className="flex h-12 items-center justify-center gap-2 rounded-xl bg-destructive/10 text-sm font-medium text-destructive"
        >
          <IconPhoneOff size={19} />
          {isZh ? '拒绝' : 'Reject'}
        </button>
        {sip ? (
          <div className="flex h-12 items-center justify-center rounded-xl bg-muted text-sm font-medium text-muted-foreground">
            {isZh ? '话机响铃中' : 'Ringing on phone'}
          </div>
        ) : (
          <button
            type="button"
            onClick={onAccept}
            className="flex h-12 items-center justify-center gap-2 rounded-xl bg-success text-sm font-medium text-white"
          >
            <IconPhone size={19} />
            {isZh ? '接听' : 'Answer'}
          </button>
        )}
      </div>
      <div className="mt-auto rounded-lg bg-muted px-3 py-3 text-center text-[11px] leading-4 text-muted-foreground">
        {isZh ? '已向宿主系统发送弹屏事件。' : 'A screen-pop event was sent to the host app.'}
      </div>
    </div>
  )
}

function OnCallBody({
  isZh,
  name,
  number,
  duration,
  recordLabel,
  dtmfOpen,
  moreOpen,
  permissions,
  onToggleDtmf,
  onToggleMore,
  onHangup,
}: {
  isZh: boolean
  name: string
  number?: string
  duration: string
  recordLabel?: string
  dtmfOpen: boolean
  moreOpen: boolean
  permissions: string[]
  onToggleDtmf: () => void
  onToggleMore: () => void
  onHangup: () => void
}) {
  const { callControl } = useCallCenterRuntime()
  const [picker, setPicker] = useState<CallTargetPickerMode | null>(null)
  const canTransfer = permissions.includes('call.operation.transfer')
  const canConsult = permissions.includes('call.operation.consult')
  const canConference = permissions.includes('call.operation.conference')
  const inConsult = callControl.mode === 'consult_ringing' || callControl.mode === 'consult_active'
  const inConference = callControl.mode === 'conference' || callControl.mode === 'conference_ringing'
  const hasMore = canConference || inConsult || inConference

  const submit = (target: PickedTarget) => {
    if (picker === 'transfer') {
      if (!window.confirm(isZh ? `确认转接给 ${target.target_name}？` : `Transfer to ${target.target_name}?`)) return
      void callControl.submitTransfer({
        target_type: target.target_type,
        target_id: target.target_id,
        number: target.number,
      })
    } else if (picker === 'consult') {
      void callControl.beginConsult({
        target_type: target.target_type === 'external' ? 'external' : 'employee',
        target_id: target.target_id,
        number: target.number,
        target_name: target.target_name,
      })
    } else if (picker === 'conference') {
      void callControl.addParticipant({
        target_type: target.target_type === 'external' ? 'external' : 'employee',
        target_id: target.target_id,
        number: target.number,
        target_name: target.target_name,
      })
    }
    setPicker(null)
  }

  return (
    <div className="flex flex-1 flex-col px-5 py-5">
      <div className="text-center">
        <span className="grid h-14 w-14 place-items-center rounded-full bg-secondary text-lg font-semibold">
          {initialsOf(name, isZh ? '客' : 'C')}
        </span>
        <h2 className="mt-3 text-lg font-semibold">{name || number || '—'}</h2>
        {name && number && name !== number ? (
          <p className="mt-1 font-mono text-sm text-muted-foreground">{number}</p>
        ) : null}
        <div className="mt-3 flex items-center justify-center gap-2 text-sm font-medium">
          <span className="h-2 w-2 rounded-full bg-destructive" />
          {isZh ? '通话中' : 'On call'} · <span className="font-mono tabular-nums">{duration}</span>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-3 gap-x-3 gap-y-4">
        <CallAction
          icon={callControl.muted ? <IconMicrophoneOff /> : <IconMicrophone />}
          label={callControl.muted ? (isZh ? '取消静音' : 'Unmute') : (isZh ? '静音' : 'Mute')}
          active={callControl.muted}
          onClick={callControl.toggleMute}
        />
        <CallAction
          icon={callControl.mode === 'hold' ? <IconPlayerPlay /> : <IconPlayerPause />}
          label={callControl.mode === 'hold' ? (isZh ? '取回' : 'Resume') : (isZh ? '保持' : 'Hold')}
          active={callControl.mode === 'hold'}
          onClick={() => void callControl.toggleHold()}
        />
        <CallAction
          icon={<IconDialpad />}
          label={isZh ? '拨号盘' : 'Keypad'}
          active={dtmfOpen}
          onClick={onToggleDtmf}
        />
        {inConsult ? (
          <CallAction
            icon={<IconArrowsExchange />}
            label={isZh ? '结束咨询' : 'End consult'}
            onClick={() => void callControl.finishConsult()}
          />
        ) : inConference ? (
          <>
            {callControl.mode === 'conference' ? (
              <CallAction
                icon={<IconUsersGroup />}
                label={isZh ? '离开三方' : 'Leave'}
                onClick={() => void callControl.leaveConference()}
              />
            ) : null}
            <CallAction
              icon={<IconPhoneOff />}
              label={isZh ? '结束全部' : 'End all'}
              onClick={() => {
                if (window.confirm(isZh ? '确认结束全部通话？' : 'End all calls?')) {
                  void callControl.endAll()
                }
              }}
            />
          </>
        ) : (
          <>
            {canTransfer ? (
              <CallAction
                icon={<IconSwitchHorizontal />}
                label={isZh ? '转接' : 'Transfer'}
                onClick={() => setPicker('transfer')}
              />
            ) : null}
            {canConsult ? (
              <CallAction
                icon={<IconUsers />}
                label={isZh ? '咨询' : 'Consult'}
                onClick={() => setPicker('consult')}
              />
            ) : null}
            {hasMore ? (
              <div className="relative flex flex-col items-center">
                <CallAction
                  icon={<IconDots />}
                  label={isZh ? '更多' : 'More'}
                  active={moreOpen}
                  onClick={onToggleMore}
                />
                {moreOpen && canConference ? (
                  <button
                    type="button"
                    onClick={() => {
                      onToggleMore()
                      setPicker('conference')
                    }}
                    className="absolute top-full z-10 mt-1 whitespace-nowrap rounded-md border border-border bg-background px-3 py-1.5 text-xs shadow-md"
                  >
                    {isZh ? '三方' : 'Conference'}
                  </button>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </div>

      {dtmfOpen ? (
        <div className="mt-4 grid grid-cols-3 gap-2">
          {'123456789*0#'.split('').map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => void callControl.sendDtmf(key)}
              className="h-10 rounded-lg border border-border text-sm hover:bg-muted"
            >
              {key}
            </button>
          ))}
        </div>
      ) : null}

      <div className="mt-auto">
        {recordLabel ? (
          <div className="mb-4 flex items-center justify-between rounded-lg bg-muted px-3 py-2.5 text-xs">
            <span className="text-muted-foreground">{isZh ? '关联记录' : 'Related record'}</span>
            <span className="font-medium">{recordLabel}</span>
          </div>
        ) : null}
        <button
          type="button"
          onClick={onHangup}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-destructive text-sm font-medium text-white"
        >
          <IconPhoneOff size={18} />
          {isZh ? '挂断' : 'Hang up'}
        </button>
      </div>

      <CallTargetPickerDialog
        open={picker !== null}
        mode={picker ?? 'transfer'}
        allowQueue={picker === 'transfer'}
        submitting={callControl.pending !== null}
        onClose={() => setPicker(null)}
        onSubmit={submit}
      />
    </div>
  )
}

function WrapUpBody({
  isZh,
  name,
  number,
  duration,
  remaining,
  outbound,
  onComplete,
}: {
  isZh: boolean
  name: string
  number?: string
  duration: string
  remaining: string | null
  outbound: boolean
  onComplete: () => void
}) {
  return (
    <div className="flex flex-1 flex-col px-5 py-5">
      <div className="text-center">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-success/10 text-success">
          <IconCheck size={26} />
        </span>
        <h2 className="mt-3 text-lg font-semibold">{isZh ? '通话已结束' : 'Call ended'}</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {isZh ? '请确认本次整理完成' : 'Confirm wrap-up to continue'}
        </p>
      </div>
      <div className="mt-6 divide-y divide-border rounded-xl border border-border px-4">
        <SummaryRow label={isZh ? '客户' : 'Customer'} value={[name, number].filter(Boolean).join(' · ') || '—'} />
        <SummaryRow label={isZh ? '方向' : 'Direction'} value={outbound ? (isZh ? '呼出' : 'Outbound') : (isZh ? '呼入' : 'Inbound')} />
        <SummaryRow label={isZh ? '通话时长' : 'Duration'} value={duration} />
      </div>
      {remaining != null && (
        <p className="mt-4 text-center font-mono text-sm tabular-nums text-muted-foreground">
          {isZh ? `整理剩余 ${remaining}` : `Wrap-up ${remaining}`}
        </p>
      )}
      <div className="mt-4 rounded-lg bg-warning/10 px-3 py-3 text-xs leading-5 text-foreground/75">
        {isZh ? '完成整理后，坐席状态将自动恢复为“就绪”。' : 'Completing wrap-up returns the agent to Ready.'}
      </div>
      <button
        type="button"
        onClick={onComplete}
        className="mt-auto h-11 rounded-lg bg-primary text-sm font-medium text-primary-foreground"
      >
        {isZh ? '完成整理' : 'Finish wrap-up'}
      </button>
    </div>
  )
}

function ObserverBody({
  isZh,
  customerName,
  duration,
  pending,
  ownerInstanceId,
  onTakeover,
}: {
  isZh: boolean
  customerName: string
  duration: string
  pending: boolean
  ownerInstanceId: string | null
  onTakeover: () => void
}) {
  return (
    <div className="flex flex-1 flex-col px-5 py-5">
      <div className="text-center">
        <span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-secondary text-muted-foreground">
          <IconDeviceDesktop size={28} />
        </span>
        <h2 className="mt-4 text-lg font-semibold">
          {isZh ? '通话正在另一窗口处理' : 'Call is handled in another window'}
        </h2>
        <p className="mx-auto mt-2 max-w-[260px] text-xs leading-5 text-muted-foreground">
          {isZh
            ? '为避免重复振铃和占用麦克风，当前页面处于只读观察态。'
            : 'This page stays read-only to avoid duplicate ringing and microphone use.'}
        </p>
      </div>
      <div className="mt-6 rounded-xl border border-border p-4">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-full bg-muted">
            <IconPhoneIncoming size={17} />
          </span>
          <div>
            <p className="text-sm font-medium">{customerName || (isZh ? '当前通话' : 'Current call')}</p>
            <p className="mt-0.5 font-mono text-xs text-muted-foreground">
              {isZh ? '通话中' : 'On call'} · {duration}
            </p>
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-xs">
          <span className="text-muted-foreground">{isZh ? '当前控制窗口' : 'Controlling window'}</span>
          <span className="font-medium">
            {ownerInstanceId ? `${ownerInstanceId.slice(0, 12)}…` : (isZh ? '其他窗口' : 'Another window')}
          </span>
        </div>
      </div>
      <button
        type="button"
        onClick={onTakeover}
        disabled={pending}
        className="mt-auto h-11 rounded-lg bg-primary text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        {isZh ? '在此处接管' : 'Take control here'}
      </button>
      <p className="mt-3 text-center text-[10px] text-muted-foreground">
        {isZh ? '接管前将再次确认，原窗口会立即转为观察态。' : 'You will confirm before takeover. The other window becomes an observer.'}
      </p>
    </div>
  )
}

function ActivateBody({
  isZh,
  sip,
  micDenied,
  onActivate,
}: {
  isZh: boolean
  sip: boolean
  micDenied: boolean
  onActivate: () => void
}) {
  return (
    <div className="flex flex-1 flex-col px-5 py-5">
      <div className="text-center">
        <span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-primary/10 text-primary">
          <IconMicrophone size={28} />
        </span>
        <h2 className="mt-4 text-lg font-semibold">{isZh ? '启用通话' : 'Enable calling'}</h2>
        <p className="mx-auto mt-2 max-w-[260px] text-xs leading-5 text-muted-foreground">
          {sip
            ? (isZh ? '将使用当前 SIP 话机接听和通话。' : 'Your SIP phone will handle call audio.')
            : (isZh ? '检测麦克风和浏览器音频权限后即可接听和外呼。' : 'Check microphone access, then you can answer and dial.')}
        </p>
      </div>
      <button
        type="button"
        onClick={onActivate}
        className="mt-auto h-11 rounded-lg bg-primary text-sm font-medium text-primary-foreground"
      >
        {isZh ? '启用通话' : 'Enable calling'}
      </button>
      {micDenied ? (
        <p className="mt-3 text-center text-xs text-destructive" role="alert">
          {isZh ? '麦克风未授权，请检查 iframe allow 和浏览器设置' : 'Microphone access is blocked. Check iframe allow and browser settings.'}
        </p>
      ) : (
        <p className="mt-3 text-center text-[10px] text-muted-foreground">
          {isZh ? '启用后可切换坐席状态、设备和拨号。' : 'After enabling, you can change status, device, and dial.'}
        </p>
      )}
    </div>
  )
}

function StatusPill({
  label,
  dot,
  dropdown,
  options,
  disabled,
  isZh,
  onChange,
}: {
  label: string
  dot: string
  dropdown: boolean
  options: typeof CALL_STATUS_OPTIONS
  disabled: boolean
  isZh: boolean
  onChange: (status: AgentStatus) => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => dropdown && !disabled && setOpen((value) => !value)}
        className="flex items-center gap-1.5 rounded-full bg-muted px-2 py-1 text-[11px] font-medium disabled:opacity-70"
      >
        <span className={cn('h-1.5 w-1.5 rounded-full', dot)} />
        {label}
        {dropdown ? <IconChevronDown size={12} /> : null}
      </button>
      {open ? (
        <div className="absolute right-0 top-full z-20 mt-1 min-w-[128px] overflow-hidden rounded-lg border border-border bg-background py-1 shadow-lg">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                setOpen(false)
                onChange(option.value)
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-muted"
            >
              <span className={cn('h-1.5 w-1.5 rounded-full', option.dotClass)} />
              {isZh ? option.label : agentStatusEn(option.value)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function DeviceMenu({
  devices,
  currentType,
  label,
  locked,
  pending,
  isZh,
  onSelect,
}: {
  devices: AgentCallDevice[]
  currentType: CallDeviceType | null
  label: string
  locked: boolean
  pending: boolean
  isZh: boolean
  onSelect: (device: AgentCallDevice) => void
}) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={locked || pending}
        title={locked ? (isZh ? '通话结束后可切换设备' : 'Switch devices after the call ends') : undefined}
        onClick={() => !locked && setOpen((value) => !value)}
        className="flex items-center gap-2 disabled:cursor-not-allowed disabled:opacity-70"
      >
        <IconPhoneCall size={15} className="text-muted-foreground" />
        <span>{label}</span>
        {!locked ? <IconChevronDown size={12} className="text-muted-foreground" /> : null}
      </button>
      {open ? (
        <div className="absolute left-0 top-full z-20 mt-1 min-w-[180px] overflow-hidden rounded-lg border border-border bg-background py-1 shadow-lg">
          {devices.map((device) => (
            <button
              key={device.device_type}
              type="button"
              disabled={!device.available && device.device_type !== currentType}
              onClick={() => {
                setOpen(false)
                onSelect(device)
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-muted disabled:opacity-50"
            >
              {device.device_type === 'sip_phone'
                ? <IconDeviceLandlinePhone size={14} className="text-muted-foreground" />
                : <IconPhoneCall size={14} className="text-muted-foreground" />}
              {formatDeviceLabel(device, isZh)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function CallAction({
  icon,
  label,
  active = false,
  onClick,
}: {
  icon: ReactNode
  label: string
  active?: boolean
  onClick: () => void
}) {
  return (
    <button type="button" onClick={onClick} className="flex flex-col items-center gap-2 text-xs">
      <span className={cn(
        'grid h-11 w-11 place-items-center rounded-full border bg-background text-foreground [&_svg]:h-[18px] [&_svg]:w-[18px]',
        active ? 'border-primary bg-muted' : 'border-border',
      )}>
        {icon}
      </span>
      <span>{label}</span>
    </button>
  )
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function resolveHeaderStatus({
  isOwner,
  phase,
  agentStatus,
  isZh,
}: {
  isOwner: boolean
  phase: string
  agentStatus: AgentStatus
  isZh: boolean
}): { label: string; dot: string; dropdown: boolean } {
  if (!isOwner) return { label: isZh ? '观察态' : 'Observer', dot: 'bg-muted-foreground', dropdown: false }
  if (phase === 'incoming') return { label: isZh ? '来电' : 'Incoming', dot: 'bg-success', dropdown: false }
  if (phase === 'outbound_ringing') return { label: isZh ? '外呼中' : 'Calling', dot: 'bg-warning', dropdown: false }
  if (phase === 'on_call') return { label: isZh ? '通话中' : 'On call', dot: 'bg-destructive', dropdown: false }
  if (phase === 'wrap_up') return { label: isZh ? '整理中' : 'Wrap-up', dot: 'bg-warning', dropdown: false }
  const option = CALL_STATUS_OPTIONS.find((item) => item.value === agentStatus)
  return {
    label: option ? (isZh ? option.label : agentStatusEn(option.value)) : (isZh ? '就绪' : 'Ready'),
    dot: option?.dotClass ?? 'bg-success',
    dropdown: true,
  }
}

function resolveDeviceHint({
  isOwner,
  activated,
  phase,
  prefill,
  duration,
  isZh,
}: {
  isOwner: boolean
  activated: boolean
  phase: string
  prefill: boolean
  duration: string
  isZh: boolean
}): string {
  if (!isOwner) return isZh ? '另一窗口处理中' : 'Handled elsewhere'
  if (!activated) return isZh ? '待启用' : 'Activation required'
  if (phase === 'incoming') return isZh ? '来电振铃' : 'Ringing'
  if (phase === 'outbound_ringing') return `${isZh ? '正在呼叫' : 'Calling'} · ${duration}`
  if (phase === 'on_call') return isZh ? '已连接' : 'Connected'
  if (phase === 'wrap_up') return isZh ? '通话已结束' : 'Call ended'
  if (prefill) return isZh ? '号码待确认' : 'Number ready'
  return isZh ? '可外呼' : 'Ready to dial'
}

function formatDeviceLabel(device: AgentCallDevice, isZh: boolean): string {
  if (device.device_type === 'sip_phone' && device.extension_number) {
    return `${device.name} · ${device.extension_number}`
  }
  if (device.device_type === 'webrtc' && !isZh && device.name === 'Web 电话') return 'Web phone'
  return device.name
}

function initialsOf(name?: string, fallback = '?'): string {
  const text = (name || '').trim()
  return text ? text.slice(0, 1) : fallback
}

function agentStatusEn(status: string): string {
  return ({ ready: 'Ready', busy: 'Busy', break: 'Break', after_call_work: 'Wrap-up', offline: 'Offline' } as Record<string, string>)[status] ?? status
}
