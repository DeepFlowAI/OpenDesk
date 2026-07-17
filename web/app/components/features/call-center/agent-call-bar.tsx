'use client'
/**
 * Agent variant of the universal call bar.
 *
 * Composes `UniversalCallBar` with the agent's in-call operations driven by the
 * `callControl` state machine on the call-center runtime: mute, hold, transfer,
 * consult, add-participant, end-all, hang-up. The extension region is the bar's
 * own inline downward area (via UniversalCallBar) — never an overlay.
 *
 * DTMF is intentionally NOT here: it reuses the single dial-pad entry at the top
 * of the workspace, per the requirement of one dial-pad entry point.
 */
import { useState } from 'react'
import {
  IconArrowsExchange,
  IconMicrophone,
  IconMicrophoneOff,
  IconPhoneOff,
  IconPlayerPause,
  IconPlayerPlay,
  IconUserPlus,
  IconUsersGroup,
} from '@tabler/icons-react'

import { useAuthStore } from '@/context/auth-store'
import { useCallCenterRuntime, formatCallDuration } from '@/context/call-center-runtime'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { hasPermission } from '@/utils/permissions'
import type { CallControlTarget } from '@/service/use-call-center'
import {
  CallTargetPickerDialog,
  type CallTargetPickerMode,
  type PickedTarget,
} from './call-target-picker-dialog'
import { CallConfirmDialog } from './call-confirm-dialog'
import {
  UniversalCallBar,
  type UniversalCallBarTone,
} from './universal-call-bar'

type Props = {
  /** Compact main-row-only rendering (e.g. inside a tight global bar). */
  compact?: boolean
  trailing?: React.ReactNode
}

