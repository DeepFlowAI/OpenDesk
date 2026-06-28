'use client'

import { useState, type ReactNode } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { BotHandoffStatus, QueueResult, ReceptionSegment, SessionRecordDetail, SessionRecordType } from '@/models/session-record'
import { SessionSummaryFields } from '@/app/components/features/session-summary/session-summary-fields'
import { useSessionRecordSatisfaction } from '@/service/use-satisfaction-survey'
import { useReceptionTrajectory } from '@/service/use-session-records'
import type { SatisfactionSurveyResult } from '@/models/satisfaction-survey'
import { formatSessionDuration } from './session-duration'

export type SessionInfoTab = 'basic' | 'summary' | 'reception'

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).replace('T', ' ')
}

function formatQueueDuration(seconds: number | null): string {
  if (seconds == null || seconds < 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${String(h).padStart(2, '0')}:${mm}:${ss}` : `${mm}:${ss}`
}

function formatSeconds(seconds: number | null): string {
  if (seconds == null || seconds < 0) return '-'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${String(h).padStart(2, '0')}:${mm}:${ss}` : `${mm}:${ss}`
}

function formatCount(value: number | null | undefined): string {
  return value == null ? '-' : String(value)
}

const ENDED_BY_LABEL_KEYS = new Set(['agent', 'visitor', 'bot_timeout', 'system_timeout'])

function endedByLabel(value: string | null, locale: Locale): string {
  if (!value) return '-'
  if (ENDED_BY_LABEL_KEYS.has(value)) return t(`ws.records.sessions.endedBy.${value}`, locale)
  return value
}

const sessionTypeClassName: Record<SessionRecordType, string> = {
  human: 'bg-muted text-muted-foreground',
  bot: 'bg-info/10 text-info',
  bot_human: 'bg-success/10 text-success',
}

const botHandoffClassName: Record<BotHandoffStatus, string> = {
  not_triggered: 'bg-muted text-muted-foreground',
  waiting_confirmation: 'bg-warning/10 text-warning',
  handoff_in_progress: 'bg-warning/10 text-warning',
  in_queue: 'bg-warning/10 text-warning',
  succeeded: 'bg-success/10 text-success',
  failed: 'bg-destructive/10 text-destructive',
  dismissed: 'bg-muted text-muted-foreground',
}

const queueResultClassName: Record<QueueResult, string> = {
  assigned: 'bg-success/10 text-success',
  canceled: 'bg-muted text-muted-foreground',
  timeout: 'bg-warning/10 text-warning',
  waiting: 'bg-warning/10 text-warning',
  failed: 'bg-destructive/10 text-destructive',
}

function StatusBadge({ label, className }: { label: string; className: string }) {
  return (
    <span className={cn('inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium', className)}>
      {label}
    </span>
  )
}

function SessionTypeValue({ value, locale }: { value: SessionRecordType | null; locale: Locale }) {
  if (!value) return ''
  return (
    <StatusBadge
      label={t(`ws.records.sessions.sessionType.${value}`, locale)}
      className={sessionTypeClassName[value]}
    />
  )
}

function BotHandoffValue({ value, locale }: { value: BotHandoffStatus | null; locale: Locale }) {
  if (!value) return ''
  return (
    <StatusBadge
      label={t(`ws.records.sessions.botHandoff.${value}`, locale)}
      className={botHandoffClassName[value]}
    />
  )
}

function QueueResultValue({ value, locale }: { value: QueueResult | null; locale: Locale }) {
  if (!value) return ''
  return (
    <StatusBadge
      label={t(`ws.records.sessions.queueResult.${value}`, locale)}
      className={queueResultClassName[value]}
    />
  )
}

const sessionStatusClassName: Record<SessionRecordDetail['status'], string> = {
  queued: 'bg-warning/10 text-warning',
  active: 'bg-success/10 text-success',
  bot: 'bg-info/10 text-info',
  handoff_pending: 'bg-warning/10 text-warning',
  closed: 'bg-muted text-muted-foreground',
}

function SessionStatusValue({ value, locale }: { value: SessionRecordDetail['status']; locale: Locale }) {
  if (!value) return ''
  return (
    <StatusBadge
      label={t(`ws.records.sessions.status.${value}`, locale)}
      className={sessionStatusClassName[value] ?? 'bg-muted text-muted-foreground'}
    />
  )
}

type Props = {
  record: SessionRecordDetail
  onSummaryDirtyChange?: (dirty: boolean) => void
  activeTab?: SessionInfoTab
  onActiveTabChange?: (tab: SessionInfoTab) => void
}

export function SessionInfoPanel({ record, onSummaryDirtyChange, activeTab: controlledActiveTab, onActiveTabChange }: Props) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [internalActiveTab, setInternalActiveTab] = useState<SessionInfoTab>('basic')
  const [summaryDirty, setSummaryDirty] = useState(false)
  const activeTab = controlledActiveTab ?? internalActiveTab
  const visitorDetailRef = record.visitor?.public_id || (record.visitor?.id ? String(record.visitor.id) : '')
  const isWebChannel = record.channel?.channel_type?.toLowerCase() === 'web'

  const handleSummaryDirtyChange = (dirty: boolean) => {
    setSummaryDirty(dirty)
    onSummaryDirtyChange?.(dirty)
  }

  const switchTab = (nextTab: SessionInfoTab) => {
    if (activeTab === 'summary' && nextTab !== 'summary' && summaryDirty) {
      const confirmed = window.confirm(t('ws.summary.unsavedConfirm', locale))
      if (!confirmed) return
    }
    if (onActiveTabChange) {
      onActiveTabChange(nextTab)
    } else {
      setInternalActiveTab(nextTab)
    }
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-x-hidden p-5">
      <div className="mb-4 flex rounded-lg border border-border bg-background p-0.5">
        <button
          type="button"
          onClick={() => switchTab('basic')}
          className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', activeTab === 'basic' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
        >
          {t('ws.summary.tab.basic', locale)}
        </button>
        <button
          type="button"
          onClick={() => switchTab('summary')}
          className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', activeTab === 'summary' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
        >
          {t('ws.summary.tab.summary', locale)}
        </button>
        <button
          type="button"
          onClick={() => switchTab('reception')}
          className={cn('flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors', activeTab === 'reception' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground')}
        >
          {t('ws.records.sessions.reception.tab', locale)}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === 'basic' ? (
          <>
            <div className="mb-6">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('ws.records.sessions.detail.userInfo', locale)}
              </h3>
              <div className="flex flex-col gap-3">
                <InfoRow
                  label={t('ws.records.sessions.detail.userName', locale)}
                  value={record.visitor?.name || '-'}
                  action={visitorDetailRef ? (
                    <button
                      type="button"
                      onClick={() => router.push(`/workspace/users/${visitorDetailRef}`)}
                      className="shrink-0 text-xs font-medium text-primary underline-offset-2 hover:underline"
                    >
                      {t('ws.records.sessions.detail.viewUser', locale)}
                    </button>
                  ) : null}
                />
              </div>
            </div>

            <div className="mb-6">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('ws.records.sessions.detail.sessionInfo', locale)}
              </h3>
              <div className="flex flex-col gap-3">
                <InfoRow label={t('ws.records.sessions.detail.shareCode', locale)} value={record.share_code || record.public_id || '-'} />
                <InfoRow
                  label={t('ws.records.sessions.detail.relatedTickets', locale)}
                  value={<RelatedTicketsLinks tickets={record.related_tickets ?? []} />}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.status', locale)}
                  value={<SessionStatusValue value={record.status} locale={locale} />}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.sessionType', locale)}
                  value={<SessionTypeValue value={record.session_type} locale={locale} />}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.botHandoff', locale)}
                  value={<BotHandoffValue value={record.bot_handoff_status} locale={locale} />}
                />
                <InfoRow label={t('ws.records.sessions.detail.channelType', locale)} value={record.channel?.channel_type || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.channelName', locale)} value={record.channel?.name || '-'} />
                {isWebChannel && (
                  <>
                    <InfoRow label={t('ws.chat.visitorSystem', locale)} value={record.visitor_system || '-'} />
                    <InfoRow label={t('ws.chat.visitorBrowser', locale)} value={record.visitor_browser || '-'} />
                    <InfoRow label={t('ws.chat.visitorIp', locale)} value={record.visitor_ip || '-'} />
                  </>
                )}
                <InfoRow
                  label={t('ws.records.sessions.detail.lastAssignedQueue', locale)}
                  value={<QueueNameValue queue={record.last_assigned_queue} locale={locale} />}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.queueDuration', locale)}
                  value={formatQueueDuration(record.queue_duration_seconds)}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.hasQueue', locale)}
                  value={record.has_queue ? t('ws.records.sessions.hasQueue.yes', locale) : t('ws.records.sessions.hasQueue.no', locale)}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.queueResult', locale)}
                  value={<QueueResultValue value={record.queue_result} locale={locale} />}
                />
                <InfoRow label={t('ws.records.sessions.detail.queueEnteredAt', locale)} value={formatDateTime(record.queue_entered_at)} />
                <InfoRow label={t('ws.records.sessions.detail.queueAssignedAt', locale)} value={formatDateTime(record.queue_assigned_at)} />
                <InfoRow label={t('ws.records.sessions.detail.agent', locale)} value={record.agent?.display_name || record.agent?.name || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.firstResponse', locale)} value={formatSeconds(record.first_human_response_seconds)} />
                <InfoRow label={t('ws.records.sessions.detail.agentResponseCount', locale)} value={record.agent_response_count == null ? '-' : String(record.agent_response_count)} />
                <InfoRow label={t('ws.records.sessions.detail.agentAvgResponse', locale)} value={formatSeconds(record.agent_avg_response_seconds)} />
                <InfoRow label={t('ws.records.sessions.detail.messageCount', locale)} value={formatCount(record.message_count)} />
                <InfoRow label={t('ws.records.sessions.detail.visitorMessageCount', locale)} value={formatCount(record.visitor_message_count)} />
                <InfoRow label={t('ws.records.sessions.detail.agentMessageCount', locale)} value={formatCount(record.agent_message_count)} />
                <InfoRow label={t('ws.records.sessions.detail.botPhaseMessageCount', locale)} value={formatCount(record.bot_phase_message_count)} />
                <InfoRow label={t('ws.records.sessions.detail.humanPhaseMessageCount', locale)} value={formatCount(record.human_phase_message_count)} />
                <InfoRow label={t('ws.records.sessions.detail.humanPhaseVisitorMessageCount', locale)} value={formatCount(record.human_phase_visitor_message_count)} />
                <InfoRow label={t('ws.records.sessions.detail.humanPhaseAgentMessageCount', locale)} value={formatCount(record.human_phase_agent_message_count)} />
                <InfoRow label={t('ws.records.sessions.detail.createdAt', locale)} value={formatDateTime(record.created_at)} />
                <InfoRow label={t('ws.records.sessions.detail.startTime', locale)} value={formatDateTime(record.started_at)} />
                <InfoRow
                  label={t('ws.records.sessions.detail.endTime', locale)}
                  value={record.ended_at ? formatDateTime(record.ended_at) : t('ws.records.sessions.status.active', locale)}
                />
                <InfoRow label={t('ws.records.sessions.detail.endedBy', locale)} value={endedByLabel(record.ended_by, locale)} />
                <InfoRow label={t('ws.records.sessions.detail.duration', locale)} value={formatSessionDuration(record)} />
              </div>
            </div>

            <SatisfactionRecordPanel recordId={record.id} />
          </>
        ) : activeTab === 'summary' ? (
          <SessionSummaryFields conversationId={record.id} onDirtyChange={handleSummaryDirtyChange} />
        ) : activeTab === 'reception' ? (
          <ReceptionTrajectoryPanel recordId={record.id} />
        ) : null}
      </div>
    </div>
  )
}

function QueueNameValue({
  queue,
  locale,
}: {
  queue: SessionRecordDetail['last_assigned_queue']
  locale: Locale
}) {
  if (!queue?.name) return <span className="text-sm text-foreground" />
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <span className="min-w-0 break-words text-sm text-foreground">{queue.name}</span>
      {queue.queue_type === 'employee' && (
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] leading-4 text-muted-foreground">
          {t('ws.records.queue.personalQueue', locale)}
        </span>
      )}
    </div>
  )
}

