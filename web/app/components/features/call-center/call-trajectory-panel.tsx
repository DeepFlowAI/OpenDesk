'use client'

import { useMemo, useState } from 'react'
import type { ComponentType } from 'react'
import {
  IconActivity,
  IconAlertTriangle,
  IconArrowsExchange,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconClock,
  IconCode,
  IconHeadset,
  IconListDetails,
  IconPhone,
  IconPlayerPause,
  IconRefresh,
  IconRobot,
  IconRoute,
  IconUsers,
} from '@tabler/icons-react'

import { useLocaleStore } from '@/context/locale-store'
import {
  formatTrajectoryDuration,
  formatTrajectoryTime,
  isBusinessTrajectoryEvent,
  trajectoryEventDescription,
  trajectoryEventLabel,
  trajectoryOperationStepDescription,
  trajectoryOperationStepLabel,
  trajectoryOperationTitle,
  trajectoryParticipantNames,
  trajectoryResultLabel,
} from '@/lib/call-trajectory'
import type { CallTrajectoryEvent, CallTrajectoryOperation } from '@/models/call-center'
import { useCallTrajectory } from '@/service/use-call-center'
import { t } from '@/utils/i18n'

type TrajectoryMode = 'business' | 'technical'

export function CallTrajectoryPanel({ recordId, enabled }: { recordId: string; enabled: boolean }) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const [mode, setMode] = useState<TrajectoryMode>('business')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const query = useCallTrajectory(recordId, enabled)
  const data = query.data

  const events = useMemo(() => {
    const all = data?.events ?? []
    return mode === 'business' ? all.filter(isBusinessTrajectoryEvent) : all
  }, [data?.events, mode])
  const eventById = useMemo(
    () => new Map((data?.events ?? []).map((event) => [event.event_id, event])),
    [data?.events],
  )
  const participantNames = useMemo(
    () => trajectoryParticipantNames(data?.events ?? []),
    [data?.events],
  )
  const operations = useMemo(
    () => new Map((data?.operations ?? []).map((operation) => [operation.operation_id, operation])),
    [data?.operations],
  )
  const renderedOperations = new Set<string>()
  const expandableIds = (data?.operations ?? [])
    .filter((operation) => operation.event_ids.length > 1)
    .map((operation) => operation.operation_id)
  const allExpanded = expandableIds.length > 0 && expandableIds.every((id) => expanded.has(id))

  const toggleOperation = (operationId: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(operationId)) next.delete(operationId)
      else next.add(operationId)
      return next
    })
  }

  if (query.isLoading) return <TrajectorySkeleton />
  if (query.isError) {
    return (
      <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
        <IconAlertTriangle size={24} />
        <p>{t('ws.records.calls.trajectory.loadFailed', locale)}</p>
        <button type="button" onClick={() => query.refetch()} className="rounded-md border border-border px-3 py-1.5 text-foreground hover:bg-muted">
          {t('ws.records.calls.trajectory.retry', locale)}
        </button>
      </div>
    )
  }
  if (!data) return null

  return (
    <section className="flex min-h-[420px] flex-col rounded-xl border border-border bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex h-8 rounded-md bg-muted p-0.5 text-xs">
            <ModeButton active={mode === 'business'} onClick={() => setMode('business')} icon={IconListDetails}>
              {t('ws.records.calls.trajectory.business', locale)}
            </ModeButton>
            <ModeButton active={mode === 'technical'} onClick={() => setMode('technical')} icon={IconCode}>
              {t('ws.records.calls.trajectory.technical', locale)}
            </ModeButton>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            {data.is_live && <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />}
            {data.is_live
              ? t('ws.records.calls.trajectory.live', locale)
              : data.is_complete
                ? t('ws.records.calls.trajectory.complete', locale)
                : t('ws.records.calls.trajectory.incomplete', locale)}
          </span>
          <button
            type="button"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-foreground hover:bg-muted disabled:opacity-50"
          >
            <IconRefresh size={14} className={query.isFetching ? 'animate-spin' : ''} />
            {t('ws.records.calls.trajectory.refresh', locale)}
          </button>
        </div>
      </div>

      {data.warnings.length > 0 && (
        <div className="mx-5 mt-4 flex gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <IconAlertTriangle size={15} className="mt-0.5 shrink-0 text-destructive" />
          <span>{data.warnings.map((warning) => warning.message).join(' · ')}</span>
        </div>
      )}

      <div className="mx-auto w-full max-w-[920px] px-5 py-5">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">
              {mode === 'business'
                ? t('ws.records.calls.trajectory.history', locale)
                : t('ws.records.calls.trajectory.rawEvents', locale)}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {t('ws.records.calls.trajectory.eventCount', locale, { count: events.length })}
            </p>
          </div>
          {expandableIds.length > 0 && (
            <button
              type="button"
              onClick={() => setExpanded(allExpanded ? new Set() : new Set(expandableIds))}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              {allExpanded
                ? t('ws.records.calls.trajectory.collapseAll', locale)
                : t('ws.records.calls.trajectory.expandAll', locale)}
            </button>
          )}
        </div>

        {events.length === 0 ? (
          <div className="flex min-h-[180px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <IconActivity size={24} />
            {t('ws.records.calls.trajectory.empty', locale)}
          </div>
        ) : events.map((event, index) => {
          const operation = event.operation_id ? operations.get(event.operation_id) : undefined
          if (operation?.event_ids.length && event.operation_id) {
            if (renderedOperations.has(event.operation_id)) return null
            renderedOperations.add(event.operation_id)
          }
          const isLast = index === events.length - 1
          return (
            <TimelineEvent key={event.event_id} event={event} isZh={isZh} technical={mode === 'technical'} participantNames={participantNames} last={isLast}>
              {operation && operation.event_ids.length > 1 && (
                <OperationCard
                  operation={operation}
                  events={operation.event_ids
                    .map((id) => eventById.get(id))
                    .filter((item): item is CallTrajectoryEvent => Boolean(item))}
                  expanded={expanded.has(operation.operation_id)}
                  onToggle={() => toggleOperation(operation.operation_id)}
                  isZh={isZh}
                  technical={mode === 'technical'}
                  participantNames={participantNames}
                />
              )}
              {event.event_type === 'call_ended' && <SettlementCard event={event} isZh={isZh} />}
            </TimelineEvent>
          )
        })}
      </div>
    </section>
  )
}