/** A small labelled icon button used across the bar. */
function BarButton({
  icon,
  label,
  onClick,
  active,
  disabled,
  destructive,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  active?: boolean
  disabled?: boolean
  destructive?: boolean
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

export function AgentCallBar({ compact = false, trailing }: Props) {
  const { callControl, hangup, incoming, callStart, now } = useCallCenterRuntime()
  const { locale } = useLocaleStore()
  const currentUser = useAuthStore((s) => s.user)

  const canTransfer = hasPermission(currentUser, 'call.operation.transfer')
  const canConsult = hasPermission(currentUser, 'call.operation.consult')
  const canConference = hasPermission(currentUser, 'call.operation.conference')

  const [expanded, setExpanded] = useState(false)
  const [picker, setPicker] = useState<CallTargetPickerMode | null>(null)
  const [confirmTransfer, setConfirmTransfer] = useState<PickedTarget | null>(null)
  const [confirmEndAll, setConfirmEndAll] = useState(false)

  const {
    mode,
    muted,
    holdStart,
    consultTarget,
    pending,
    toggleMute,
    toggleHold,
    submitTransfer,
    beginConsult,
    finishConsult,
    addParticipant,
    endAll,
    leaveConference,
  } = callControl

  const number = incoming?.direction === 'outbound' ? incoming?.to : incoming?.from
  const duration = formatCallDuration(callStart ? now - callStart : 0)

  // Consult/conference must stay expanded so required controls aren't hidden.
  const expandLocked =
    mode === 'consult_ringing' ||
    mode === 'consult_active' ||
    mode === 'conference' ||
    mode === 'conference_ringing'
  const isExpanded = expanded || expandLocked

  const tone: UniversalCallBarTone =
    mode === 'hold' || mode === 'consult_ringing' || mode === 'consult_active'
      ? 'warning'
      : mode === 'transferring' || mode === 'conference_ringing'
        ? 'neutral'
        : 'active'

  const statusLabel = (() => {
    switch (mode) {
      case 'hold':
        return t('ws.callbar.statusHold', locale)
      case 'consult_ringing':
        return t('ws.callbar.statusConsultRinging', locale, { name: consultTarget?.target_name ?? '' })
      case 'consult_active':
        return t('ws.callbar.statusConsultActive', locale, { name: consultTarget?.target_name ?? '' })
      case 'conference':
        return t('ws.callbar.statusConference', locale, { count: 3 })
      case 'conference_ringing':
        return t('ws.callbar.statusConferenceRinging', locale)
      case 'transferring':
        return t('ws.callbar.statusTransferring', locale, { name: '' })
      default:
        return t('ws.callbar.statusInCall', locale)
    }
  })()

  const status = (
    <>
      <span className="shrink-0 text-sm font-semibold">{statusLabel}</span>
      {!compact && (
        <span className="min-w-0 truncate text-sm text-foreground/70">{number || t('ws.call.unknownNumber', locale)}</span>
      )}
      <span className="shrink-0 font-mono text-xs tabular-nums text-foreground/60">{duration}</span>
      {mode === 'hold' && holdStart && (
        <span className="shrink-0 font-mono text-xs tabular-nums text-warning">
          {formatCallDuration(now - holdStart)}
        </span>
      )}
    </>
  )

  const inConsult = mode === 'consult_ringing' || mode === 'consult_active'

  // Main-row high-frequency actions.
  const mainActions = (
    <>
      <BarButton
        icon={muted ? <IconMicrophoneOff size={15} /> : <IconMicrophone size={15} />}
        label={muted ? t('ws.callbar.muted', locale) : t('ws.callbar.mute', locale)}
        onClick={toggleMute}
        active={muted}
      />
      {!inConsult && mode !== 'conference' && mode !== 'conference_ringing' && (
        <BarButton
          icon={mode === 'hold' ? <IconPlayerPlay size={15} /> : <IconPlayerPause size={15} />}
          label={mode === 'hold' ? t('ws.callbar.resume', locale) : t('ws.callbar.hold', locale)}
          onClick={() => void toggleHold()}
          active={mode === 'hold'}
          disabled={pending === 'hold'}
        />
      )}
      <button
        type="button"
        onClick={() => void hangup()}
        title={t('ws.callbar.hangupUser', locale)}
        aria-label={t('ws.callbar.hangupUser', locale)}
        className="grid h-8 w-8 place-items-center rounded-md bg-destructive/90 text-destructive-foreground transition-colors hover:bg-destructive"
      >
        <IconPhoneOff size={15} />
      </button>
    </>
  )

  // Inline extension: collaboration + danger operations by state.
  const extension = (
    <>
      {inConsult ? (
        <BarButton
          icon={<IconArrowsExchange size={15} />}
          label={t('ws.callbar.endConsult', locale)}
          onClick={() => void finishConsult()}
          active
          disabled={pending === 'consult_end'}
        />
      ) : mode === 'conference' || mode === 'conference_ringing' ? (
        <>
          {mode === 'conference' && (
            <BarButton
              icon={<IconUsersGroup size={15} />}
              label={t('ws.callbar.leaveConference', locale)}
              onClick={() => void leaveConference()}
              disabled={pending === 'conf_leave'}
            />
          )}
          <BarButton
            icon={<IconPhoneOff size={15} />}
            label={t('ws.callbar.endAll', locale)}
            onClick={() => setConfirmEndAll(true)}
            destructive
            disabled={pending === 'conf_end_all'}
          />
        </>
      ) : (
        <>
          {canTransfer && (
            <BarButton
              icon={<IconArrowsExchange size={15} />}
              label={t('ws.callbar.transfer', locale)}
              onClick={() => setPicker('transfer')}
              disabled={mode === 'transferring'}
            />
          )}
          {canConsult && (
            <BarButton
              icon={<IconUserPlus size={15} />}
              label={t('ws.callbar.consult', locale)}
              onClick={() => setPicker('consult')}
              disabled={mode === 'transferring'}
            />
          )}
          {canConference && (
            <BarButton
              icon={<IconUsersGroup size={15} />}
              label={t('ws.callbar.addParticipant', locale)}
              onClick={() => setPicker('conference')}
              disabled={mode === 'transferring'}
            />
          )}
        </>
      )}
    </>
  )

  const hasExtension =
    inConsult ||
    mode === 'conference' ||
    mode === 'conference_ringing' ||
    canTransfer ||
    canConsult ||
    canConference

  return (
    <>
      <UniversalCallBar
        tone={tone}
        status={status}
        mainActions={mainActions}
        extension={hasExtension ? extension : undefined}
        expanded={isExpanded}
        onToggleExpand={() => setExpanded((v) => !v)}
        expandLocked={expandLocked}
        trailing={trailing}
      />

      <CallTargetPickerDialog
        open={picker !== null}
        mode={picker ?? 'transfer'}
        allowQueue={picker === 'transfer'}
        submitting={pending === 'transfer' || pending === 'consult' || pending === 'conf_add'}
        onClose={() => setPicker(null)}
        onSubmit={(target) => {
          if (picker === 'transfer') {
            // Direct transfer needs a second confirm before it leaves the call.
            setConfirmTransfer(target)
            setPicker(null)
          } else if (picker === 'consult') {
            void beginConsult({
              target_type: target.target_type === 'external' ? 'external' : 'employee',
              target_id: target.target_id,
              number: target.number,
              target_name: target.target_name,
            })
            setPicker(null)
          } else if (picker === 'conference') {
            void addParticipant({
              target_type: target.target_type === 'external' ? 'external' : 'employee',
              target_id: target.target_id,
              number: target.number,
              target_name: target.target_name,
            })
            setPicker(null)
          }
        }}
      />

      <CallConfirmDialog
        open={confirmTransfer !== null}
        title={t('ws.callbar.confirmTransferTitle', locale)}
        body={t('ws.callbar.confirmTransferBody', locale)}
        lines={confirmTransfer ? [{ label: t('ws.callbar.transfer', locale), value: confirmTransfer.target_name }] : undefined}
        confirmLabel={t('ws.callbar.confirmTransferConfirm', locale)}
        submitting={pending === 'transfer'}
        onClose={() => setConfirmTransfer(null)}
        onConfirm={() => {
          if (!confirmTransfer) return
          const target: CallControlTarget = {
            target_type: confirmTransfer.target_type,
            target_id: confirmTransfer.target_id,
            number: confirmTransfer.number,
          }
          void submitTransfer(target, confirmTransfer.target_name)
          setConfirmTransfer(null)
        }}
      />

      <CallConfirmDialog
        open={confirmEndAll}
        title={t('ws.callbar.confirmEndAllTitle', locale)}
        body={t('ws.callbar.confirmEndAllBody', locale)}
        lines={[{ label: t('ws.callbar.addParticipant', locale), value: t('ws.callbar.confirmEndAllParticipants', locale, { count: 3 }) }]}
        confirmLabel={t('ws.callbar.confirmEndAllConfirm', locale)}
        submitting={pending === 'conf_end_all'}
        onClose={() => setConfirmEndAll(false)}
        onConfirm={() => {
          void endAll()
          setConfirmEndAll(false)
        }}
      />
    </>
  )
}
