'use client'

import { useState, type ReactNode } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { BotHandoffStatus, SessionRecordDetail, SessionRecordType } from '@/models/session-record'
import { SessionSummaryFields } from '@/app/components/features/session-summary/session-summary-fields'
import { useSessionRecordSatisfaction } from '@/service/use-satisfaction-survey'
import type { SatisfactionSurveyResult } from '@/models/satisfaction-survey'

export type SessionInfoTab = 'basic' | 'summary'

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

function formatDuration(startStr: string | null, endStr: string | null, locale: Locale): string {
  if (!startStr) return '-'
  const start = new Date(startStr).getTime()
  const end = endStr ? new Date(endStr).getTime() : Date.now()
  const diff = Math.max(0, Math.floor((end - start) / 1000))
  const h = Math.floor(diff / 3600)
  const m = Math.floor((diff % 3600) / 60)
  const s = diff % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
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
                  label={t('ws.records.sessions.detail.sessionType', locale)}
                  value={<SessionTypeValue value={record.session_type} locale={locale} />}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.botHandoff', locale)}
                  value={<BotHandoffValue value={record.bot_handoff_status} locale={locale} />}
                />
                <InfoRow label={t('ws.records.sessions.detail.channelType', locale)} value={record.channel?.channel_type || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.channelName', locale)} value={record.channel?.name || '-'} />
                <InfoRow
                  label={t('ws.records.sessions.detail.lastAssignedQueue', locale)}
                  value={<QueueNameValue queue={record.last_assigned_queue} locale={locale} />}
                />
                <InfoRow
                  label={t('ws.records.sessions.detail.queueDuration', locale)}
                  value={formatQueueDuration(record.queue_duration_seconds)}
                />
                <InfoRow label={t('ws.records.sessions.detail.agent', locale)} value={record.agent?.display_name || record.agent?.name || '-'} />
                <InfoRow label={t('ws.records.sessions.detail.startTime', locale)} value={formatDateTime(record.started_at)} />
                <InfoRow
                  label={t('ws.records.sessions.detail.endTime', locale)}
                  value={record.ended_at ? formatDateTime(record.ended_at) : t('ws.records.sessions.status.active', locale)}
                />
                <InfoRow label={t('ws.records.sessions.detail.duration', locale)} value={formatDuration(record.started_at, record.ended_at, locale)} />
              </div>
            </div>

            <SatisfactionRecordPanel recordId={record.id} />
          </>
        ) : activeTab === 'summary' ? (
          <SessionSummaryFields conversationId={record.id} onDirtyChange={handleSummaryDirtyChange} />
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
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="flex min-w-0 items-center justify-between gap-3">
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
