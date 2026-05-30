'use client'

import {
  IconCheck,
  IconPhone,
  IconPhoneIncoming,
  IconPhoneOff,
  IconPhoneOutgoing,
} from '@tabler/icons-react'

import {
  formatCallDuration,
  useCallCenterRuntime,
} from '@/context/call-center-runtime'
import { cn } from '@/lib/utils'

type GlobalCallBarProps = {
  hidden?: boolean
}

export function GlobalCallBar({ hidden = false }: GlobalCallBarProps) {
  const {
    phase,
    incoming,
    callStart,
    now,
    leg,
    accept,
    reject,
    hangup,
    completeWrapUp,
  } = useCallCenterRuntime()

  if (hidden || phase === 'idle' || phase === 'mic_check' || phase === 'mic_denied') {
    return null
  }
  if (!incoming && phase !== 'wrap_up') return null

  const duration = formatCallDuration(callStart ? now - callStart : 0)
  const isIncoming = phase === 'incoming'
  const isOutbound = incoming?.direction === 'outbound'
  const number = isOutbound ? incoming?.to : incoming?.from
  const label =
    phase === 'incoming'
      ? '来电'
      : phase === 'outbound_ringing'
        ? '外呼中'
        : phase === 'on_call'
          ? '通话中'
          : '整理中'

  const toneClass =
    phase === 'incoming'
      ? 'border-amber-200 bg-amber-50 text-amber-900'
      : phase === 'outbound_ringing'
        ? 'border-sky-200 bg-sky-50 text-sky-900'
        : phase === 'on_call'
          ? 'border-green-200 bg-green-50 text-green-900'
          : 'border-border bg-muted text-foreground'

  const icon =
    phase === 'incoming'
      ? <IconPhoneIncoming size={15} className="animate-pulse text-amber-700" />
      : phase === 'outbound_ringing'
        ? <IconPhoneOutgoing size={15} className="animate-pulse text-sky-700" />
        : phase === 'on_call'
          ? <IconPhone size={15} className="text-green-700" />
          : <IconCheck size={15} className="text-amber-700" />

  return (
    <div
      className={cn(
        'flex h-9 min-w-0 max-w-[min(640px,calc(100vw-10rem))] items-center gap-2 rounded-md border px-2.5 text-xs shadow-sm',
        toneClass,
      )}
    >
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white/80">
        {icon}
      </span>
      <span className="shrink-0 font-semibold">{label}</span>
      {phase !== 'wrap_up' && (
        <span className="min-w-0 truncate text-foreground/80">
          {number || '未知号码'}
        </span>
      )}
      <span className="shrink-0 font-mono tabular-nums text-foreground/70">
        {duration}
      </span>
      <div className="ml-1 flex shrink-0 items-center gap-1">
        {isIncoming ? (
          <>
            <button
              type="button"
              onClick={() => void reject()}
              disabled={leg.state === 'connecting'}
              title="拒接"
              className="grid h-7 w-7 place-items-center rounded-full bg-red-500 text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <IconPhoneOff size={14} />
            </button>
            <button
              type="button"
              onClick={() => void accept()}
              disabled={leg.state === 'connecting'}
              title={leg.state === 'connecting' ? '正在接通...' : '接听'}
              className="grid h-7 w-7 place-items-center rounded-full bg-green-500 text-white transition-colors hover:bg-green-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <IconPhone size={14} />
            </button>
          </>
        ) : phase === 'wrap_up' ? (
          <button
            type="button"
            onClick={completeWrapUp}
            title="完成整理"
            className="grid h-7 w-7 place-items-center rounded-full bg-green-500 text-white transition-colors hover:bg-green-600"
          >
            <IconCheck size={14} />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void hangup()}
            title={phase === 'outbound_ringing' ? '取消外呼' : '挂断'}
            className="grid h-7 w-7 place-items-center rounded-full bg-red-500 text-white transition-colors hover:bg-red-600"
          >
            <IconPhoneOff size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
