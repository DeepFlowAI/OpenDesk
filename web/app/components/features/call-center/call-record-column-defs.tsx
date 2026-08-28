import { IconPhoneIncoming, IconPhoneOutgoing } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'

import type { Locale } from '@/context/locale-store'
import type { CallRecordListItem } from '@/models/call-center'
import { t } from '@/utils/i18n'

export type CallRecordColumnDef = {
  key: string
  labelKey: string
  thClass: string
  tdClass: string
  defaultVisible: boolean
  required?: boolean
  render: (record: CallRecordListItem, locale: Locale) => ReactNode
}

function dateTime(value: string | null, locale: Locale): string {
  if (!value) return '—'
  return new Date(value).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function duration(value: number | null): string {
  if (value == null) return '—'
  const seconds = Math.floor(value / 1000)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainder = seconds % 60
  const tail = `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
  return hours > 0 ? `${String(hours).padStart(2, '0')}:${tail}` : tail
}

function optionLabel(group: string, value: string | null, locale: Locale): string {
  if (!value) return '—'
  const key = `ws.records.calls.option.${group}.${value}`
  const translated = t(key, locale)
  return translated === key ? value : translated
}

function DirectionCell({ record, locale }: { record: CallRecordListItem; locale: Locale }) {
  const inbound = record.direction === 'inbound'
  const Icon = inbound ? IconPhoneIncoming : IconPhoneOutgoing
  return (
    <span className={inbound
      ? 'inline-flex items-center gap-1 rounded bg-info/10 px-1.5 py-0.5 text-xs text-info'
      : 'inline-flex items-center gap-1 rounded bg-success/10 px-1.5 py-0.5 text-xs text-success'}
    >
      <Icon size={11} />
      {optionLabel('direction', record.direction, locale)}
    </span>
  )
}

function UserCell({ record, locale }: { record: CallRecordListItem; locale: Locale }) {
  const label = record.user_name || record.user_public_id
  if (label) return <span className="block max-w-[180px] truncate text-foreground">{label}</span>
  return (
    <span className="inline-flex rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
      {optionLabel('association', record.user_association_status, locale)}
    </span>
  )
}

function QueueCell({ record, locale }: { record: CallRecordListItem; locale: Locale }) {
  if (!record.last_queue?.name) return <span>—</span>
  return (
    <span className="flex max-w-[180px] items-center gap-1.5">
      <span className="truncate" title={record.last_queue.name}>{record.last_queue.name}</span>
      <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px]">
        {t(`ws.records.calls.filter.${record.last_queue.queue_type === 'employee' ? 'personalQueue' : 'groupQueue'}`, locale)}
      </span>
    </span>
  )
}

function CallIdCell({ value, locale }: { value: string; locale: Locale }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      toast.success(t('ws.records.calls.copySuccess', locale))
    } catch {
      toast.error(t('ws.records.calls.copyFailed', locale))
    }
  }
  return (
    <button type="button" title={value} onClick={(event) => { event.stopPropagation(); void copy() }} className="block max-w-[180px] truncate text-left hover:text-foreground hover:underline">
      {value}
    </button>
  )
}

function StatusCell({ group, value, locale }: { group: string; value: string | null; locale: Locale }) {
  if (!value) return <span>—</span>
  return (
    <span className="inline-flex rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
      {optionLabel(group, value, locale)}
    </span>
  )
}

function SatisfactionCell({ record, locale }: { record: CallRecordListItem; locale: Locale }) {
  if (!record.satisfaction_result) return <span>—</span>
  const result = optionLabel('satisfactionResult', record.satisfaction_result, locale)
  if (!record.satisfaction_primary_option_label) return <StatusCell group="satisfactionResult" value={record.satisfaction_result} locale={locale} />
  return (
    <span className="inline-flex max-w-[220px] flex-wrap items-center gap-1.5">
      <span>{record.satisfaction_primary_option_label}</span>
      {(record.satisfaction_answer_count ?? 0) > 1 && (
        <span className="text-xs text-muted-foreground">
          {t('ws.records.calls.satisfaction.answerCount', locale, { count: record.satisfaction_answer_count ?? 0 })}
        </span>
      )}
      {record.satisfaction_result === 'partial' && <span className="text-xs text-warning">{result}</span>}
    </span>
  )
}

const text = (value: string | number | null | undefined) => value == null || value === '' ? '—' : String(value)

export const CALL_RECORD_COLUMN_DEFS: CallRecordColumnDef[] = [
  { key: 'customer_number', labelKey: 'ws.records.calls.col.customerNumber', thClass: 'w-[170px]', tdClass: 'max-w-[170px] truncate text-foreground', defaultVisible: true, required: true, render: (r, l) => r.customer_number || t('ws.records.calls.unknownNumber', l) },
  { key: 'direction', labelKey: 'ws.records.calls.col.direction', thClass: 'w-[100px]', tdClass: '', defaultVisible: true, render: (r, l) => <DirectionCell record={r} locale={l} /> },
  { key: 'user', labelKey: 'ws.records.calls.col.user', thClass: 'w-[180px]', tdClass: '', defaultVisible: true, render: (r, l) => <UserCell record={r} locale={l} /> },
  { key: 'user_association_status', labelKey: 'ws.records.calls.col.userAssociationStatus', thClass: 'w-[130px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r, l) => optionLabel('association', r.user_association_status, l) },
  { key: 'service_number', labelKey: 'ws.records.calls.col.serviceNumber', thClass: 'w-[170px]', tdClass: 'max-w-[170px] truncate text-muted-foreground', defaultVisible: true, render: (r) => text(r.service_number) },
  { key: 'call_id', labelKey: 'ws.records.calls.col.callId', thClass: 'w-[180px]', tdClass: 'max-w-[180px] font-mono text-muted-foreground', defaultVisible: false, render: (r, l) => <CallIdCell value={r.call_id} locale={l} /> },
  { key: 'call_source', labelKey: 'ws.records.calls.col.callSource', thClass: 'w-[150px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r, l) => optionLabel('callSource', r.call_source, l) },
  { key: 'initiator_agent', labelKey: 'ws.records.calls.col.initiatorAgent', thClass: 'w-[140px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r) => text(r.initiator_agent_name) },
  { key: 'last_queue', labelKey: 'ws.records.calls.col.lastQueue', thClass: 'w-[180px]', tdClass: 'text-muted-foreground', defaultVisible: true, render: (r, l) => <QueueCell record={r} locale={l} /> },
  { key: 'last_serving_agent', labelKey: 'ws.records.calls.col.lastServingAgent', thClass: 'w-[140px]', tdClass: 'text-muted-foreground', defaultVisible: true, render: (r) => text(r.last_serving_agent_name) },
  { key: 'lifecycle_status', labelKey: 'ws.records.calls.col.lifecycleStatus', thClass: 'w-[110px]', tdClass: '', defaultVisible: false, render: (r, l) => <StatusCell group="lifecycleStatus" value={r.lifecycle_status} locale={l} /> },
  { key: 'finalization_status', labelKey: 'ws.records.calls.col.finalizationStatus', thClass: 'w-[130px]', tdClass: '', defaultVisible: false, render: (r, l) => <StatusCell group="finalizationStatus" value={r.finalization_status} locale={l} /> },
  { key: 'actual_reception_type', labelKey: 'ws.records.calls.col.receptionType', thClass: 'w-[130px]', tdClass: '', defaultVisible: false, render: (r, l) => <StatusCell group="receptionType" value={r.actual_reception_type} locale={l} /> },
  { key: 'call_result', labelKey: 'ws.records.calls.col.callResult', thClass: 'w-[150px]', tdClass: '', defaultVisible: true, render: (r, l) => <StatusCell group="callResult" value={r.call_result || r.lifecycle_status} locale={l} /> },
  { key: 'hangup_party', labelKey: 'ws.records.calls.col.hangupParty', thClass: 'w-[110px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r, l) => optionLabel('hangupParty', r.hangup_party, l) },
  { key: 'hangup_reason_code', labelKey: 'ws.records.calls.col.hangupReason', thClass: 'w-[170px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r, l) => optionLabel('hangupReason', r.hangup_reason_code, l) },
  { key: 'started_at', labelKey: 'ws.records.calls.col.startedAt', thClass: 'min-w-[190px] whitespace-nowrap', tdClass: 'min-w-[190px] whitespace-nowrap text-muted-foreground', defaultVisible: true, render: (r, l) => dateTime(r.started_at, l) },
  { key: 'customer_connected_at', labelKey: 'ws.records.calls.col.customerConnectedAt', thClass: 'min-w-[190px] whitespace-nowrap', tdClass: 'min-w-[190px] whitespace-nowrap text-muted-foreground', defaultVisible: false, render: (r, l) => dateTime(r.customer_connected_at, l) },
  { key: 'first_agent_connected_at', labelKey: 'ws.records.calls.col.firstAgentConnectedAt', thClass: 'min-w-[190px] whitespace-nowrap', tdClass: 'min-w-[190px] whitespace-nowrap text-muted-foreground', defaultVisible: false, render: (r, l) => dateTime(r.first_agent_connected_at, l) },
  { key: 'human_service_ended_at', labelKey: 'ws.records.calls.col.humanServiceEndedAt', thClass: 'min-w-[190px] whitespace-nowrap', tdClass: 'min-w-[190px] whitespace-nowrap text-muted-foreground', defaultVisible: false, render: (r, l) => dateTime(r.human_service_ended_at, l) },
  { key: 'ended_at', labelKey: 'ws.records.calls.col.endedAt', thClass: 'min-w-[190px] whitespace-nowrap', tdClass: 'min-w-[190px] whitespace-nowrap text-muted-foreground', defaultVisible: false, render: (r, l) => dateTime(r.ended_at, l) },
  { key: 'total_duration_ms', labelKey: 'ws.records.calls.col.totalDuration', thClass: 'w-[120px]', tdClass: 'font-mono text-muted-foreground', defaultVisible: false, render: (r) => duration(r.total_duration_ms) },
  { key: 'customer_ring_duration_ms', labelKey: 'ws.records.calls.col.customerRingDuration', thClass: 'w-[130px]', tdClass: 'font-mono text-muted-foreground', defaultVisible: false, render: (r) => duration(r.customer_ring_duration_ms) },
  { key: 'agent_wait_duration_ms', labelKey: 'ws.records.calls.col.agentWaitDuration', thClass: 'w-[130px]', tdClass: 'font-mono text-muted-foreground', defaultVisible: true, render: (r) => duration(r.agent_wait_duration_ms) },
  { key: 'customer_agent_talk_duration_ms', labelKey: 'ws.records.calls.col.talkDuration', thClass: 'w-[130px]', tdClass: 'font-mono text-muted-foreground', defaultVisible: true, render: (r) => duration(r.customer_agent_talk_duration_ms) },
  { key: 'recording_status', labelKey: 'ws.records.calls.col.recordingStatus', thClass: 'w-[130px]', tdClass: '', defaultVisible: false, render: (r, l) => <StatusCell group="recordingStatus" value={r.recording_status} locale={l} /> },
  { key: 'satisfaction_result', labelKey: 'ws.records.calls.col.satisfactionResult', thClass: 'w-[190px]', tdClass: '', defaultVisible: true, render: (r, l) => <SatisfactionCell record={r} locale={l} /> },
  { key: 'satisfaction_trigger_source', labelKey: 'ws.records.calls.col.satisfactionSource', thClass: 'w-[150px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r, l) => optionLabel('satisfactionSource', r.satisfaction_trigger_source, l) },
  { key: 'satisfaction_primary_option_label', labelKey: 'ws.records.calls.col.satisfactionPrimaryOption', thClass: 'w-[180px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r) => text(r.satisfaction_primary_option_label) },
  { key: 'satisfaction_answer_count', labelKey: 'ws.records.calls.col.satisfactionAnswerCount', thClass: 'w-[130px]', tdClass: 'text-muted-foreground', defaultVisible: false, render: (r) => text(r.satisfaction_answer_count) },
  { key: 'satisfaction_duration_ms', labelKey: 'ws.records.calls.col.satisfactionDuration', thClass: 'w-[130px]', tdClass: 'font-mono text-muted-foreground', defaultVisible: false, render: (r) => duration(r.satisfaction_duration_ms) },
]