function resultLabel(result: SatisfactionSurveyResult | null, locale: Locale): string {
  if (!result) return '-'
  return result.option_name || '-'
}

function SatisfactionRecordPanel({ recordId }: { recordId: number }) {
  const { locale } = useLocaleStore()
  const { data, isLoading, isError, refetch } = useSessionRecordSatisfaction(recordId)
  const record = data?.record
  const hasResult = Boolean(record?.service_result || record?.product_result)

  return (
    <div>
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {t('ws.summary.tab.satisfaction', locale)}
      </h3>

      {isLoading ? (
        <PanelState text={t('ws.records.sessions.satisfaction.loading', locale)} />
      ) : isError ? (
        <div className="space-y-3">
          <PanelState text={t('ws.records.sessions.satisfaction.loadFailed', locale)} />
          <button
            type="button"
            onClick={() => refetch()}
            className="h-8 rounded-md border border-border px-3 text-xs text-foreground hover:bg-muted"
          >
            {t('ws.chat.retry', locale)}
          </button>
        </div>
      ) : hasResult ? (
        <SatisfactionResultCard
          serviceResult={record?.service_result ?? null}
          productResult={record?.product_result ?? null}
          submittedAt={record?.submitted_at ?? null}
          locale={locale}
        />
      ) : (
        <PanelState text={t('ws.records.sessions.satisfaction.empty', locale)} />
      )}
    </div>
  )
}

