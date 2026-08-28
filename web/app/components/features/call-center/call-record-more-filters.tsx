'use client'

import type { Locale } from '@/context/locale-store'
import type { CallRecordFilterOptionsResponse } from '@/models/call-center'
import { UserSelect } from '@/app/components/features/ticket/user-select'
import { t } from '@/utils/i18n'

import type { CallRecordFilterDraft } from './use-call-record-list'
import { CallRecordSearchableSelect } from './call-record-searchable-select'

type Props = {
  locale: Locale
  draft: CallRecordFilterDraft
  onChange: (next: CallRecordFilterDraft) => void
  options?: CallRecordFilterOptionsResponse
  canFilterByOwnership: boolean
}

type Option = [string, string]
const selectClass = 'h-9 w-full rounded-md border border-border bg-background px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'
const inputClass = `${selectClass} min-w-0`

function SelectField({ label, value, onChange, options }: {
  label: string; value: string; onChange: (value: string) => void; options: Option[]
}) {
  return (
    <label className="space-y-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className={selectClass}>
        <option value="">—</option>
        {options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}
      </select>
    </label>
  )
}

function MultiField({ label, values, onChange, options }: {
  label: string; values: string[]; onChange: (values: string[]) => void; options: Option[]
}) {
  return (
    <details className="relative">
      <summary className="flex h-9 cursor-pointer list-none items-center rounded-md border border-border px-2.5 text-sm">
        <span className="truncate">{label}{values.length ? ` (${values.length})` : ''}</span>
      </summary>
      <div className="absolute left-0 top-10 z-40 min-w-full space-y-2 rounded-md border border-border bg-popover p-3 shadow-lg">
        {options.map(([value, optionLabel]) => (
          <label key={value} className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm">
            <input type="checkbox" checked={values.includes(value)} onChange={(event) => onChange(event.target.checked ? [...values, value] : values.filter((item) => item !== value))} />
            {optionLabel}
          </label>
        ))}
      </div>
    </details>
  )
}

function DurationField({ label, minimum, maximum, onMinimum, onMaximum, locale }: {
  label: string; minimum: string; maximum: string; onMinimum: (value: string) => void
  onMaximum: (value: string) => void; locale: Locale
}) {
  return (
    <div className="space-y-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5">
        <input type="number" min="0" max="86400" value={minimum} onChange={(event) => onMinimum(event.target.value)} placeholder={t('ws.records.calls.filter.minSeconds', locale)} className={inputClass} />
        <span className="text-muted-foreground">–</span>
        <input type="number" min="0" max="86400" value={maximum} onChange={(event) => onMaximum(event.target.value)} placeholder={t('ws.records.calls.filter.maxSeconds', locale)} className={inputClass} />
      </div>
    </div>
  )
}

function translatedOptions(locale: Locale, group: string, values: string[]): Option[] {
  return values.map((value) => [value, t(`ws.records.calls.option.${group}.${value}`, locale)])
}

