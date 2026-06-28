'use client'

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { IconSearch, IconLoader2, IconCalendar, IconChevronDown, IconChevronRight, IconColumns3 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSessionRecords } from '@/service/use-session-records'
import { useEmployees } from '@/service/use-employees'
import { useSatisfactionFilterOptions } from '@/service/use-satisfaction-survey'
import { useAuthStore } from '@/context/auth-store'
import { getDataScope } from '@/utils/permissions'
import { DateInput } from '@/components/ui/time-input'
import { WorkspaceColumnsDrawer, type WorkspaceColumnConfigItem } from '@/components/workspace/columns-drawer'
import { formatSessionDuration } from './session-duration'
import type { BotHandoffStatus, QueueResult, SessionRecord, SessionRecordFilters, SessionRecordType } from '@/models/session-record'

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
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

function receptionFinalAgentName(record: SessionRecord): string {
  if (record.reception_final_agent_id == null) return '-'
  const match = record.reception_participants.find((p) => p.agent_id === record.reception_final_agent_id)
  return match?.name || `#${record.reception_final_agent_id}`
}

function ReceptionParticipantsCell({ record, locale }: { record: SessionRecord; locale: Locale }) {
  const participants = record.reception_participants
  if (!participants.length) return <span>-</span>
  const head = participants.slice(0, 2).map((p) => p.name || `#${p.agent_id}`)
  const extra = participants.length - head.length
  return (
    <span className="truncate">
      {head.join('、')}
      {extra > 0 && (
        <span className="ml-1 text-xs text-muted-foreground">
          {t('ws.records.sessions.col.receptionParticipantsMore', locale).replace('{count}', String(extra))}
        </span>
      )}
    </span>
  )
}

function QueueNameCell({
  queue,
  locale,
}: {
  queue: SessionRecord['last_assigned_queue']
  locale: Locale
}) {
  if (!queue?.name) return null
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      <span className="min-w-0 truncate" title={queue.name}>{queue.name}</span>
      {queue.queue_type === 'employee' && (
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] leading-4 text-muted-foreground">
          {t('ws.records.queue.personalQueue', locale)}
        </span>
      )}
    </div>
  )
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

function SessionTypeBadge({ value, locale }: { value: SessionRecordType | null; locale: Locale }) {
  if (!value) return null
  return (
    <StatusBadge
      label={t(`ws.records.sessions.sessionType.${value}`, locale)}
      className={sessionTypeClassName[value]}
    />
  )
}

function BotHandoffBadge({ value, locale }: { value: BotHandoffStatus | null; locale: Locale }) {
  if (!value) return null
  return (
    <StatusBadge
      label={t(`ws.records.sessions.botHandoff.${value}`, locale)}
      className={botHandoffClassName[value]}
    />
  )
}

function QueueResultBadge({ value, locale }: { value: QueueResult | null; locale: Locale }) {
  if (!value) return <span className="text-sm text-muted-foreground">-</span>
  return (
    <StatusBadge
      label={t(`ws.records.sessions.queueResult.${value}`, locale)}
      className={queueResultClassName[value]}
    />
  )
}

const sessionStatusClassName: Record<SessionRecord['status'], string> = {
  queued: 'bg-warning/10 text-warning',
  active: 'bg-success/10 text-success',
  bot: 'bg-info/10 text-info',
  handoff_pending: 'bg-warning/10 text-warning',
  closed: 'bg-muted text-muted-foreground',
}

function SessionStatusBadge({ value, locale }: { value: SessionRecord['status']; locale: Locale }) {
  if (!value) return <span className="text-sm text-muted-foreground">-</span>
  return (
    <StatusBadge
      label={t(`ws.records.sessions.status.${value}`, locale)}
      className={sessionStatusClassName[value] ?? 'bg-muted text-muted-foreground'}
    />
  )
}

function satisfactionLabel(status: string, locale: string) {
  if (status === 'none') return locale === 'zh' ? '未评价' : 'Not rated'
  if (status === 'invited') return locale === 'zh' ? '已邀请' : 'Invited'
  if (status === 'submitted') return locale === 'zh' ? '已评价' : 'Rated'
  return status
}