function PanelState({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground">
      {text}
    </div>
  )
}

const RECEPTION_ENTRY_KEYS = new Set(['first', 'bot_handoff', 'transfer_in', 'reassign'])
const RECEPTION_END_KEYS = new Set(['transfer_out', 'reassign_out', 'session_closed'])

function receptionEntryLabel(value: string, locale: Locale): string {
  return RECEPTION_ENTRY_KEYS.has(value) ? t(`ws.records.sessions.reception.entry.${value}`, locale) : value
}

function receptionEndLabel(value: string | null, locale: Locale): string {
  if (!value) return '-'
  return RECEPTION_END_KEYS.has(value) ? t(`ws.records.sessions.reception.end.${value}`, locale) : value
}

function ReceptionTrajectoryPanel({ recordId }: { recordId: number }) {
  const { locale } = useLocaleStore()
  const { data, isLoading, isError, refetch } = useReceptionTrajectory(recordId)

  const title = (
    <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
      {t('ws.records.sessions.reception.title', locale)}
    </h3>
  )

  if (isLoading) {
    return <div>{title}<PanelState text={t('ws.records.sessions.reception.loading', locale)} /></div>
  }
  if (isError || !data) {
    return (
      <div>
        {title}
        <div className="space-y-3">
          <PanelState text={t('ws.records.sessions.reception.loadFailed', locale)} />
          <RefreshButton onClick={() => refetch()} locale={locale} />
        </div>
      </div>
    )
  }

  // Map agent_id -> snapshot name within this trajectory so source/target agent
  // names resolve from the segment chain without an extra lookup.
  const nameById = new Map<number, string>()
  for (const segment of data.segments) {
    if (segment.agent_id != null && segment.agent_name) nameById.set(segment.agent_id, segment.agent_name)
  }
  const agentName = (id: number | null): string => (id != null ? nameById.get(id) || `#${id}` : '-')

  if (data.conversation_status !== 'closed') {
    return <div>{title}<PanelState text={t('ws.records.sessions.reception.inProgress', locale)} /></div>
  }
  if (data.generation_status === 'failed') {
    return (
      <div>
        {title}
        <div className="space-y-3">
          <PanelState text={t('ws.records.sessions.reception.unavailable', locale)} />
          <RefreshButton onClick={() => refetch()} locale={locale} />
        </div>
      </div>
    )
  }
  if (data.generation_status == null) {
    return (
      <div>
        {title}
        <div className="space-y-3">
          <PanelState text={t('ws.records.sessions.reception.generating', locale)} />
          <RefreshButton onClick={() => refetch()} locale={locale} />
        </div>
      </div>
    )
  }
  if (data.segments.length === 0) {
    return <div>{title}<PanelState text={t('ws.records.sessions.reception.empty', locale)} /></div>
  }

  return (
    <div>
      {title}
      <div className="space-y-3">
        {data.segments.map((segment) => (
          <ReceptionSegmentCard
            key={segment.seq_no}
            segment={segment}
            agentName={agentName}
            locale={locale}
          />
        ))}
      </div>
    </div>
  )
}