export function CallRecordMoreFilters({ locale, draft, onChange, options, canFilterByOwnership }: Props) {
  const patch = (next: Partial<CallRecordFilterDraft>) => onChange({ ...draft, ...next })
  const queueOptions = (options?.queues ?? []).map((queue) => ({
    value: `${queue.queue_type}:${queue.queue_id}`, label: queue.name,
    description: t(`ws.records.calls.filter.${queue.queue_type === 'employee' ? 'personalQueue' : 'groupQueue'}`, locale),
  }))
  const agentOptions = (options?.agents ?? []).map((agent) => ({ value: String(agent.id), label: agent.name }))
  const satisfactionResults = translatedOptions(locale, 'satisfactionResult', ['not_surveyed', 'completed', 'partial', 'unanswered', 'failed'])
  const satisfactionSources = translatedOptions(locale, 'satisfactionSource', ['auto_transfer', 'agent_invite'])
  const callResultOptions = translatedOptions(locale, 'callResult', ['agent_answered', 'customer_short_abandon', 'agent_no_answer', 'customer_no_answer', 'customer_busy', 'customer_unreachable', 'invalid_number', 'ivr_customer_hangup', 'bot_customer_hangup', 'bot_completed', 'canceled', 'failed'])
    .map(([value, label]) => ({ value, label }))
  const hangupReasonOptions = translatedOptions(locale, 'hangupReason', ['normal_completed', 'customer_hangup', 'agent_hangup', 'supervisor_force_hangup', 'bot_completed', 'no_route', 'no_flow_version', 'queue_limit_reached', 'no_available_queue', 'queue_timeout', 'no_agent_online', 'agent_rejected', 'agent_no_answer', 'customer_no_answer', 'customer_busy', 'customer_power_off', 'customer_unreachable', 'invalid_number', 'canceled', 'originate_failed', 'bridge_failed', 'media_failed', 'reconnect_failed', 'drain_timeout', 'provider_not_found', 'provider_unsupported', 'provider_unresolvable_destination', 'provider_auth_failed', 'provider_balance_insufficient', 'provider_rejected', 'provider_rate_limited', 'provider_timeout', 'provider_unavailable', 'unknown'])
    .map(([value, label]) => ({ value, label }))

  return (
    <div className="mt-4 space-y-4 rounded-lg border border-border bg-muted/20 p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <SelectField label={t('ws.records.calls.filter.callSource', locale)} value={draft.callSource} onChange={(value) => patch({ callSource: value })} options={translatedOptions(locale, 'callSource', ['inbound', 'agent_dial', 'manual_outbound_task', 'auto_outbound'])} />
        <SelectField label={t('ws.records.calls.filter.lifecycleStatus', locale)} value={draft.lifecycleStatus} onChange={(value) => patch({ lifecycleStatus: value })} options={translatedOptions(locale, 'lifecycleStatus', ['active', 'ended'])} />
        <SelectField label={t('ws.records.calls.filter.finalizationStatus', locale)} value={draft.finalizationStatus} onChange={(value) => patch({ finalizationStatus: value })} options={translatedOptions(locale, 'finalizationStatus', ['pending', 'completed', 'incomplete', 'failed'])} />
        <SelectField label={t('ws.records.calls.filter.receptionType', locale)} value={draft.receptionType} onChange={(value) => patch({ receptionType: value })} options={translatedOptions(locale, 'receptionType', ['ivr', 'bot', 'agent', 'bot_agent'])} />
        <div className="space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{t('ws.records.calls.filter.callResult', locale)}</span><CallRecordSearchableSelect value={draft.callResult} onChange={(value) => patch({ callResult: value })} options={callResultOptions} placeholder="—" searchPlaceholder={t('ws.records.calls.filter.searchOption', locale)} emptyText={t('ws.records.calls.filter.emptyOptions', locale)} /></div>
        <SelectField label={t('ws.records.calls.filter.hangupParty', locale)} value={draft.hangupParty} onChange={(value) => patch({ hangupParty: value })} options={translatedOptions(locale, 'hangupParty', ['customer', 'agent', 'supervisor', 'bot', 'system', 'carrier', 'unknown'])} />
        <div className="space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{t('ws.records.calls.filter.hangupReason', locale)}</span><CallRecordSearchableSelect value={draft.hangupReason} onChange={(value) => patch({ hangupReason: value })} options={hangupReasonOptions} placeholder="—" searchPlaceholder={t('ws.records.calls.filter.searchOption', locale)} emptyText={t('ws.records.calls.filter.emptyOptions', locale)} /></div>
        {canFilterByOwnership && <div className="space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{t('ws.records.calls.filter.initiatorAgent', locale)}</span><CallRecordSearchableSelect value={draft.initiatorAgentId} onChange={(value) => patch({ initiatorAgentId: value })} options={agentOptions} placeholder="—" searchPlaceholder={t('ws.records.calls.filter.searchOption', locale)} emptyText={t('ws.records.calls.filter.emptyOptions', locale)} /></div>}
        {canFilterByOwnership && <div className="space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{t('ws.records.calls.filter.lastQueue', locale)}</span><CallRecordSearchableSelect value={draft.queueValue} onChange={(value) => patch({ queueValue: value })} options={queueOptions} placeholder="—" searchPlaceholder={t('ws.records.calls.filter.searchOption', locale)} emptyText={t('ws.records.calls.filter.emptyOptions', locale)} /></div>}
        <div className="space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{t('ws.records.calls.filter.user', locale)}</span><UserSelect value={draft.userId} onChange={(value) => patch({ userId: typeof value === 'number' ? value : null })} placeholder={t('ws.records.calls.filter.searchUser', locale)} /></div>
        <SelectField label={t('ws.records.calls.filter.recordingStatus', locale)} value={draft.recordingStatus} onChange={(value) => patch({ recordingStatus: value })} options={translatedOptions(locale, 'recordingStatus', ['none', 'recording', 'completed', 'partial', 'failed'])} />
        <div className="space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{t('ws.records.calls.filter.satisfactionResult', locale)}</span><MultiField label={t('ws.records.calls.filter.all', locale)} values={draft.satisfactionResults} onChange={(values) => patch({ satisfactionResults: values })} options={satisfactionResults} /></div>
        <div className="space-y-1.5"><span className="text-xs font-medium text-muted-foreground">{t('ws.records.calls.filter.satisfactionSource', locale)}</span><MultiField label={t('ws.records.calls.filter.all', locale)} values={draft.satisfactionSources} onChange={(values) => patch({ satisfactionSources: values })} options={satisfactionSources} /></div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DurationField locale={locale} label={t('ws.records.calls.filter.totalDuration', locale)} minimum={draft.minTotalDuration} maximum={draft.maxTotalDuration} onMinimum={(value) => patch({ minTotalDuration: value })} onMaximum={(value) => patch({ maxTotalDuration: value })} />
        <DurationField locale={locale} label={t('ws.records.calls.filter.customerRingDuration', locale)} minimum={draft.minRingDuration} maximum={draft.maxRingDuration} onMinimum={(value) => patch({ minRingDuration: value })} onMaximum={(value) => patch({ maxRingDuration: value })} />
        <DurationField locale={locale} label={t('ws.records.calls.filter.agentWaitDuration', locale)} minimum={draft.minWaitDuration} maximum={draft.maxWaitDuration} onMinimum={(value) => patch({ minWaitDuration: value })} onMaximum={(value) => patch({ maxWaitDuration: value })} />
        <DurationField locale={locale} label={t('ws.records.calls.filter.talkDuration', locale)} minimum={draft.minTalkDuration} maximum={draft.maxTalkDuration} onMinimum={(value) => patch({ minTalkDuration: value })} onMaximum={(value) => patch({ maxTalkDuration: value })} />
      </div>
    </div>
  )
}