function SatisfactionSummaryCell({ record, locale }: { record: SessionRecord; locale: string }) {
  const summary = record.satisfaction
  if (!summary || summary.status === 'none') {
    return <span className="text-sm text-muted-foreground">{satisfactionLabel('none', locale)}</span>
  }
  if (summary.status === 'invited') {
    return (
      <span className="inline-flex items-center rounded-full bg-[#FEF3C7] px-2 py-0.5 text-xs font-medium text-[#92400E]">
        {satisfactionLabel('invited', locale)}
      </span>
    )
  }
  return (
    <div className="flex max-w-[220px] flex-wrap gap-1">
      {summary.labels.length > 0 ? summary.labels.map((label) => (
        <span key={label} className="inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
          {label}
        </span>
      )) : (
        <span className="inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
          {satisfactionLabel(summary.status, locale)}
        </span>
      )}
    </div>
  )
}

// ── Column definitions ──
// Fixed session-record columns. Each entry owns its header label, cell styling
// and render logic so the table body can be driven by a visibility/order config.

type SessionColumnDef = {
  key: string
  labelKey: string
  thClass: string
  tdClass: string
  /** Whether the column is shown by default (when the user has no saved override). */
  defaultVisible?: boolean
  render: (record: SessionRecord, locale: Locale) => React.ReactNode
}

