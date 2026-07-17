'use client'
/**
 * Supervisor variant of the universal call bar.
 *
 * Composes `UniversalCallBar` with the monitor operation set
 * (listen / whisper / barge / takeover / force-hangup). It shares only the
 * presentation shell with the agent variant — never the agent's business
 * actions (mute/hold/dial/transfer/consult/three-way/hang-up user). The
 * extension region is the bar's own inline downward area, not an overlay.
 */
import {
  IconHeadphones,
  IconMicrophone,
  IconMicrophoneOff,
  IconLogout,
  IconPhone,
  IconPhoneOff,
  IconUserPlus,
  IconUserShare,
} from '@tabler/icons-react'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { formatDuration } from '@/utils/format-duration'
import type { InterventionMode } from '@/models/call-intervention'
import { UniversalCallBar, type UniversalCallBarTone } from '@/app/components/features/call-center/universal-call-bar'

export type MonitorSession = {
  callId: string
  agentName: string
  maskedCustomerNumber: string
  phaseLabel: string
  /** Active monitor mode; a mode is "settled" once its request succeeds. */
  mode: InterventionMode
  /** Talk time of the monitored call, seconds. */
  talkSeconds: number
  /** How long this supervisor has been monitoring, seconds. */
  monitorSeconds: number
}

type Props = {
  session: MonitorSession
  expanded: boolean
  onToggleExpand: () => void
  /** Which mode's request is in flight (disables the others). */
  pendingMode: InterventionMode | null
  canWhisper: boolean
  canBarge: boolean
  canTakeover: boolean
  canForceHangup: boolean
  onSwitchMode: (mode: 'listen' | 'whisper' | 'barge') => void
  onTakeover: () => void
  onForceHangup: () => void
  onExit: () => void
  /** End the taken-over call (only meaningful in takeover mode). */
  onEndTakeover: () => void
  /** Supervisor mic muted — only meaningful in takeover mode. */
  muted?: boolean
  /** Toggle the supervisor mic — only meaningful in takeover mode. */
  onToggleMute?: () => void
}

const MODE_TONE: Record<InterventionMode, UniversalCallBarTone> = {
  listen: 'neutral',
  whisper: 'warning',
  barge: 'destructive',
  takeover: 'destructive',
  force_hangup: 'destructive',
}