function RefreshButton({ onClick, locale }: { onClick: () => void; locale: Locale }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-8 rounded-md border border-border px-3 text-xs text-foreground hover:bg-muted"
    >
      {t('ws.records.sessions.reception.refresh', locale)}
    </button>
  )
}

function ReceptionSegmentCard({
  segment,
  agentName,
  locale,
}: {
  segment: ReceptionSegment
  agentName: (id: number | null) => string
  locale: Locale
}) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-foreground">
          {t('ws.records.sessions.reception.segmentSeq', locale).replace('{seq}', String(segment.seq_no))}
        </span>
        <span className="inline-flex whitespace-nowrap rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {receptionEntryLabel(segment.entry_reason, locale)}
        </span>
      </div>
      <div className="flex flex-col gap-3">
        <InfoRow label={t('ws.records.sessions.reception.agent', locale)} value={segment.agent_name || agentName(segment.agent_id)} />
        <InfoRow label={t('ws.records.sessions.reception.group', locale)} value={segment.group_name || '—'} />
        <InfoRow label={t('ws.records.sessions.reception.startTime', locale)} value={formatDateTime(segment.started_at)} />
        <InfoRow label={t('ws.records.sessions.reception.endTime', locale)} value={formatDateTime(segment.ended_at)} />
        <InfoRow label={t('ws.records.sessions.reception.duration', locale)} value={formatSeconds(segment.duration_seconds)} />
        <InfoRow label={t('ws.records.sessions.reception.entryReason', locale)} value={receptionEntryLabel(segment.entry_reason, locale)} />
        <InfoRow label={t('ws.records.sessions.reception.endReason', locale)} value={receptionEndLabel(segment.end_reason, locale)} />
        {segment.from_agent_id != null && (
          <InfoRow label={t('ws.records.sessions.reception.fromAgent', locale)} value={agentName(segment.from_agent_id)} />
        )}
        {segment.to_agent_id != null && (
          <InfoRow label={t('ws.records.sessions.reception.toAgent', locale)} value={agentName(segment.to_agent_id)} />
        )}
        <InfoRow label={t('ws.records.sessions.reception.visitorMessageCount', locale)} value={formatCount(segment.visitor_message_count)} />
        <InfoRow label={t('ws.records.sessions.reception.agentMessageCount', locale)} value={formatCount(segment.agent_message_count)} />
        {segment.seq_no === 1 && (
          <InfoRow label={t('ws.records.sessions.reception.firstResponse', locale)} value={segment.first_response_seconds == null ? '—' : formatSeconds(segment.first_response_seconds)} />
        )}
        <InfoRow label={t('ws.records.sessions.reception.avgResponse', locale)} value={formatSeconds(segment.avg_response_seconds)} />
      </div>
    </div>
  )
}