const SESSION_COLUMN_DEFS: SessionColumnDef[] = [
  {
    key: 'visitor',
    labelKey: 'ws.records.sessions.col.visitor',
    thClass: '',
    tdClass: 'text-foreground',
    render: (record) => record.visitor?.name || '-',
  },
  {
    key: 'shareCode',
    labelKey: 'ws.records.sessions.col.shareCode',
    thClass: 'w-[120px]',
    tdClass: 'font-mono text-muted-foreground',
    render: (record) => record.share_code || record.public_id || '-',
  },
  {
    key: 'sessionType',
    labelKey: 'ws.records.sessions.col.sessionType',
    thClass: 'w-[96px]',
    tdClass: '',
    render: (record, locale) => <SessionTypeBadge value={record.session_type} locale={locale} />,
  },
  {
    key: 'botHandoff',
    labelKey: 'ws.records.sessions.col.botHandoff',
    thClass: 'w-[160px]',
    tdClass: '',
    render: (record, locale) => <BotHandoffBadge value={record.bot_handoff_status} locale={locale} />,
  },
  {
    key: 'channelType',
    labelKey: 'ws.records.sessions.col.channelType',
    thClass: 'w-[100px]',
    tdClass: 'text-muted-foreground',
    render: (record) => record.channel?.channel_type || '-',
  },
  {
    key: 'channelName',
    labelKey: 'ws.records.sessions.col.channelName',
    thClass: 'w-[150px]',
    tdClass: 'text-muted-foreground',
    render: (record) => record.channel?.name || '-',
  },
  {
    key: 'lastAssignedQueue',
    labelKey: 'ws.records.sessions.col.lastAssignedQueue',
    thClass: 'w-[160px]',
    tdClass: 'max-w-[160px] text-muted-foreground',
    render: (record, locale) => <QueueNameCell queue={record.last_assigned_queue} locale={locale} />,
  },
  {
    key: 'queueDuration',
    labelKey: 'ws.records.sessions.col.queueDuration',
    thClass: 'w-[110px]',
    tdClass: 'font-mono text-muted-foreground',
    render: (record) => formatQueueDuration(record.queue_duration_seconds),
  },
  {
    key: 'hasQueue',
    labelKey: 'ws.records.sessions.col.hasQueue',
    thClass: 'w-[92px]',
    tdClass: 'text-muted-foreground',
    render: (record, locale) =>
      record.has_queue
        ? t('ws.records.sessions.hasQueue.yes', locale)
        : t('ws.records.sessions.hasQueue.no', locale),
  },
  {
    key: 'queueResult',
    labelKey: 'ws.records.sessions.col.queueResult',
    thClass: 'w-[110px]',
    tdClass: '',
    render: (record, locale) => <QueueResultBadge value={record.queue_result} locale={locale} />,
  },
  {
    key: 'queueEnteredAt',
    labelKey: 'ws.records.sessions.col.queueEnteredAt',
    thClass: 'min-w-[170px] whitespace-nowrap',
    tdClass: 'min-w-[170px] whitespace-nowrap text-muted-foreground',
    render: (record) => formatDateTime(record.queue_entered_at),
  },
  {
    key: 'queueAssignedAt',
    labelKey: 'ws.records.sessions.col.queueAssignedAt',
    thClass: 'min-w-[170px] whitespace-nowrap',
    tdClass: 'min-w-[170px] whitespace-nowrap text-muted-foreground',
    render: (record) => formatDateTime(record.queue_assigned_at),
  },
  {
    key: 'agent',
    labelKey: 'ws.records.sessions.col.agent',
    thClass: 'w-[120px]',
    tdClass: 'text-muted-foreground',
    render: (record) => record.agent?.display_name || record.agent?.name || '-',
  },
  {
    key: 'satisfaction',
    labelKey: 'ws.records.sessions.col.satisfaction',
    thClass: 'w-[180px]',
    tdClass: '',
    render: (record, locale) => <SatisfactionSummaryCell record={record} locale={locale} />,
  },
  {
    key: 'startTime',
    labelKey: 'ws.records.sessions.col.startTime',
    thClass: 'min-w-[170px] whitespace-nowrap',
    tdClass: 'min-w-[170px] whitespace-nowrap text-muted-foreground',
    render: (record) => formatDateTime(record.started_at),
  },
  {
    key: 'endTime',
    labelKey: 'ws.records.sessions.col.endTime',
    thClass: 'min-w-[170px] whitespace-nowrap',
    tdClass: 'min-w-[170px] whitespace-nowrap text-muted-foreground',
    render: (record, locale) =>
      record.ended_at ? (
        formatDateTime(record.ended_at)
      ) : (
        <span className="inline-flex items-center rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
          {t('ws.records.sessions.status.active', locale)}
        </span>
      ),
  },
  {
    key: 'duration',
    labelKey: 'ws.records.sessions.col.duration',
    thClass: 'w-[100px]',
    tdClass: 'text-muted-foreground',
    render: (record) => formatSessionDuration(record),
  },
  // Fields exposed by the API but hidden by default — toggle on via the column drawer.
  {
    key: 'status',
    labelKey: 'ws.records.sessions.col.status',
    thClass: 'w-[110px]',
    tdClass: '',
    defaultVisible: false,
    render: (record, locale) => <SessionStatusBadge value={record.status} locale={locale} />,
  },
  {
    key: 'firstResponse',
    labelKey: 'ws.records.sessions.col.firstResponse',
    thClass: 'w-[120px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatSeconds(record.first_human_response_seconds),
  },
  {
    key: 'agentResponseCount',
    labelKey: 'ws.records.sessions.col.agentResponseCount',
    thClass: 'w-[110px]',
    tdClass: 'text-muted-foreground',
    defaultVisible: false,
    render: (record) => (record.agent_response_count == null ? '-' : String(record.agent_response_count)),
  },
  {
    key: 'agentAvgResponse',
    labelKey: 'ws.records.sessions.col.agentAvgResponse',
    thClass: 'w-[120px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatSeconds(record.agent_avg_response_seconds),
  },
  {
    key: 'messageCount',
    labelKey: 'ws.records.sessions.col.messageCount',
    thClass: 'w-[110px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.message_count),
  },
  {
    key: 'visitorMessageCount',
    labelKey: 'ws.records.sessions.col.visitorMessageCount',
    thClass: 'w-[120px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.visitor_message_count),
  },
  {
    key: 'agentMessageCount',
    labelKey: 'ws.records.sessions.col.agentMessageCount',
    thClass: 'w-[120px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.agent_message_count),
  },
  {
    key: 'botPhaseMessageCount',
    labelKey: 'ws.records.sessions.col.botPhaseMessageCount',
    thClass: 'w-[150px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.bot_phase_message_count),
  },
  {
    key: 'humanPhaseMessageCount',
    labelKey: 'ws.records.sessions.col.humanPhaseMessageCount',
    thClass: 'w-[150px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.human_phase_message_count),
  },
  {
    key: 'humanPhaseVisitorMessageCount',
    labelKey: 'ws.records.sessions.col.humanPhaseVisitorMessageCount',
    thClass: 'w-[170px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.human_phase_visitor_message_count),
  },
  {
    key: 'humanPhaseAgentMessageCount',
    labelKey: 'ws.records.sessions.col.humanPhaseAgentMessageCount',
    thClass: 'w-[170px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.human_phase_agent_message_count),
  },
  {
    key: 'createdAt',
    labelKey: 'ws.records.sessions.col.createdAt',
    thClass: 'min-w-[170px] whitespace-nowrap',
    tdClass: 'min-w-[170px] whitespace-nowrap text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatDateTime(record.created_at),
  },
  {
    key: 'endedBy',
    labelKey: 'ws.records.sessions.col.endedBy',
    thClass: 'w-[110px]',
    tdClass: 'text-muted-foreground',
    defaultVisible: false,
    render: (record, locale) => endedByLabel(record.ended_by, locale),
  },
  {
    key: 'visitorSystem',
    labelKey: 'ws.records.sessions.col.visitorSystem',
    thClass: 'w-[130px]',
    tdClass: 'text-muted-foreground',
    defaultVisible: false,
    render: (record) => record.visitor_system || '-',
  },
  {
    key: 'visitorBrowser',
    labelKey: 'ws.records.sessions.col.visitorBrowser',
    thClass: 'w-[130px]',
    tdClass: 'text-muted-foreground',
    defaultVisible: false,
    render: (record) => record.visitor_browser || '-',
  },
  {
    key: 'visitorIp',
    labelKey: 'ws.records.sessions.col.visitorIp',
    thClass: 'w-[130px]',
    tdClass: 'text-muted-foreground',
    defaultVisible: false,
    render: (record) => record.visitor_ip || '-',
  },
  {
    key: 'receptionSegmentCount',
    labelKey: 'ws.records.sessions.col.receptionSegmentCount',
    thClass: 'w-[110px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.reception_segment_count),
  },
  {
    key: 'receptionTransferCount',
    labelKey: 'ws.records.sessions.col.receptionTransferCount',
    thClass: 'w-[110px]',
    tdClass: 'font-mono text-muted-foreground',
    defaultVisible: false,
    render: (record) => formatCount(record.reception_transfer_count),
  },
  {
    key: 'receptionParticipants',
    labelKey: 'ws.records.sessions.col.receptionParticipants',
    thClass: 'w-[180px]',
    tdClass: 'max-w-[180px] text-muted-foreground',
    defaultVisible: false,
    render: (record, locale) => <ReceptionParticipantsCell record={record} locale={locale} />,
  },
  {
    key: 'receptionFinalAgent',
    labelKey: 'ws.records.sessions.col.receptionFinalAgent',
    thClass: 'w-[130px]',
    tdClass: 'text-muted-foreground',
    defaultVisible: false,
    render: (record) => receptionFinalAgentName(record),
  },
]

