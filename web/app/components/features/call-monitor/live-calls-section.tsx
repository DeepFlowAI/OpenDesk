'use client'
/**
 * "实时通话" section for the call-monitor page.
 *
 * Renders above today's data: a filter bar, the live-call table (with a
 * per-row three-dot monitor menu), an empty state, and — once a listen/whisper/
 * barge session is active — the supervisor variant of the universal call bar
 * plus the high-risk confirmation dialogs (barge / takeover / force-hangup).
 *
 * Data refreshes every 10s (full recalibration). Row actions are gated by
 * permission and by the phase capability matrix; unavailable items are disabled
 * with a reason, missing-permission items are hidden.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  IconDotsVertical,
  IconHeadphones,
  IconMicrophone,
  IconPhoneIncoming,
  IconPhoneOff,
  IconPhoneOutgoing,
  IconSearch,
  IconUserPlus,
  IconUserShare,
} from '@tabler/icons-react'
import { toast } from 'sonner'

import { EmployeeAvatar } from '@/app/components/features/session-reports/employee-avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useSocketStore } from '@/context/socket-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { formatDuration } from '@/utils/format-duration'
import { hasPermission } from '@/utils/permissions'
import type { CallPhase, InterventionMode, LiveCallRow } from '@/models/call-intervention'
import {
  useBargeCall,
  useEndTakeover,
  useForceHangupCall,
  useListenCall,
  useLiveCalls,
  useStopMonitoring,
  useTakeoverCall,
  useWhisperCall,
} from '@/service/use-call-intervention'
import { CallConfirmDialog } from '@/app/components/features/call-center/call-confirm-dialog'
import { InterventionReasonDialog } from './intervention-reason-dialog'
import { SupervisorCallBar, type MonitorSession } from './supervisor-call-bar'
import { useSupervisorLeg } from './use-supervisor-leg'

// Phase capability matrix mirrored from the backend: which intervention modes
// are allowed while the call is in each phase. Keeps the row menu's enable/
// disable state in sync with what the server will accept.
const PHASE_MATRIX: Record<CallPhase, Record<'listen' | 'whisper' | 'barge' | 'takeover' | 'force_hangup', boolean>> = {
  single: { listen: true, whisper: true, barge: true, takeover: true, force_hangup: true },
  customer_hold: { listen: true, whisper: true, barge: false, takeover: false, force_hangup: true },
  consulting: { listen: true, whisper: true, barge: false, takeover: false, force_hangup: true },
  three_way: { listen: true, whisper: true, barge: false, takeover: false, force_hangup: true },
  transferring: { listen: false, whisper: false, barge: false, takeover: false, force_hangup: false },
}

const TAKEOVER_REASONS = [
  { value: 'customer_escalation', labelKey: 'ws.records.callMonitor.takeoverReason.escalation' },
  { value: 'service_risk', labelKey: 'ws.records.callMonitor.takeoverReason.risk' },
  { value: 'agent_help', labelKey: 'ws.records.callMonitor.takeoverReason.help' },
  { value: 'other', labelKey: 'ws.records.callMonitor.reason.other' },
]

const FORCE_HANGUP_REASONS = [
  { value: 'violation', labelKey: 'ws.records.callMonitor.forceHangupReason.violation' },
  { value: 'security_risk', labelKey: 'ws.records.callMonitor.forceHangupReason.security' },
  { value: 'customer_request', labelKey: 'ws.records.callMonitor.forceHangupReason.customer' },
  { value: 'other', labelKey: 'ws.records.callMonitor.reason.other' },
]

const PHASE_ALL = '__all__'

type Props = {
  /** Reports edition gate — the whole section is hidden when disabled. */
  reportsEnabled: boolean
}