function SatisfactionResultCard({
  serviceResult,
  productResult,
  submittedAt,
  locale,
}: {
  serviceResult: SatisfactionSurveyResult | null
  productResult: SatisfactionSurveyResult | null
  submittedAt: string | null
  locale: Locale
}) {
  const results = [
    serviceResult ? { key: 'service', typeLabel: t('ws.records.sessions.satisfaction.service', locale), result: serviceResult } : null,
    productResult ? { key: 'product', typeLabel: t('ws.records.sessions.satisfaction.product', locale), result: productResult } : null,
  ].filter((item): item is { key: string; typeLabel: string; result: SatisfactionSurveyResult } => item !== null)
  const displaySubmittedAt = submittedAt ?? serviceResult?.submitted_at ?? productResult?.submitted_at ?? null

  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-foreground">
          {t('ws.records.sessions.satisfaction.result', locale)}
        </h3>
      </div>
      <div className="space-y-4">
        {results.map((item, index) => (
          <div key={item.key} className={cn('space-y-3', index > 0 && 'border-t border-border pt-4')}>
            <div className="text-xs font-medium text-muted-foreground">{item.typeLabel}</div>
            {item.result.type === 'service' && (
              <InfoRow
                label={t('ws.records.sessions.satisfaction.resolved', locale)}
                value={item.result.resolved == null ? t('ws.records.sessions.satisfaction.notEnabled', locale) : item.result.resolved ? t('ws.records.sessions.satisfaction.resolved', locale) : t('ws.records.sessions.satisfaction.unresolved', locale)}
              />
            )}
            <InfoRow label={t('ws.records.sessions.satisfaction.rating', locale)} value={resultLabel(item.result, locale)} />
            <InfoRow label={t('ws.records.sessions.satisfaction.labels', locale)} value={item.result.labels.length ? item.result.labels.join('、') : '-'} />
            <InfoRow label={t('ws.records.sessions.satisfaction.remark', locale)} value={item.result.remark || '-'} />
          </div>
        ))}
        <div className="border-t border-border pt-4">
          <InfoRow label={t('ws.records.sessions.satisfaction.submittedAt', locale)} value={formatDateTime(displaySubmittedAt)} />
        </div>
      </div>
    </div>
  )
}

function InfoRow({
  label,
  value,
  action,
}: {
  label: string
  value: ReactNode
  action?: ReactNode
}) {
  const valueNode = typeof value === 'string' || typeof value === 'number'
    ? <span className="min-w-0 break-words text-sm text-foreground">{value}</span>
    : <div className="min-w-0">{value}</div>

  return (
    <div className="flex min-w-0 items-start gap-3">
      <span className="w-24 shrink-0 pt-0.5 text-xs text-muted-foreground">{label}</span>
      <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
        {valueNode}
        {action}
      </div>
    </div>
  )
}

function RelatedTicketsLinks({
  tickets,
}: {
  tickets: SessionRecordDetail['related_tickets']
}) {
  if (!tickets.length) {
    return <span className="text-sm text-foreground">-</span>
  }

  return (
    <div className="flex min-w-0 flex-wrap gap-x-2 gap-y-1">
      {tickets.map((ticket) => (
        <Link
          key={ticket.id}
          href={`/workspace/tickets/${ticket.id}?from=list`}
          className="max-w-full truncate text-sm font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {ticket.ticket_number || `#${ticket.id}`}
        </Link>
      ))}
    </div>
  )
}