function BarButton({
  icon,
  label,
  onClick,
  active,
  disabled,
  destructive,
  warning,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  active?: boolean
  disabled?: boolean
  destructive?: boolean
  warning?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cn(
        'flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        destructive
          ? 'border-destructive/30 text-destructive hover:bg-destructive/10'
          : warning
            ? 'border-warning/40 text-warning hover:bg-warning/10'
            : active
              ? 'border-primary/40 bg-primary/10 text-primary'
              : 'border-border bg-background/60 text-foreground/80 hover:bg-background',
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

export function SupervisorCallBar({
  session,
  expanded,
  onToggleExpand,
  pendingMode,
  canWhisper,
  canBarge,
  canTakeover,
  canForceHangup,
  onSwitchMode,
  onTakeover,
  onForceHangup,
  onExit,
  onEndTakeover,
  muted = false,
  onToggleMute,
}: Props) {
  const { locale } = useLocaleStore()
  const busy = pendingMode !== null

  // After a takeover the supervisor IS the party on the call: the bar becomes a
  // minimal in-call variant (通话中 + customer + duration + 挂断), with none of
  // the monitor mode-switch actions. The media leg is reused, not rebuilt.
  if (session.mode === 'takeover') {
    const callSeconds = session.talkSeconds + session.monitorSeconds
    return (
      <UniversalCallBar
        tone="active"
        expanded={false}
        onToggleExpand={() => {}}
        status={
          <>
            <span className="flex shrink-0 items-center gap-1.5 text-sm font-semibold">
              <IconPhone size={16} />
              {t('ws.records.callMonitor.takeoverInCall', locale)}
            </span>
            <span className="min-w-0 truncate text-sm text-foreground/70">
              {session.maskedCustomerNumber}
            </span>
            <span className="shrink-0 font-mono text-xs tabular-nums text-foreground/60">
              {formatDuration(callSeconds)}
            </span>
          </>
        }
        mainActions={
          <>
            <BarButton
              icon={muted ? <IconMicrophoneOff size={15} /> : <IconMicrophone size={15} />}
              label={t(muted ? 'ws.callbar.unmute' : 'ws.callbar.mute', locale)}
              onClick={() => onToggleMute?.()}
              active={muted}
              disabled={busy}
            />
            <button
              type="button"
              onClick={onEndTakeover}
              disabled={busy}
              title={t('ws.records.callMonitor.hangUp', locale)}
              aria-label={t('ws.records.callMonitor.hangUp', locale)}
              className="flex h-8 items-center gap-1.5 rounded-md border border-destructive/30 px-2.5 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <IconPhoneOff size={15} />
              <span>{t('ws.records.callMonitor.hangUp', locale)}</span>
            </button>
          </>
        }
      />
    )
  }

  const modeLabel = t(`ws.records.callMonitor.mode.${session.mode}`, locale)

  const status = (
    <>
      <span className="flex shrink-0 items-center gap-1.5 text-sm font-semibold">
        <IconHeadphones size={16} />
        {t('ws.records.callMonitor.monitoring', locale)}
      </span>
      <span className="min-w-0 truncate text-sm text-foreground/70">
        {t('ws.records.callMonitor.monitorTarget', locale, {
          agent: session.agentName,
          number: session.maskedCustomerNumber,
        })}
      </span>
      <span className="shrink-0 text-xs text-foreground/60">{session.phaseLabel}</span>
      <span className="shrink-0 font-mono text-xs tabular-nums text-foreground/60">
        {formatDuration(session.talkSeconds)}
      </span>
      <span className="shrink-0 rounded bg-background/60 px-1.5 py-0.5 text-xs font-medium">
        {modeLabel}
      </span>
      <span className="shrink-0 font-mono text-xs tabular-nums text-foreground/50">
        {t('ws.records.callMonitor.monitorDuration', locale, {
          duration: formatDuration(session.monitorSeconds),
        })}
      </span>
    </>
  )

  const mainActions = (
    <button
      type="button"
      onClick={onExit}
      title={t('ws.records.callMonitor.exitMonitor', locale)}
      aria-label={t('ws.records.callMonitor.exitMonitor', locale)}
      className="flex h-8 items-center gap-1.5 rounded-md border border-border bg-background/60 px-2.5 text-xs font-medium text-foreground/80 transition-colors hover:bg-background"
    >
      <IconLogout size={15} />
      <span>{t('ws.records.callMonitor.exitMonitor', locale)}</span>
    </button>
  )

  // Fixed order: listen / whisper / barge / takeover / force-hangup.
  const extension = (
    <>
      <BarButton
        icon={<IconHeadphones size={15} />}
        label={t('ws.records.callMonitor.mode.listen', locale)}
        onClick={() => onSwitchMode('listen')}
        active={session.mode === 'listen'}
        disabled={busy}
      />
      {canWhisper && (
        <BarButton
          icon={<IconMicrophone size={15} />}
          label={t('ws.records.callMonitor.mode.whisper', locale)}
          onClick={() => onSwitchMode('whisper')}
          active={session.mode === 'whisper'}
          warning
          disabled={busy}
        />
      )}
      {canBarge && (
        <BarButton
          icon={<IconUserPlus size={15} />}
          label={t('ws.records.callMonitor.mode.barge', locale)}
          onClick={() => onSwitchMode('barge')}
          active={session.mode === 'barge'}
          destructive
          disabled={busy}
        />
      )}
      {canTakeover && (
        <BarButton
          icon={<IconUserShare size={15} />}
          label={t('ws.records.callMonitor.mode.takeover', locale)}
          onClick={onTakeover}
          destructive
          disabled={busy}
        />
      )}
      {canForceHangup && (
        <BarButton
          icon={<IconPhoneOff size={15} />}
          label={t('ws.records.callMonitor.mode.forceHangup', locale)}
          onClick={onForceHangup}
          destructive
          disabled={busy}
        />
      )}
    </>
  )

  return (
    <UniversalCallBar
      tone={MODE_TONE[session.mode]}
      status={status}
      mainActions={mainActions}
      extension={extension}
      expanded={expanded}
      onToggleExpand={onToggleExpand}
    />
  )
}
