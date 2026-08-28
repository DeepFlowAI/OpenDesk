'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { IconAlertTriangle, IconArrowLeft, IconPlayerPause, IconPlayerPlay, IconPlayerStop } from '@tabler/icons-react'
import { toast } from 'sonner'

import { PersonalOutboundRecordingField } from '@/app/components/features/call-center/personal-outbound-recording-field'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Input } from '@/components/ui/input'
import { useLocaleStore } from '@/context/locale-store'
import {
  useCurrentPersonalAutoOutboundSession,
  useControlPersonalAutoOutboundSession,
  usePersonalAutoOutboundConfig,
  useRemovePersonalOutboundRecording,
  useSavePersonalOutboundOpeningScript,
  useStartPersonalAutoOutboundSession,
  useUploadPersonalOutboundRecording,
} from '@/service/use-personal-auto-outbound'
import { t } from '@/utils/i18n'

import { isPersonalAutoOutboundIncoming } from '@/lib/auto-outbound-incoming'
import type { IncomingCall } from '@/lib/call-session-reducer'

import { resolvePersonalAutoOutboundFormState } from './personal-auto-outbound-form-state'
import { PersonalAutoOutboundTaskPop } from './personal-auto-outbound-task-pop'
import {
  assignActiveCallsToSlots,
  buildLaneSlots,
  endedCallCount,
  isLaneActiveCall,
  nextClearingSlots,
  resolveRunningBadge,
  type ClearingSlot,
  type LaneAssignment,
} from './personal-auto-outbound-lanes'
import { PersonalAutoOutboundLanes } from './personal-auto-outbound-lane-list'