export function LiveCallsSection({ reportsEnabled }: Props) {
  const { locale } = useLocaleStore()
  const user = useAuthStore((s) => s.user)

  const canView = hasPermission(user, 'call.monitor.view')
  const canListen = hasPermission(user, 'call.monitor.listen')
  const canWhisper = hasPermission(user, 'call.monitor.whisper')
  const canBarge = hasPermission(user, 'call.monitor.barge')
  const canTakeover = hasPermission(user, 'call.monitor.takeover') && hasPermission(user, 'call.workspace.use')
  const canForceHangup = hasPermission(user, 'call.monitor.force_hangup')

  const enabled = reportsEnabled && canView
  const { data, isFetching, isError } = useLiveCalls(enabled)

  const [search, setSearch] = useState('')
  const [queue, setQueue] = useState(PHASE_ALL)
  const [phase, setPhase] = useState<CallPhase | typeof PHASE_ALL>(PHASE_ALL)

  const rows = data?.items ?? []

  const queueOptions = useMemo(() => {
    const names = new Set<string>()
    rows.forEach((r) => { if (r.queue_name) names.add(r.queue_name) })
    return Array.from(names).sort()
  }, [rows])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (queue !== PHASE_ALL && r.queue_name !== queue) return false
      if (phase !== PHASE_ALL && r.phase !== phase) return false
      if (!q) return true
      const agent = (r.agent.display_name ?? r.agent.name ?? '').toLowerCase()
      return agent.includes(q) || r.masked_customer_number.toLowerCase().includes(q)
    })
  }, [rows, search, queue, phase])

  // ── monitoring session state ──
  const [session, setSession] = useState<MonitorSession | null>(null)
  const [barExpanded, setBarExpanded] = useState(true)
  const [pendingMode, setPendingMode] = useState<InterventionMode | null>(null)
  const [monitorStart, setMonitorStart] = useState<number | null>(null)
  const [nowTick, setNowTick] = useState(() => Date.now())

  // Bumped by every session teardown (manual exit, takeover end, auto-exit on
  // dead target). Async mode flows (listen/whisper/barge/takeover negotiation)
  // capture it on entry; if it changed by the time the request resolves the
  // user already left — bail instead of resurrecting a bar over a released
  // media leg.
  const sessionGenRef = useRef(0)

  const listen = useListenCall()
  const whisper = useWhisperCall()
  const barge = useBargeCall()
  const takeover = useTakeoverCall()
  const forceHangup = useForceHangupCall()
  const endTakeover = useEndTakeover()
  const stop = useStopMonitoring()
  const supervisorLeg = useSupervisorLeg()
  const { socket } = useSocketStore()

  // Live monitor-duration ticker while a session is active.
  useEffect(() => {
    if (!session) return
    const id = window.setInterval(() => setNowTick(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [session])

  // Apply kernel ICE candidates for the supervisor's own leg. A distinct event
  // (`cc.supervisor.ice`, not `cc.webrtc.ice`) keeps a supervisor who is also an
  // agent from cross-applying candidates between their two legs.
  useEffect(() => {
    if (!socket) return
    const onSupervisorIce = (data: { candidate: RTCIceCandidateInit }) => {
      void supervisorLeg.applyRemoteIce(data.candidate)
    }
    socket.on('cc.supervisor.ice', onSupervisorIce)
    return () => {
      socket.off('cc.supervisor.ice', onSupervisorIce)
    }
  }, [socket, supervisorLeg])

  // Auto-exit monitoring when the target call ends / leaves the live list, per
  // the spec ("通话结束 → 当前监控会话自动结束"). Without this the bar keeps
  // pointing at a dead call_id, so a later whisper/barge builds a media leg on
  // an ended call and 404s. Guarded to a real, loaded list so a transient empty
  // poll or fetch error can't kill an active session.
  useEffect(() => {
    if (!session || isFetching || isError || !data) return
    // Takeover intentionally reassigns the call away from the original agent,
    // so it disappears from the monitored-agent list while the supervisor is
    // still the active media party. Keep B's leg until the customer hangs up
    // or B explicitly ends the taken-over call.
    if (session.mode === 'takeover') return
    if (rows.some((r) => r.call_id === session.callId)) return
    sessionGenRef.current += 1
    supervisorLeg.release()
    setSession(null)
    setPendingMode(null)
    toast(t('ws.records.callMonitor.targetEnded', locale))
  }, [session, rows, isFetching, isError, data, supervisorLeg, t, locale])

  // Restore a listen-only monitoring session after a page refresh. The backend
  // monitor lock is the source of truth; when it names me as holder in listen
  // mode, rebuild the bar (a plain listen holds no browser media leg, so this
  // is safe). Speaking modes (whisper/barge/takeover) lost their media leg
  // with the page and are not auto-restored — the row menu stays actionable
  // for sessions held by me (see RowMenu) so I can re-enter via listen.
  const myEmployeeId = user?.id
  useEffect(() => {
    if (session || isFetching || isError || !data || myEmployeeId == null) return
    const mine = rows.find(
      (r) =>
        r.current_supervisor?.employee_id === myEmployeeId &&
        r.current_supervisor?.mode === 'listen',
    )
    if (mine) beginSession(mine, 'listen')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, isFetching, isError, data, myEmployeeId])

  // Confirmation dialog state.
  const [confirmBarge, setConfirmBarge] = useState<LiveCallRow | null>(null)
  const [confirmTakeover, setConfirmTakeover] = useState<LiveCallRow | null>(null)
  const [confirmForceHangup, setConfirmForceHangup] = useState<LiveCallRow | null>(null)

  if (!enabled) return null

  const phaseLabel = (p: CallPhase) => t(`ws.records.callMonitor.phase.${p}`, locale)

  const beginSession = (row: LiveCallRow, mode: InterventionMode) => {
    setSession({
      callId: row.call_id,
      agentName: row.agent.display_name ?? row.agent.name ?? '',
      maskedCustomerNumber: row.masked_customer_number,
      phaseLabel: phaseLabel(row.phase),
      mode,
      talkSeconds: row.talk_duration_seconds,
      monitorSeconds: 0,
    })
    setMonitorStart(Date.now())
    setBarExpanded(true)
  }

  const failBanner = (err: unknown) => {
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status === 501) {
      toast.error(t('ws.records.callMonitor.notSupported', locale))
    } else {
      toast.error(t('ws.records.callMonitor.actionFailed', locale))
    }
  }

  // True when the session was torn down while an async flow (captured `gen`)
  // was still negotiating — the caller must bail. A leg re-negotiated after
  // the teardown's release is released again so nothing leaks.
  const superseded = (gen: number): boolean => {
    if (sessionGenRef.current === gen) return false
    supervisorLeg.release()
    return true
  }

  // Whisper / barge / takeover need the supervisor's own audio leg. Negotiate
  // it once (idempotent) before the speaking-mode request. Returns false when
  // the mic/handshake fails so the caller can abort cleanly.
  const ensureAudioLeg = async (callId: string): Promise<boolean> => {
    const legId = await supervisorLeg.ensureLeg(callId)
    if (!legId) {
      toast.error(t('ws.records.callMonitor.audioLegFailed', locale))
      return false
    }
    return true
  }

  const runMode = async (row: LiveCallRow, mode: 'listen' | 'whisper' | 'barge') => {
    const gen = sessionGenRef.current
    setPendingMode(mode)
    try {
      if (mode === 'listen') {
        await listen.mutateAsync(row.call_id)
      } else {
        if (!(await ensureAudioLeg(row.call_id))) return
        if (mode === 'whisper') await whisper.mutateAsync(row.call_id)
        else await barge.mutateAsync(row.call_id)
      }
      if (superseded(gen)) return
      beginSession(row, mode)
    } catch (err) {
      failBanner(err)
    } finally {
      setPendingMode(null)
    }
  }

  // Switch mode from within the supervisor bar (session already established).
  const switchMode = async (mode: 'listen' | 'whisper' | 'barge') => {
    if (!session) return
    if (mode === 'barge') {
      const row = rows.find((r) => r.call_id === session.callId)
      if (row) setConfirmBarge(row)
      return
    }
    setPendingMode(mode)
    const gen = sessionGenRef.current
    try {
      if (mode === 'listen') {
        await listen.mutateAsync(session.callId)
      } else {
        if (!(await ensureAudioLeg(session.callId))) return
        await whisper.mutateAsync(session.callId)
      }
      if (superseded(gen)) return
      setSession({ ...session, mode })
    } catch (err) {
      failBanner(err)
    } finally {
      setPendingMode(null)
    }
  }

  const doExit = async () => {
    if (!session) return
    try {
      await stop.mutateAsync(session.callId)
    } catch {
      // best-effort; still clear the local session
    }
    sessionGenRef.current += 1
    supervisorLeg.release()
    setSession(null)
    setMonitorStart(null)
    setPendingMode(null)
  }

  // Hang up a call the supervisor has taken over: ends the customer call, then
  // tears down the supervisor's own media leg and clears the in-call bar.
  const doEndTakeover = async () => {
    if (!session) return
    setPendingMode('takeover')
    try {
      await endTakeover.mutateAsync(session.callId)
    } catch {
      // best-effort; still tear down locally
    }
    sessionGenRef.current += 1
    supervisorLeg.release()
    setSession(null)
    setMonitorStart(null)
    setPendingMode(null)
  }

  const liveSession = session
    ? { ...session, monitorSeconds: monitorStart ? Math.floor((nowTick - monitorStart) / 1000) : 0 }
    : null

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-base font-semibold text-foreground">
        {t('ws.records.callMonitor.liveTitle', locale)}
      </h2>

      {liveSession && (
        <SupervisorCallBar
          session={liveSession}
          expanded={barExpanded}
          onToggleExpand={() => setBarExpanded((v) => !v)}
          pendingMode={pendingMode}
          canWhisper={canWhisper}
          canBarge={canBarge}
          canTakeover={canTakeover}
          canForceHangup={canForceHangup}
          onSwitchMode={switchMode}
          onTakeover={() => {
            const row = rows.find((r) => r.call_id === session?.callId)
            if (row) setConfirmTakeover(row)
          }}
          onForceHangup={() => {
            const row = rows.find((r) => r.call_id === session?.callId)
            if (row) setConfirmForceHangup(row)
          }}
          onExit={() => void doExit()}
          onEndTakeover={() => void doEndTakeover()}
          muted={supervisorLeg.muted}
          onToggleMute={supervisorLeg.toggleMute}
        />
      )}

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <IconSearch size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('ws.records.callMonitor.searchPlaceholder', locale)}
            aria-label={t('ws.records.callMonitor.searchPlaceholder', locale)}
            className="h-9 w-64 rounded-md border border-border bg-background pl-8 pr-3 text-sm outline-none focus:border-ring"
          />
        </div>
        <Select value={queue} onValueChange={(v) => setQueue(v ?? PHASE_ALL)}>
          <SelectTrigger className="h-9 w-44" aria-label={t('ws.records.callMonitor.colQueue', locale)}>
            <SelectValue placeholder={t('ws.records.callMonitor.filterQueue', locale)} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={PHASE_ALL}>{t('ws.records.callMonitor.filterAllQueues', locale)}</SelectItem>
            {queueOptions.map((name) => (
              <SelectItem key={name} value={name}>{name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={phase} onValueChange={(v) => setPhase((v as CallPhase | typeof PHASE_ALL) ?? PHASE_ALL)}>
          <SelectTrigger className="h-9 w-44" aria-label={t('ws.records.callMonitor.colPhase', locale)}>
            <SelectValue placeholder={t('ws.records.callMonitor.filterPhase', locale)} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={PHASE_ALL}>{t('ws.records.callMonitor.filterAllPhases', locale)}</SelectItem>
            {(['single', 'customer_hold', 'consulting', 'three_way', 'transferring'] as CallPhase[]).map((p) => (
              <SelectItem key={p} value={p}>{phaseLabel(p)}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {t('ws.records.callMonitor.errorLoad', locale)}
        </div>
      )}

      <LiveCallTable
        rows={filtered}
        loading={!data && isFetching}
        currentUserId={user?.id}
        canListen={canListen}
        canWhisper={canWhisper}
        canBarge={canBarge}
        canTakeover={canTakeover}
        canForceHangup={canForceHangup}
        busy={pendingMode !== null || !!session}
        onListen={(row) => void runMode(row, 'listen')}
        onWhisper={(row) => void runMode(row, 'whisper')}
        onBarge={(row) => setConfirmBarge(row)}
        onTakeover={(row) => setConfirmTakeover(row)}
        onForceHangup={(row) => setConfirmForceHangup(row)}
      />

      {/* Barge confirm */}
      <CallConfirmDialog
        open={confirmBarge !== null}
        title={t('ws.records.callMonitor.bargeConfirm.title', locale)}
        body={t('ws.records.callMonitor.bargeConfirm.body', locale)}
        lines={
          confirmBarge
            ? [
                { label: t('ws.records.callMonitor.colAgent', locale), value: confirmBarge.agent.display_name ?? confirmBarge.agent.name },
                { label: t('ws.records.callMonitor.colCustomer', locale), value: confirmBarge.masked_customer_number },
              ]
            : undefined
        }
        confirmLabel={t('ws.records.callMonitor.bargeConfirm.confirm', locale)}
        submitting={pendingMode === 'barge'}
        onClose={() => setConfirmBarge(null)}
        onConfirm={async () => {
          const row = confirmBarge
          setConfirmBarge(null)
          if (!row) return
          setPendingMode('barge')
          const gen = sessionGenRef.current
          try {
            if (!(await ensureAudioLeg(row.call_id))) return
            await barge.mutateAsync(row.call_id)
            if (superseded(gen)) return
            beginSession(row, 'barge')
          } catch (err) {
            failBanner(err)
          } finally {
            setPendingMode(null)
          }
        }}
      />

      {/* Takeover confirm */}
      <InterventionReasonDialog
        open={confirmTakeover !== null}
        title={t('ws.records.callMonitor.takeoverConfirm.title', locale)}
        body={
          confirmTakeover
            ? t('ws.records.callMonitor.takeoverConfirm.body', locale, {
                agent: confirmTakeover.agent.display_name ?? confirmTakeover.agent.name,
              })
            : ''
        }
        lines={
          confirmTakeover
            ? [
                { label: t('ws.records.callMonitor.colAgent', locale), value: confirmTakeover.agent.display_name ?? confirmTakeover.agent.name },
                { label: t('ws.records.callMonitor.colCustomer', locale), value: confirmTakeover.masked_customer_number },
              ]
            : undefined
        }
        reasonOptions={TAKEOVER_REASONS}
        confirmLabel={t('ws.records.callMonitor.takeoverConfirm.confirm', locale)}
        submitting={pendingMode === 'takeover'}
        onClose={() => setConfirmTakeover(null)}
        onConfirm={async (reason, note) => {
          const row = confirmTakeover
          if (!row) return
          setPendingMode('takeover')
          const gen = sessionGenRef.current
          try {
            if (!(await ensureAudioLeg(row.call_id))) return
            await takeover.mutateAsync({ callId: row.call_id, payload: { reason, note: note || undefined } })
            if (superseded(gen)) return
            toast.success(t('ws.records.callMonitor.takeoverSuccess', locale, {
              agent: row.agent.display_name ?? row.agent.name,
            }))
            setConfirmTakeover(null)
            // Supervisor is now the responsible party — switch the bar to the
            // in-call takeover variant (通话中 + 挂断). The media leg stays live
            // (reused, not rebuilt), so no navigation and no media gap.
            beginSession(row, 'takeover')
          } catch (err) {
            failBanner(err)
          } finally {
            setPendingMode(null)
          }
        }}
      />

      {/* Force-hangup confirm */}
      <InterventionReasonDialog
        open={confirmForceHangup !== null}
        title={t('ws.records.callMonitor.forceHangupConfirm.title', locale)}
        body={t('ws.records.callMonitor.forceHangupConfirm.body', locale)}
        lines={
          confirmForceHangup
            ? [
                { label: t('ws.records.callMonitor.colAgent', locale), value: confirmForceHangup.agent.display_name ?? confirmForceHangup.agent.name },
                { label: t('ws.records.callMonitor.colCustomer', locale), value: confirmForceHangup.masked_customer_number },
              ]
            : undefined
        }
        reasonOptions={FORCE_HANGUP_REASONS}
        confirmLabel={t('ws.records.callMonitor.forceHangupConfirm.confirm', locale)}
        submitting={pendingMode === 'force_hangup'}
        onClose={() => setConfirmForceHangup(null)}
        onConfirm={async (reason, note) => {
          const row = confirmForceHangup
          if (!row) return
          setPendingMode('force_hangup')
          try {
            await forceHangup.mutateAsync({ callId: row.call_id, payload: { reason, note: note || undefined } })
            toast.success(t('ws.records.callMonitor.forceHangupSuccess', locale))
            setConfirmForceHangup(null)
            sessionGenRef.current += 1
            supervisorLeg.release()
            if (session?.callId === row.call_id) setSession(null)
          } catch (err) {
            failBanner(err)
          } finally {
            setPendingMode(null)
          }
        }}
      />
    </section>
  )
}

// ───────────────────────── table ─────────────────────────

type TableProps = {
  rows: LiveCallRow[]
  loading?: boolean
  currentUserId?: number
  canListen: boolean
  canWhisper: boolean
  canBarge: boolean
  canTakeover: boolean
  canForceHangup: boolean
  busy: boolean
  onListen: (row: LiveCallRow) => void
  onWhisper: (row: LiveCallRow) => void
  onBarge: (row: LiveCallRow) => void
  onTakeover: (row: LiveCallRow) => void
  onForceHangup: (row: LiveCallRow) => void
}

function LiveCallTable({
  rows,
  loading,
  currentUserId,
  canListen,
  canWhisper,
  canBarge,
  canTakeover,
  canForceHangup,
  busy,
  onListen,
  onWhisper,
  onBarge,
  onTakeover,
  onForceHangup,
}: TableProps) {
  const { locale } = useLocaleStore()

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="overflow-x-auto">
        <div className="flex h-12 min-w-[960px] items-center gap-3 bg-muted/60 px-6 text-xs font-semibold text-muted-foreground">
          <div className="w-[220px]">{t('ws.records.callMonitor.colAgent', locale)}</div>
          <div className="w-[140px]">{t('ws.records.callMonitor.colCustomer', locale)}</div>
          <div className="w-[140px]">{t('ws.records.callMonitor.colDirection', locale)}</div>
          <div className="w-[120px]">{t('ws.records.callMonitor.colPhase', locale)}</div>
          <div className="w-[110px] text-center">{t('ws.records.callMonitor.colDuration', locale)}</div>
          <div className="flex-1">{t('ws.records.callMonitor.colSupervisor', locale)}</div>
          <div className="w-[56px] text-center">{t('ws.records.callMonitor.colActions', locale)}</div>
        </div>

        {loading ? (
          <div className="min-w-[960px] px-6 py-16 text-center text-sm text-muted-foreground">
            {t('ws.records.sessionReports.common.loading', locale)}
          </div>
        ) : rows.length === 0 ? (
          <div className="min-w-[960px] px-6 py-16 text-center text-sm text-muted-foreground">
            {t('ws.records.callMonitor.liveEmpty', locale)}
          </div>
        ) : (
          rows.map((row, index) => (
            <div
              key={row.call_id}
              className={cn(
                'flex h-14 min-w-[960px] select-text items-center gap-3 border-b border-border px-6 text-[13px] text-foreground last:border-b-0 hover:bg-muted/35',
                index % 2 === 1 ? 'bg-muted/20' : 'bg-background'
              )}
            >
              <div className="flex w-[220px] items-center gap-3">
                <EmployeeAvatar employee={row.agent} />
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="truncate font-semibold text-foreground">
                    {row.agent.display_name ?? row.agent.name}
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {row.agent.username ?? row.agent.email ?? '—'}
                  </span>
                </div>
              </div>
              <div className="w-[140px] font-mono text-xs">{row.masked_customer_number}</div>
              <div className="flex w-[140px] items-center gap-1.5">
                {row.direction === 'inbound' ? (
                  <IconPhoneIncoming size={14} className="text-success" />
                ) : (
                  <IconPhoneOutgoing size={14} className="text-primary" />
                )}
                <span>
                  {t(`ws.records.callMonitor.direction.${row.direction}`, locale)}
                  {row.queue_name ? ` · ${row.queue_name}` : ''}
                </span>
              </div>
              <div className="w-[120px]">{t(`ws.records.callMonitor.phase.${row.phase}`, locale)}</div>
              <div className="w-[110px] text-center font-mono tabular-nums">
                {formatDuration(row.talk_duration_seconds)}
              </div>
              <div className="flex-1 truncate text-muted-foreground">
                {row.current_supervisor
                  ? t('ws.records.callMonitor.supervisorMode', locale, {
                      name: row.current_supervisor.name,
                      mode: t(`ws.records.callMonitor.mode.${row.current_supervisor.mode}`, locale),
                    })
                  : '—'}
              </div>
              <div className="flex w-[56px] justify-center">
                <RowMenu
                  row={row}
                  isOwnCall={row.agent.id === currentUserId}
                  canListen={canListen}
                  canWhisper={canWhisper}
                  canBarge={canBarge}
                  canTakeover={canTakeover}
                  canForceHangup={canForceHangup}
                  busy={busy}
                  onListen={onListen}
                  onWhisper={onWhisper}
                  onBarge={onBarge}
                  onTakeover={onTakeover}
                  onForceHangup={onForceHangup}
                />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ───────────────────────── row menu ─────────────────────────

type RowMenuProps = {
  row: LiveCallRow
  isOwnCall: boolean
  canListen: boolean
  canWhisper: boolean
  canBarge: boolean
  canTakeover: boolean
  canForceHangup: boolean
  busy: boolean
  onListen: (row: LiveCallRow) => void
  onWhisper: (row: LiveCallRow) => void
  onBarge: (row: LiveCallRow) => void
  onTakeover: (row: LiveCallRow) => void
  onForceHangup: (row: LiveCallRow) => void
}

function RowMenu({
  row,
  isOwnCall,
  canListen,
  canWhisper,
  canBarge,
  canTakeover,
  canForceHangup,
  busy,
  onListen,
  onWhisper,
  onBarge,
  onTakeover,
  onForceHangup,
}: RowMenuProps) {
  const { locale } = useLocaleStore()

  const heldByOther = row.current_supervisor !== null
  // Disabled reason shared by all items when the call is unavailable to act on.
  const globalBlock = isOwnCall
    ? t('ws.records.callMonitor.disabled.ownCall', locale)
    : heldByOther
      ? t('ws.records.callMonitor.disabled.heldByOther', locale, { name: row.current_supervisor?.name ?? '' })
      : null

  const caps = PHASE_MATRIX[row.phase]

  const reasonFor = (op: 'listen' | 'whisper' | 'barge' | 'takeover' | 'force_hangup'): string | null => {
    if (globalBlock) return globalBlock
    if (!caps[op]) return t('ws.records.callMonitor.disabled.phase', locale)
    if (busy) return t('ws.records.callMonitor.disabled.busy', locale)
    return null
  }

  const items: {
    key: InterventionMode
    show: boolean
    labelKey: string
    icon: React.ReactNode
    danger?: boolean
    reason: string | null
    onSelect: () => void
  }[] = [
    { key: 'listen', show: canListen, labelKey: 'ws.records.callMonitor.mode.listen', icon: <IconHeadphones size={15} />, reason: reasonFor('listen'), onSelect: () => onListen(row) },
    { key: 'whisper', show: canWhisper, labelKey: 'ws.records.callMonitor.mode.whisper', icon: <IconMicrophone size={15} />, reason: reasonFor('whisper'), onSelect: () => onWhisper(row) },
    { key: 'barge', show: canBarge, labelKey: 'ws.records.callMonitor.mode.barge', icon: <IconUserPlus size={15} />, reason: reasonFor('barge'), onSelect: () => onBarge(row) },
    { key: 'takeover', show: canTakeover, labelKey: 'ws.records.callMonitor.mode.takeover', icon: <IconUserShare size={15} />, danger: true, reason: reasonFor('takeover'), onSelect: () => onTakeover(row) },
    { key: 'force_hangup', show: canForceHangup, labelKey: 'ws.records.callMonitor.mode.forceHangup', icon: <IconPhoneOff size={15} />, danger: true, reason: reasonFor('force_hangup'), onSelect: () => onForceHangup(row) },
  ]

  const visible = items.filter((i) => i.show)
  const hasAny = visible.length > 0
  const firstDanger = visible.find((i) => i.danger)?.key

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={!hasAny}
        aria-label={t('ws.records.callMonitor.rowMenuLabel', locale)}
        title={hasAny ? t('ws.records.callMonitor.rowMenuLabel', locale) : t('ws.records.callMonitor.disabled.noActions', locale)}
        className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
      >
        <IconDotsVertical size={16} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        {visible.map((item) => (
          <div key={item.key}>
            {item.danger && item.key === firstDanger && <DropdownMenuSeparator />}
            <DropdownMenuItem
              variant={item.danger ? 'destructive' : 'default'}
              disabled={item.reason !== null}
              title={item.reason ?? undefined}
              onClick={() => {
                if (item.reason !== null) return
                item.onSelect()
              }}
            >
              {item.icon}
              <span>{t(item.labelKey, locale)}</span>
            </DropdownMenuItem>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