function ModeButton({ active, onClick, icon: Icon, children }: { active: boolean; onClick: () => void; icon: ComponentType<{ size?: number }>; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={`inline-flex h-7 items-center gap-1.5 rounded px-2.5 ${active ? 'bg-background font-medium shadow-sm' : 'text-muted-foreground'}`}>
      <Icon size={14} />{children}
    </button>
  )
}

function TimelineEvent({ event, isZh, technical, participantNames, last, children }: { event: CallTrajectoryEvent; isZh: boolean; technical: boolean; participantNames: Map<string, string>; last: boolean; children?: React.ReactNode }) {
  const Icon = iconForCategory(event.event_category)
  return (
    <div className="grid grid-cols-[76px_28px_minmax(0,1fr)] gap-3">
      <time className="pt-1.5 text-right font-mono text-[10px] text-muted-foreground">{formatTrajectoryTime(event.occurred_at, technical)}</time>
      <div className="relative flex justify-center">
        {!last && <div className="absolute bottom-0 top-7 w-px bg-border" />}
        <span className="relative z-10 grid h-7 w-7 place-items-center rounded-full bg-muted text-muted-foreground ring-1 ring-border"><Icon size={14} /></span>
      </div>
      <div className="min-w-0 pb-5">
        <div className={`pt-1 text-xs font-semibold ${technical ? 'font-mono' : ''}`}>{technical ? event.event_type : trajectoryEventLabel(event.event_type, isZh)}</div>
        <p className="mt-1 text-[11px] leading-4 text-muted-foreground">{trajectoryEventDescription(event, isZh, technical, participantNames)}</p>
        {technical && <TechnicalIdentifiers callLegId={event.call_leg_id} traceId={event.trace_id} isZh={isZh} />}
        {children}
      </div>
    </div>
  )
}

function TechnicalIdentifiers({ callLegId, traceId, isZh }: { callLegId: string | null; traceId: string | null; isZh: boolean }) {
  if (!callLegId && !traceId) return null
  const hint = isZh ? '单击可全选，用于查询日志' : 'Click to select for log lookup'
  return (
    <div className="mt-1 space-y-0.5 font-mono text-[10px] leading-4 text-muted-foreground">
      <p className="flex min-w-0 gap-1"><span>leg=</span><span title={hint} className="min-w-0 select-all break-all">{callLegId || '-'}</span></p>
      <p className="flex min-w-0 gap-1"><span>trace=</span><span title={hint} className="min-w-0 select-all break-all">{traceId || '-'}</span></p>
    </div>
  )
}