export function PersonalAutoOutboundView({
  initialTaskId,
  agentReady,
  deviceAvailable,
  incoming = null,
  phase = 'idle',
  onWrapupSubmitted,
}: {
  initialTaskId: number | null
  agentReady: boolean
  deviceAvailable: boolean
  incoming?: IncomingCall | null
  phase?: string
  onWrapupSubmitted?: () => void
}) {
  const { locale } = useLocaleStore()
  const configQuery = usePersonalAutoOutboundConfig()
  const sessionQuery = useCurrentPersonalAutoOutboundSession()
  const uploadRecording = useUploadPersonalOutboundRecording()
  const removeRecording = useRemovePersonalOutboundRecording()
  const saveOpeningScript = useSavePersonalOutboundOpeningScript()
  const startSession = useStartPersonalAutoOutboundSession()
  const controlSession = useControlPersonalAutoOutboundSession()
  const [taskId, setTaskId] = useState('')
  const [phoneId, setPhoneId] = useState('')
  const [fallbackGroupId, setFallbackGroupId] = useState('')
  const [concurrency, setConcurrency] = useState(4)
  const [openingScript, setOpeningScript] = useState('')
  const [stopOpen, setStopOpen] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const assignmentRef = useRef<LaneAssignment>({})
  const clearingRef = useRef<Record<number, ClearingSlot>>({})
  const [laneTick, setLaneTick] = useState(0)

  const config = configQuery.data
  const session = sessionQuery.data?.session ?? null
  const metrics = sessionQuery.data?.metrics ?? EMPTY_METRICS
  const calls = useMemo(() => sessionQuery.data?.calls ?? [], [sessionQuery.data?.calls])
  const locked = Boolean(session)

  useEffect(() => {
    if (!config) return

    const resolved = resolvePersonalAutoOutboundFormState(config, session, initialTaskId)
    if (session) {
      setTaskId(resolved.taskId)
      setPhoneId(resolved.phoneId)
      setFallbackGroupId(resolved.fallbackGroupId)
      setConcurrency(resolved.concurrency)
      return
    }

    if (!taskId) {
      setTaskId(resolved.taskId)
      if (resolved.initialTaskMissing) toast.info(t('personalAuto.invalidTask', locale))
    }
    if (!phoneId) setPhoneId(resolved.phoneId)
  }, [config, initialTaskId, locale, phoneId, session, taskId])

  useEffect(() => {
    if (!config || session) return
    setOpeningScript(config.recordings.opening?.script_text ?? '')
  }, [config, session])

  const fallback = useMemo(
    () => config?.fallback_groups.find((group) => String(group.id) === fallbackGroupId),
    [config?.fallback_groups, fallbackGroupId],
  )
  const effectiveConcurrency = concurrency > 1 && (!fallback || fallback.ready_agent_count === 0) ? 1 : concurrency
  const complete = Boolean(
    taskId &&
      phoneId &&
      config?.recordings.opening &&
      config.recordings.closing &&
      config.has_enabled_prescreen_intents &&
      agentReady &&
      deviceAvailable,
  )

  const savedOpeningScript = config?.recordings.opening?.script_text ?? ''
  const openingScriptError =
    openingScript.trim().length > 200 ? t('personalAuto.openingScriptTooLong', locale) : null

  const persistOpeningScript = async (opts?: { afterUpload?: boolean; silent?: boolean }) => {
    if (locked || openingScriptError) return
    if (!opts?.afterUpload && !config?.recordings.opening) return
    const next = openingScript.trim()
    if (next === (savedOpeningScript ?? '').trim()) return
    try {
      await saveOpeningScript.mutateAsync(next || null)
      if (!opts?.silent) toast.success(t('personalAuto.openingScriptSaved', locale))
    } catch {
      if (!opts?.silent) toast.error(t('personalAuto.openingScriptSaveFailed', locale))
    }
  }

  const upload = async (type: 'opening' | 'closing', file: File) => {
    try {
      await uploadRecording.mutateAsync({ type, file })
      toast.success(t(type === 'opening' ? 'personalAuto.openingSaved' : 'personalAuto.closingSaved', locale))
      if (type === 'opening') await persistOpeningScript({ afterUpload: true, silent: true })
    } catch {
      toast.error(t('personalAuto.recordingSaveFailed', locale))
      throw new Error('recording upload failed')
    }
  }

  const remove = async (type: 'opening' | 'closing') => {
    try {
      await removeRecording.mutateAsync(type)
      toast.success(t('personalAuto.recordingRemoved', locale))
    } catch {
      toast.error(t('personalAuto.recordingRemoveFailed', locale))
    }
  }

  const start = async () => {
    if (!complete) return
    try {
      await startSession.mutateAsync({
        task_id: Number(taskId),
        outbound_phone_number_id: phoneId,
        fallback_group_id: fallbackGroupId ? Number(fallbackGroupId) : null,
        configured_concurrency: concurrency,
      })
      toast.success(t('personalAuto.started', locale))
    } catch {
      toast.error(t('personalAuto.startFailed', locale))
    }
  }

  useEffect(() => {
    if (!session) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [session])

  const control = async (action: 'pause' | 'resume' | 'stop') => {
    if (!session) return
    try {
      await controlSession.mutateAsync({ sessionId: session.id, action })
      const successKey = action === 'pause' ? 'personalAuto.paused' : action === 'resume' ? 'personalAuto.resumed' : 'personalAuto.stopped'
      toast.success(t(successKey, locale))
      if (action === 'stop') setStopOpen(false)
    } catch {
      toast.error(t('personalAuto.controlFailed', locale))
    }
  }

  useEffect(() => {
    if (!session) {
      assignmentRef.current = {}
      clearingRef.current = {}
      return
    }
    const activeIds = calls.filter(isLaneActiveCall).map((item) => item.id)
    const nextAssignment = assignActiveCallsToSlots(
      assignmentRef.current,
      activeIds,
      session.effective_concurrency,
    )
    const callsById = new Map(calls.map((item) => [item.id, item]))
    clearingRef.current = nextClearingSlots({
      previousAssignment: assignmentRef.current,
      nextAssignment,
      previousClearing: clearingRef.current,
      callsById,
      now: Date.now(),
    })
    assignmentRef.current = nextAssignment
    setLaneTick((value) => value + 1)
  }, [calls, session])

  if (configQuery.isPending || sessionQuery.isPending) return <div className="h-full animate-pulse bg-muted/40" />
  if (configQuery.isError || sessionQuery.isError || !config) return <div className="p-6 text-sm text-destructive">{t('personalAuto.loadFailed', locale)}</div>

  const selectedTask = config.tasks.find((item) => String(item.id) === taskId)
  const selectedPhone = config.phone_numbers.find((item) => item.id === phoneId)
  const showTaskPop =
    isPersonalAutoOutboundIncoming(incoming) &&
    (phase === 'incoming' || phase === 'on_call' || phase === 'wrap_up')
  const onHumanCall = showTaskPop || sessionQuery.data?.gate_reason === 'primary_human'
  const badge = session
    ? resolveRunningBadge({
        session,
        ringingCurrent: metrics.ringing_current,
        screeningCurrent: metrics.screening_current,
        onHumanCall,
      })
    : { key: 'personalAuto.status.notStarted', tone: 'muted' as const }
  const badgeClass =
    badge.tone === 'info'
      ? 'bg-info/10 text-info'
      : badge.tone === 'warning'
        ? 'bg-warning/20 text-foreground'
        : badge.tone === 'success'
          ? 'bg-success/10 text-success'
          : 'bg-muted text-muted-foreground'
  const lanes = session
    ? buildLaneSlots({
        slotCount: session.effective_concurrency,
        assignment: assignmentRef.current,
        clearing: clearingRef.current,
        callsById: new Map(calls.map((item) => [item.id, item])),
        now: now + laneTick * 0,
      })
    : []
  const hideGateAlert = sessionQuery.data?.gate_reason === 'screening' || sessionQuery.data?.gate_reason === 'primary_human'

  return (
    <div className="h-full overflow-y-auto bg-background p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href="/workspace/call?view=outbound-tasks" aria-label={t('personalAuto.back', locale)} className="inline-flex h-9 w-9 items-center justify-center rounded-md hover:bg-muted">
              <IconArrowLeft size={18} />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold">{t('personalAuto.title', locale)}</h1>
                <span className={`rounded-md px-2 py-1 text-[11px] font-medium ${badgeClass}`}>
                  {t(badge.key, locale, badge.params)}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {session
                  ? t('personalAuto.runningSubtitle', locale, {
                      taskName: selectedTask?.name ?? '',
                      outboundNumber: selectedPhone?.phone_number ?? '',
                    })
                  : t('personalAuto.description', locale)}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {!session && <Button size="lg" disabled={!complete || startSession.isPending} onClick={() => void start()}><IconPlayerPlay size={17} />{t(startSession.isPending ? 'personalAuto.starting' : 'personalAuto.start', locale)}</Button>}
            {session?.status === 'running' && <Button variant="outline" disabled={controlSession.isPending} onClick={() => void control('pause')}><IconPlayerPause size={17} />{t('personalAuto.pause', locale)}</Button>}
            {session && ['paused', 'auto_paused'].includes(session.status) && <Button disabled={controlSession.isPending || !agentReady || !deviceAvailable} onClick={() => void control('resume')}><IconPlayerPlay size={17} />{t('personalAuto.resume', locale)}</Button>}
            {session && session.status !== 'stopping' && <Button variant="destructive" disabled={controlSession.isPending} onClick={() => setStopOpen(true)}><IconPlayerStop size={17} />{t('personalAuto.stop', locale)}</Button>}
          </div>
        </header>

        {!agentReady && <Notice text={t('personalAuto.agentNotReady', locale)} destructive />}
        {!deviceAvailable && <Notice text={t('personalAuto.deviceUnavailable', locale)} destructive />}
        {!config.has_enabled_prescreen_intents && <Notice text={t('personalAuto.noIntents', locale)} destructive />}
        {config.tasks.length > 0 && !session && effectiveConcurrency < concurrency && <Notice text={t('personalAuto.concurrencyReduced', locale)} />}
        {sessionQuery.data?.gate_reason && !hideGateAlert && <Notice text={t(`personalAuto.gate.${sessionQuery.data.gate_reason}`, locale)} />}

        {config.tasks.length === 0 ? (
          <section className="rounded-xl border border-dashed border-border p-10 text-center">
            <p className="text-sm text-muted-foreground">{t('personalAuto.noTasks', locale)}</p>
            <Link href="/workspace/call?view=outbound-tasks" className="mt-4 inline-flex h-9 items-center rounded-md border border-border px-3 text-sm font-medium hover:bg-muted">{t('personalAuto.back', locale)}</Link>
          </section>
        ) : showTaskPop ? (
          <PersonalAutoOutboundTaskPop
            incoming={incoming}
            phase={phase}
            onSubmitted={onWrapupSubmitted ?? (() => undefined)}
          />
        ) : session ? (
          <div className="flex flex-col gap-4">
            <PersonalAutoOutboundLanes lanes={lanes} locale={locale} />
            <p className="px-1 text-[11px] text-muted-foreground">
              {calls.some(isLaneActiveCall)
                ? t('personalAuto.endedCount', locale, { count: endedCallCount(calls) })
                : t('personalAuto.preparingCalls', locale)}
            </p>
          </div>
        ) : (
          <>
            <section>
              <h2 className="text-base font-semibold">{t('personalAuto.configuration', locale)}</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <SelectField label={t('personalAuto.task', locale)} value={taskId} disabled={locked} onChange={setTaskId} options={config.tasks.map((task) => ({ value: String(task.id), label: `${task.name} (${task.callable_count})` }))} placeholder={t('personalAuto.selectTask', locale)} />
                <SelectField label={t('personalAuto.phone', locale)} value={phoneId} disabled={locked} onChange={setPhoneId} options={config.phone_numbers.map((phone) => ({ value: phone.id, label: phone.phone_number }))} placeholder={t('personalAuto.selectPhone', locale)} />
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <SelectField label={t('personalAuto.fallbackGroup', locale)} value={fallbackGroupId} disabled={locked} onChange={setFallbackGroupId} options={config.fallback_groups.map((group) => ({ value: String(group.id), label: `${group.name} (${t('personalAuto.readyCount', locale, { count: group.ready_agent_count })})` }))} placeholder={t('personalAuto.noFallback', locale)} />
                <label className="text-sm font-medium">{t('personalAuto.concurrency', locale)}<div className="mt-2 flex items-center gap-3"><Input className="w-28" type="number" min={1} max={10} value={concurrency} disabled={locked} onChange={(event) => setConcurrency(Math.max(1, Math.min(10, Number(event.target.value))))} /><span className="text-xs text-muted-foreground">{t('personalAuto.effectiveConcurrency', locale, { count: effectiveConcurrency })}</span></div></label>
              </div>
            </section>
            <section>
              <h2 className="text-base font-semibold">{t('personalAuto.recordings', locale)}</h2>
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                <PersonalOutboundRecordingField type="opening" recording={config.recordings.opening} disabled={locked} pending={uploadRecording.isPending || removeRecording.isPending || saveOpeningScript.isPending} onUpload={(file) => upload('opening', file)} onRemove={() => remove('opening')} openingScript={openingScript} onOpeningScriptChange={setOpeningScript} onOpeningScriptSave={() => void persistOpeningScript()} openingScriptError={openingScriptError} />
                <PersonalOutboundRecordingField type="closing" recording={config.recordings.closing} disabled={locked} pending={uploadRecording.isPending || removeRecording.isPending} onUpload={(file) => upload('closing', file)} onRemove={() => remove('closing')} />
              </div>
            </section>
          </>
        )}
        <ConfirmDialog open={stopOpen} title={t('personalAuto.stopTitle', locale)} message={t('personalAuto.stopMessage', locale, { ringing: metrics.ringing_current, screening: metrics.screening_current, human: metrics.human_current })} confirmLabel={t('personalAuto.confirmStop', locale)} cancelLabel={t('personalAuto.cancel', locale)} variant="destructive" loading={controlSession.isPending} onCancel={() => setStopOpen(false)} onConfirm={() => control('stop')} />
      </div>
    </div>
  )
}

const EMPTY_METRICS = {
  ringing_current: 0,
  ringing_total: 0,
  screening_current: 0,
  screening_total: 0,
  human_current: 0,
  human_total: 0,
  filtered_current: 0,
  filtered_total: 0,
}

function Notice({ text, destructive = false }: { text: string; destructive?: boolean }) {
  return <div className={`flex items-center gap-2 rounded-lg border px-4 py-3 text-sm ${destructive ? 'border-destructive/30 bg-destructive/5 text-destructive' : 'border-warning/30 bg-warning/5 text-warning-foreground'}`}><IconAlertTriangle size={17} />{text}</div>
}

function SelectField({ label, value, disabled, onChange, options, placeholder }: { label: string; value: string; disabled: boolean; onChange: (value: string) => void; options: Array<{ value: string; label: string }>; placeholder: string }) {
  return <label className="text-sm font-medium">{label}<select className="mt-2 h-10 w-full rounded-md border border-input bg-background px-3 text-sm disabled:opacity-60" value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}><option value="">{placeholder}</option>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
}