// ── localStorage helpers for personal column config (per tenant) ──

const COL_STORAGE_PREFIX = 'ws_session_cols_'

function getColStorageKey(tenantId: number | null): string {
  return `${COL_STORAGE_PREFIX}${tenantId ?? 'unknown'}`
}

function readColsFromStorage(tenantId: number | null): WorkspaceColumnConfigItem[] | null {
  try {
    const raw = localStorage.getItem(getColStorageKey(tenantId))
    if (!raw) return null
    return JSON.parse(raw) as WorkspaceColumnConfigItem[]
  } catch {
    return null
  }
}

function writeColsToStorage(tenantId: number | null, cols: WorkspaceColumnConfigItem[]): void {
  try {
    localStorage.setItem(getColStorageKey(tenantId), JSON.stringify(cols))
  } catch { /* quota exceeded – ignore */ }
}

function removeColsFromStorage(tenantId: number | null): void {
  try {
    localStorage.removeItem(getColStorageKey(tenantId))
  } catch { /* ignore */ }
}

type Props = {
  onSelectRecord: (record: SessionRecord) => void
}

const PER_PAGE_OPTIONS = [20, 50, 100]

export function SessionTable({ onSelectRecord }: Props) {
  const { locale } = useLocaleStore()
  const { user } = useAuthStore()
  const sessionScope = getDataScope(user, 'session_record')
  const canFilterByAgent = sessionScope === 'all' || sessionScope === 'group'
  const userGroupIds = useMemo(() => new Set(user?.group_ids ?? []), [user?.group_ids])
  const tenantId = user?.tenant_id ?? null

  // Column visibility/order — persisted per tenant in localStorage.
  const [columnsDrawerOpen, setColumnsDrawerOpen] = useState(false)
  const [columnOverrides, setColumnOverrides] = useState<WorkspaceColumnConfigItem[] | null>(null)
  const colInitRef = useRef(false)
  useEffect(() => {
    if (colInitRef.current) return
    colInitRef.current = true
    setColumnOverrides(readColsFromStorage(tenantId))
  }, [tenantId])
  const hasColumnOverride = columnOverrides !== null

  const columnFields = useMemo(
    () => SESSION_COLUMN_DEFS.map((c) => ({ id: null, key: c.key, name: t(c.labelKey, locale) })),
    [locale],
  )
  const defaultColumnConfig = useMemo<WorkspaceColumnConfigItem[]>(
    () => SESSION_COLUMN_DEFS.map((c, i) => ({
      field_id: null,
      field_key: c.key,
      visible: c.defaultVisible !== false,
      sort_order: i,
    })),
    [],
  )
  // Reconcile a saved override against the current column defs: append any
  // column keys missing from the saved config (e.g. newly shipped columns) as
  // hidden so they still surface in the column drawer instead of disappearing.
  const reconciledOverrides = useMemo<WorkspaceColumnConfigItem[] | null>(() => {
    if (!columnOverrides) return null
    const savedKeys = new Set(columnOverrides.map((c) => c.field_key))
    const missing = SESSION_COLUMN_DEFS.filter((c) => !savedKeys.has(c.key))
    if (missing.length === 0) return columnOverrides
    const base = columnOverrides.reduce((max, c) => Math.max(max, c.sort_order), -1)
    return [
      ...columnOverrides,
      ...missing.map((c, i) => ({
        field_id: null,
        field_key: c.key,
        visible: false,
        sort_order: base + 1 + i,
      })),
    ]
  }, [columnOverrides])

  const visibleColumns = useMemo<SessionColumnDef[]>(() => {
    if (!reconciledOverrides) return SESSION_COLUMN_DEFS.filter((c) => c.defaultVisible !== false)
    const defByKey = new Map(SESSION_COLUMN_DEFS.map((c) => [c.key, c]))
    return reconciledOverrides
      .filter((c) => c.visible && c.field_key != null && defByKey.has(c.field_key))
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((c) => defByKey.get(c.field_key as string) as SessionColumnDef)
  }, [reconciledOverrides])

  const handleApplyColumns = useCallback((cols: WorkspaceColumnConfigItem[]) => {
    setColumnOverrides(cols)
    writeColsToStorage(tenantId, cols)
  }, [tenantId])

  const handleResetColumns = useCallback(() => {
    setColumnOverrides(null)
    removeColsFromStorage(tenantId)
  }, [tenantId])

  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)

  const [filters, setFilters] = useState<SessionRecordFilters>({
    page: 1,
    per_page: 20,
    start_date: sevenDaysAgo.toISOString(),
    end_date: now.toISOString(),
  })
  const [draftKeyword, setDraftKeyword] = useState('')
  const [draftStartDate, setDraftStartDate] = useState(sevenDaysAgo.toISOString().slice(0, 10))
  const [draftEndDate, setDraftEndDate] = useState(now.toISOString().slice(0, 10))
  const [draftAgentId, setDraftAgentId] = useState<number | undefined>(undefined)
  const [draftSessionType, setDraftSessionType] = useState<SessionRecordType | ''>('')
  const [draftHasQueue, setDraftHasQueue] = useState<'true' | 'false' | ''>('')
  const [draftSatisfactionStatus, setDraftSatisfactionStatus] = useState('')
  const [draftResolved, setDraftResolved] = useState('')
  const [draftServiceOption, setDraftServiceOption] = useState('')
  const [draftServiceLabel, setDraftServiceLabel] = useState('')
  const [draftProductOption, setDraftProductOption] = useState('')
  const [draftProductLabel, setDraftProductLabel] = useState('')
  const [satisfactionFiltersExpanded, setSatisfactionFiltersExpanded] = useState(false)

  const { data, isLoading } = useSessionRecords(filters)
  const { data: satisfactionOptions } = useSatisfactionFilterOptions()
  const hasSatisfactionFilters = satisfactionOptions?.configured === true
  const satisfactionFilterActiveCount = [
    draftSatisfactionStatus,
    draftResolved,
    draftServiceOption,
    draftServiceLabel,
    draftProductOption,
    draftProductLabel,
  ].filter(Boolean).length
  const { data: employeesData } = useEmployees(
    { per_page: 200, status: 'active' },
    { enabled: canFilterByAgent }
  )
  const agentOptions = useMemo(() => {
    const items = employeesData?.items ?? []
    if (sessionScope !== 'group') return items
    return items.filter((emp) => {
      const groupIds = emp.group_ids ?? []
      if (emp.id === user?.id) return true
      return groupIds.some((groupId) => userGroupIds.has(groupId))
    })
  }, [employeesData?.items, sessionScope, user?.id, userGroupIds])

  const handleSearch = useCallback(() => {
    setFilters({
      ...filters,
      page: 1,
      start_date: draftStartDate ? new Date(draftStartDate + 'T00:00:00').toISOString() : undefined,
      end_date: draftEndDate ? new Date(draftEndDate + 'T23:59:59').toISOString() : undefined,
      agent_id: draftAgentId,
      session_type: draftSessionType || undefined,
      has_queue: draftHasQueue ? draftHasQueue === 'true' : undefined,
      keyword: draftKeyword || undefined,
      satisfaction_status: draftSatisfactionStatus || undefined,
      satisfaction_resolved: draftResolved || undefined,
      satisfaction_service_option: draftServiceOption || undefined,
      satisfaction_service_label: draftServiceLabel || undefined,
      satisfaction_product_option: draftProductOption || undefined,
      satisfaction_product_label: draftProductLabel || undefined,
    })
  }, [filters, draftStartDate, draftEndDate, draftAgentId, draftSessionType, draftHasQueue, draftKeyword, draftSatisfactionStatus, draftResolved, draftServiceOption, draftServiceLabel, draftProductOption, draftProductLabel])

  const handleReset = useCallback(() => {
    const resetStart = sevenDaysAgo.toISOString().slice(0, 10)
    const resetEnd = now.toISOString().slice(0, 10)
    setDraftKeyword('')
    setDraftStartDate(resetStart)
    setDraftEndDate(resetEnd)
    setDraftAgentId(undefined)
    setDraftSessionType('')
    setDraftHasQueue('')
    setDraftSatisfactionStatus('')
    setDraftResolved('')
    setDraftServiceOption('')
    setDraftServiceLabel('')
    setDraftProductOption('')
    setDraftProductLabel('')
    setSatisfactionFiltersExpanded(false)
    setFilters({
      page: 1,
      per_page: 20,
      start_date: new Date(resetStart + 'T00:00:00').toISOString(),
      end_date: new Date(resetEnd + 'T23:59:59').toISOString(),
    })
  }, [])

  const handleRowClick = useCallback(
    (record: SessionRecord, e: React.MouseEvent) => {
      const selection = window.getSelection()
      if (selection && selection.toString().length > 0) return
      onSelectRecord(record)
    },
    [onSelectRecord]
  )

  const items = data?.items || []
  const total = data?.total || 0
  const pages = data?.pages || 0
  const hasActiveFilters = Boolean(
    filters.keyword
    || filters.agent_id
    || filters.session_type
    || filters.has_queue !== undefined
    || filters.satisfaction_status
    || filters.satisfaction_resolved
    || filters.satisfaction_service_option
    || filters.satisfaction_service_label
    || filters.satisfaction_product_option
    || filters.satisfaction_product_label
  )

  return (
    <div className="flex h-full min-w-0 flex-col">
      {/* Filter bar — horizontal padding matches .pen Content Area (24px) */}
      <div className="flex shrink-0 items-end gap-3 px-6 py-4">
        <div className="flex min-w-0 flex-1 flex-wrap items-end gap-3">
        {/* Date range — single grouped control (Date Range Picker) */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-muted-foreground" id="session-records-date-range-label">
            {t('ws.records.sessions.filter.dateRange', locale)}
          </span>
          <div
            className="flex h-9 max-w-md min-w-0 items-center gap-1.5 rounded-lg border border-border bg-background pl-2.5 pr-2"
            role="group"
            aria-labelledby="session-records-date-range-label"
          >
            <IconCalendar size={16} className="shrink-0 text-muted-foreground" aria-hidden />
            <DateInput
              value={draftStartDate}
              onChange={(e) => setDraftStartDate(e.target.value)}
              className="h-7 w-[min(8.5rem,100%)] min-w-0 flex-1 border-0 bg-transparent py-0 text-sm text-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 md:text-sm"
            />
            <span className="shrink-0 text-sm text-muted-foreground">~</span>
            <DateInput
              value={draftEndDate}
              onChange={(e) => setDraftEndDate(e.target.value)}
              className="h-7 w-[min(8.5rem,100%)] min-w-0 flex-1 border-0 bg-transparent py-0 text-sm text-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 md:text-sm"
            />
          </div>
        </div>

        {/* Agent select */}
        {canFilterByAgent && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">
              {t('ws.records.sessions.filter.agent', locale)}
            </label>
            <select
              value={draftAgentId ?? ''}
              onChange={(e) => setDraftAgentId(e.target.value ? Number(e.target.value) : undefined)}
              className="h-9 min-w-[160px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="">{t('ws.records.sessions.filter.allAgents', locale)}</option>
              {agentOptions.map((emp: { id: number; name: string }) => (
                <option key={emp.id} value={emp.id}>
                  {emp.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">
            {t('ws.records.sessions.filter.sessionType', locale)}
          </label>
          <select
            value={draftSessionType}
            onChange={(e) => setDraftSessionType(e.target.value as SessionRecordType | '')}
            className="h-9 min-w-[130px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
            <option value="human">{t('ws.records.sessions.sessionType.human', locale)}</option>
            <option value="bot">{t('ws.records.sessions.sessionType.bot', locale)}</option>
            <option value="bot_human">{t('ws.records.sessions.sessionType.bot_human', locale)}</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">
            {t('ws.records.sessions.filter.hasQueue', locale)}
          </label>
          <select
            value={draftHasQueue}
            onChange={(e) => setDraftHasQueue(e.target.value as 'true' | 'false' | '')}
            className="h-9 min-w-[120px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
            <option value="true">{t('ws.records.sessions.hasQueue.yes', locale)}</option>
            <option value="false">{t('ws.records.sessions.hasQueue.no', locale)}</option>
          </select>
        </div>

        {/* Keyword */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">&nbsp;</label>
          <div className="relative">
            <IconSearch size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={draftKeyword}
              onChange={(e) => setDraftKeyword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder={t('ws.records.sessions.filter.keyword', locale)}
              className="h-9 w-[260px] rounded-md border border-border bg-background pl-8 pr-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>

        {/* Satisfaction filters */}
        {hasSatisfactionFilters && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">&nbsp;</label>
            <button
              type="button"
              onClick={() => setSatisfactionFiltersExpanded((expanded) => !expanded)}
              aria-expanded={satisfactionFiltersExpanded}
              aria-controls="session-records-satisfaction-filters"
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-sm text-foreground transition-colors hover:bg-accent"
            >
              {satisfactionFiltersExpanded
                ? <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
                : <IconChevronRight size={16} className="shrink-0 text-muted-foreground" />}
              <span>{t('ws.records.sessions.filter.satisfactionGroup', locale)}</span>
              {satisfactionFilterActiveCount > 0 && (
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary/10 px-1.5 text-xs font-medium text-primary">
                  {satisfactionFilterActiveCount}
                </span>
              )}
            </button>
          </div>
        )}

        {hasSatisfactionFilters && satisfactionFiltersExpanded && (
          <div id="session-records-satisfaction-filters" className="contents">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">
                {t('ws.records.sessions.filter.satisfactionStatus', locale)}
              </label>
              <select
                value={draftSatisfactionStatus}
                onChange={(e) => setDraftSatisfactionStatus(e.target.value)}
                className="h-9 min-w-[130px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                <option value="none">{t('ws.records.sessions.satisfaction.none', locale)}</option>
                <option value="invited">{t('ws.records.sessions.satisfaction.invited', locale)}</option>
                <option value="submitted">{t('ws.records.sessions.satisfaction.submitted', locale)}</option>
              </select>
            </div>

            {satisfactionOptions.show_resolution && (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.resolved', locale)}
                </label>
                <select
                  value={draftResolved}
                  onChange={(e) => setDraftResolved(e.target.value)}
                  className="h-9 min-w-[120px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  <option value="resolved">{t('ws.records.sessions.satisfaction.resolved', locale)}</option>
                  <option value="unresolved">{t('ws.records.sessions.satisfaction.unresolved', locale)}</option>
                </select>
              </div>
            )}

            {satisfactionOptions.service_options?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.serviceRating', locale)}
                </label>
                <select
                  value={draftServiceOption}
                  onChange={(e) => setDraftServiceOption(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.service_options.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {satisfactionOptions.service_labels?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.serviceLabel', locale)}
                </label>
                <select
                  value={draftServiceLabel}
                  onChange={(e) => setDraftServiceLabel(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.service_labels.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {satisfactionOptions.product_options?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.productRating', locale)}
                </label>
                <select
                  value={draftProductOption}
                  onChange={(e) => setDraftProductOption(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.product_options.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {satisfactionOptions.product_labels?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.productLabel', locale)}
                </label>
                <select
                  value={draftProductLabel}
                  onChange={(e) => setDraftProductLabel(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.product_labels.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>
        )}

        {/* Buttons */}
        <div className="flex gap-2">
          <button
            onClick={handleSearch}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t('ws.records.sessions.filter.search', locale)}
          </button>
          <button
            onClick={handleReset}
            className="h-9 rounded-md border border-border bg-background px-4 text-sm text-foreground transition-colors hover:bg-accent"
          >
            {t('ws.records.sessions.filter.reset', locale)}
          </button>
        </div>
        </div>

        <button
          type="button"
          onClick={() => setColumnsDrawerOpen(true)}
          className={cn(
            'flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-3 text-sm transition-colors',
            hasColumnOverride
              ? 'border-border bg-muted text-foreground hover:bg-muted/80'
              : 'border-border bg-background text-foreground hover:bg-accent',
          )}
        >
          <IconColumns3 size={16} />
          {locale === 'zh' ? '列字段' : 'Columns'}
        </button>
      </div>

      {/* Table — outer frame + horizontal inset so rules do not run flush to the card edges (.pen) */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col px-6 pt-4">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-background">
          <div className="min-h-0 flex-1 overflow-auto">
            {isLoading ? (
              <div className="flex h-full min-h-[200px] items-center justify-center">
                <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 px-4 text-muted-foreground">
                <p className="text-sm">
                  {hasActiveFilters
                    ? t('ws.records.sessions.emptyFiltered', locale)
                    : t('ws.records.sessions.empty', locale)}
                </p>
              </div>
            ) : (
              <table className="w-max min-w-full border-separate border-spacing-0 table-auto">
                <thead>
                  <tr>
                    {visibleColumns.map((col, idx) => {
                      const isFirst = idx === 0
                      const isLast = idx === visibleColumns.length - 1
                      return (
                        <th
                          key={col.key}
                          className={cn(
                            'sticky top-0 z-10 border-b border-border bg-muted py-3 text-left text-xs font-semibold text-muted-foreground',
                            isFirst ? 'pl-4' : 'pl-3',
                            isLast ? 'pr-4' : 'pr-3',
                            isFirst && 'rounded-tl-lg',
                            isLast && 'rounded-tr-lg',
                            col.thClass,
                          )}
                        >
                          {t(col.labelKey, locale)}
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {items.map((record) => (
                    <tr
                      key={record.id}
                      onClick={(e) => handleRowClick(record, e)}
                      className="cursor-pointer transition-colors hover:bg-accent/30"
                    >
                      {visibleColumns.map((col, idx) => {
                        const isFirst = idx === 0
                        const isLast = idx === visibleColumns.length - 1
                        return (
                          <td
                            key={col.key}
                            className={cn(
                              'border-b border-border py-3 text-sm',
                              isFirst ? 'pl-4' : 'pl-3',
                              isLast ? 'pr-4' : 'pr-3',
                              col.tdClass,
                            )}
                          >
                            {col.render(record, locale)}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex shrink-0 items-center justify-between px-6 py-3">
          <span className="text-xs text-muted-foreground">
            {t('ws.records.sessions.pagination.total', locale, { total: String(total) })}
          </span>
          <div className="flex items-center gap-2">
            <select
              value={filters.per_page}
              onChange={(e) => setFilters({ ...filters, page: 1, per_page: Number(e.target.value) })}
              className="h-8 rounded-md border border-border bg-background px-2 text-xs outline-none"
            >
              {PER_PAGE_OPTIONS.map((n) => (
                <option key={n} value={n}>{n} / page</option>
              ))}
            </select>
            <div className="flex gap-1">
              {Array.from({ length: Math.min(pages, 7) }, (_, i) => {
                let pageNum: number
                if (pages <= 7) {
                  pageNum = i + 1
                } else if (filters.page <= 4) {
                  pageNum = i + 1
                } else if (filters.page >= pages - 3) {
                  pageNum = pages - 6 + i
                } else {
                  pageNum = filters.page - 3 + i
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setFilters({ ...filters, page: pageNum })}
                    className={cn(
                      'flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs transition-colors',
                      filters.page === pageNum
                        ? 'bg-primary text-primary-foreground'
                        : 'border border-border text-foreground hover:bg-accent'
                    )}
                  >
                    {pageNum}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {columnsDrawerOpen && (
        <WorkspaceColumnsDrawer
          locale={locale}
          fields={columnFields}
          baselineConfig={defaultColumnConfig}
          currentOverride={reconciledOverrides}
          onApply={handleApplyColumns}
          onReset={handleResetColumns}
          onClose={() => setColumnsDrawerOpen(false)}
        />
      )}
    </div>
  )
}