function OperationCard({ operation, events, expanded, onToggle, isZh, technical, participantNames }: { operation: CallTrajectoryOperation; events: CallTrajectoryEvent[]; expanded: boolean; onToggle: () => void; isZh: boolean; technical: boolean; participantNames: Map<string, string> }) {
  const first = events[0]
  const title = technical
    ? first?.event_type || operation.operation_id
    : trajectoryOperationTitle(events, isZh, participantNames)
  const status = technical
    ? operation.result || (isZh ? '进行中' : 'In progress')
    : trajectoryResultLabel(operation.result, isZh)
  const meta = technical
    ? `${events.length} events · ${formatTrajectoryDuration(operation.duration_ms)}`
    : `${events.length} ${isZh ? '个步骤' : events.length === 1 ? 'step' : 'steps'} · ${formatTrajectoryDuration(operation.duration_ms, isZh)}`
  return (
    <div className="mt-2 overflow-hidden rounded-lg border border-border bg-background shadow-sm">
      <button type="button" onClick={onToggle} aria-expanded={expanded} className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left hover:bg-muted/40">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium">{status}</span><span className={`truncate text-xs font-medium ${technical ? 'font-mono' : ''}`}>{title}</span></div>
          <p className="mt-1 text-[10px] text-muted-foreground">{meta}</p>
        </div>
        {expanded ? <IconChevronDown size={15} /> : <IconChevronRight size={15} />}
      </button>
      {expanded && <div className="border-t border-border bg-muted/20 px-3 py-2">{events.map((event) => {
        const detail = technical
          ? event.reason_code || event.result || event.source
          : trajectoryOperationStepDescription(event, isZh, participantNames)
        return <div key={event.event_id} className="grid grid-cols-[76px_minmax(0,1fr)] gap-2 py-1 text-[10px]"><span className="font-mono text-muted-foreground">{formatTrajectoryTime(event.occurred_at, technical)}</span><span><b className={`font-medium ${technical ? 'font-mono' : ''}`}>{technical ? event.event_type : trajectoryOperationStepLabel(event.event_type, isZh)}</b>{detail && <span className="ml-2 text-muted-foreground">{detail}</span>}</span></div>
      })}</div>}
    </div>
  )
}

function SettlementCard({ event, isZh }: { event: CallTrajectoryEvent; isZh: boolean }) {
  const values = [
    [isZh ? '通话结果' : 'Call result', event.details.call_result],
    [isZh ? '结束方' : 'Ended by', event.details.hangup_party],
    [isZh ? '结束阶段' : 'End stage', event.details.hangup_stage],
    [isZh ? '总时长' : 'Total duration', formatTrajectoryDuration(event.details.total_duration_ms as number | undefined)],
  ]
  return <div className="mt-2 grid grid-cols-2 gap-3 rounded-lg border border-border bg-muted/20 p-3 sm:grid-cols-4">{values.map(([label, value]) => <div key={String(label)} className="text-[10px]"><span className="text-muted-foreground">{String(label)}</span><div className="mt-1 font-medium">{value ? String(value) : '-'}</div></div>)}</div>
}

function TrajectorySkeleton() {
  return <div className="min-h-[420px] animate-pulse space-y-5 rounded-xl border border-border p-5"><div className="h-8 w-64 rounded bg-muted" />{Array.from({ length: 5 }, (_, index) => <div key={index} className="flex gap-4"><div className="h-7 w-7 rounded-full bg-muted" /><div className="space-y-2"><div className="h-3 w-48 rounded bg-muted" /><div className="h-3 w-72 rounded bg-muted" /></div></div>)}</div>
}

function iconForCategory(category: string): ComponentType<{ size?: number }> {
  if (category === 'routing' || category === 'ivr') return IconRoute
  if (category === 'bot') return IconRobot
  if (category === 'queue') return IconUsers
  if (category === 'reception') return IconHeadset
  if (category === 'control') return IconPlayerPause
  if (['transfer', 'consult', 'conference'].includes(category)) return IconArrowsExchange
  if (category === 'lifecycle') return IconPhone
  if (category === 'system') return IconCheck
  return IconClock
}
