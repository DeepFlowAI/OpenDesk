'use client'
/**
 * Centered target selector for in-call operations (direct transfer, consult,
 * add participant). Mirrors the online-service transfer dialog: same Dialog,
 * header, search, filter chips, and a footer submit — desktop width ~480px.
 *
 * The three entry points share this one dialog but keep distinct titles and
 * submit labels; the caller passes `mode` and `onSubmit`. Employee selection
 * resolves to a live agent `target_id`; queue selection resolves to a queue
 * `target_id`; external resolves to a `number`.
 */
import { useEffect, useMemo, useState } from 'react'
import { IconLoader2, IconUser, IconUsersGroup } from '@tabler/icons-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { useConsultableAgents, useTransferQueues } from '@/service/use-call-center'
import type { AgentStatus, ConsultableAgent, TransferQueue } from '@/models/call-center'
import type { TransferTargetType } from '@/service/use-call-center'

export type CallTargetPickerMode = 'transfer' | 'consult' | 'conference'

export type PickedTarget = {
  target_type: TransferTargetType
  target_id?: number | null
  number?: string | null
  target_name: string
  /** Display-only status line for the confirm dialog (e.g. queue availability). */
  target_status?: string
  /** Available-agent count when target is a queue; used for empty-queue warning. */
  queue_available_count?: number
}

type Props = {
  open: boolean
  mode: CallTargetPickerMode
  /** conference/consult can't transfer to a queue. */
  allowQueue?: boolean
  submitting?: boolean
  onClose: () => void
  onSubmit: (target: PickedTarget) => void
}

const TITLE_KEY: Record<CallTargetPickerMode, string> = {
  transfer: 'ws.callbar.pickerTransferTitle',
  consult: 'ws.callbar.pickerConsultTitle',
  conference: 'ws.callbar.pickerConferenceTitle',
}
const DESC_KEY: Record<CallTargetPickerMode, string> = {
  transfer: 'ws.callbar.pickerTransferDesc',
  consult: 'ws.callbar.pickerConsultDesc',
  conference: 'ws.callbar.pickerConferenceDesc',
}
const SUBMIT_KEY: Record<CallTargetPickerMode, string> = {
  transfer: 'ws.callbar.submitTransfer',
  consult: 'ws.callbar.submitConsult',
  conference: 'ws.callbar.submitConference',
}

// Semantic status colors, matching the call-monitor convention (no hard-coded
// hex): ready=success (green), busy=destructive (red), break / after_call_work
// =warning (amber), offline=muted (gray). Dot + text carry the same meaning.
const STATUS_STYLE: Record<AgentStatus, { dot: string; text: string }> = {
  ready: { dot: 'bg-success', text: 'text-success' },
  busy: { dot: 'bg-destructive', text: 'text-destructive' },
  break: { dot: 'bg-warning', text: 'text-warning' },
  after_call_work: { dot: 'bg-warning', text: 'text-warning' },
  offline: { dot: 'bg-muted-foreground', text: 'text-muted-foreground' },
}
const STATUS_LABEL_KEY: Record<AgentStatus, string> = {
  ready: 'ws.callbar.agentStatusReady',
  busy: 'ws.callbar.agentStatusBusy',
  break: 'ws.callbar.agentStatusBreak',
  after_call_work: 'ws.callbar.agentStatusAfterCallWork',
  offline: 'ws.callbar.agentStatusOffline',
}

/** Only ready agents can be consulted / transferred / conferenced to. */
function isAgentAvailable(status: AgentStatus): boolean {
  return status === 'ready'
}

export function CallTargetPickerDialog({
  open,
  mode,
  allowQueue = false,
  submitting = false,
  onClose,
  onSubmit,
}: Props) {
  // Latch on click so a second press cannot fire before the parent
  // re-renders with submitting=true (relevant when the dialog stays open).
  const [submitLatched, setSubmitLatched] = useState(false)
  useEffect(() => {
    if (!open) setSubmitLatched(false)
  }, [open])
  const { locale } = useLocaleStore()
  const [filter, setFilter] = useState<TransferTargetType>('external')
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [externalNumber, setExternalNumber] = useState('')
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [selectedQueueId, setSelectedQueueId] = useState<number | null>(null)

  // Reset transient state each time the dialog opens.
  useEffect(() => {
    if (open) {
      setFilter('external')
      setKeyword('')
      setDebouncedKeyword('')
      setExternalNumber('')
      setSelectedAgentId(null)
      setSelectedQueueId(null)
    }
  }, [open])

  // Debounce the keyword so server-side name filtering doesn't fire per key.
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedKeyword(keyword.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [keyword])

  const agentsQuery = useConsultableAgents(
    debouncedKeyword,
    open && filter === 'employee',
  )
  const agents = agentsQuery.data ?? []
  const selectedAgent = useMemo(
    () => agents.find((a) => a.employee_id === selectedAgentId) ?? null,
    [agents, selectedAgentId],
  )

  const queuesQuery = useTransferQueues(
    debouncedKeyword,
    open && filter === 'queue',
  )
  const queues = queuesQuery.data ?? []
  const selectedQueue = useMemo(
    () => queues.find((q) => q.queue_id === selectedQueueId) ?? null,
    [queues, selectedQueueId],
  )

  const filters: { value: TransferTargetType; labelKey: string }[] = [
    { value: 'employee', labelKey: 'ws.callbar.filterEmployee' },
    ...(allowQueue
      ? [{ value: 'queue' as TransferTargetType, labelKey: 'ws.callbar.filterQueue' }]
      : []),
    { value: 'external', labelKey: 'ws.callbar.filterExternal' },
  ]

  const busy = submitting || submitLatched
  const canSubmit =
    !busy &&
    (filter === 'external'
      ? externalNumber.trim().length > 0
      : filter === 'employee'
        ? selectedAgent !== null && isAgentAvailable(selectedAgent.status)
        : selectedQueue !== null)

  const handleSubmit = () => {
    if (!canSubmit) return
    if (filter === 'external') {
      const number = externalNumber.trim()
      setSubmitLatched(true)
      onSubmit({ target_type: 'external', number, target_name: number })
      return
    }
    if (filter === 'employee') {
      if (!selectedAgent || !isAgentAvailable(selectedAgent.status)) return
      setSubmitLatched(true)
      onSubmit({
        target_type: 'employee',
        target_id: selectedAgent.employee_id,
        target_name: selectedAgent.name ?? String(selectedAgent.employee_id),
      })
      return
    }
    if (!selectedQueue) return
    setSubmitLatched(true)
    onSubmit({
      target_type: 'queue',
      target_id: selectedQueue.queue_id,
      target_name: selectedQueue.name,
      target_status: t('ws.callbar.queueAvailableCount', locale, {
        count: selectedQueue.available_agent_count,
      }),
      queue_available_count: selectedQueue.available_agent_count,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next && !busy) onClose() }}>
      <DialogContent className="grid-cols-[minmax(0,1fr)] gap-3 pb-3 sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t(TITLE_KEY[mode], locale)}</DialogTitle>
          <DialogDescription>{t(DESC_KEY[mode], locale)}</DialogDescription>
        </DialogHeader>

        <div className="flex gap-1.5" role="tablist" aria-label={t('ws.callbar.filterAll', locale)}>
          {filters.map((f) => (
            <button
              key={f.value}
              type="button"
              role="tab"
              aria-selected={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                filter === f.value
                  ? 'border-primary/30 bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:bg-muted/50',
              )}
            >
              {t(f.labelKey, locale)}
            </button>
          ))}
        </div>

        {filter === 'external' ? (
          <input
            type="tel"
            inputMode="tel"
            value={externalNumber}
            onChange={(e) => setExternalNumber(e.target.value)}
            placeholder={t('ws.callbar.externalNumberPlaceholder', locale)}
            aria-label={t('ws.callbar.externalNumberPlaceholder', locale)}
            className="h-10 w-full rounded-md border border-border px-3 text-sm outline-none focus:border-primary"
          />
        ) : filter === 'employee' ? (
          <AgentPicker
            locale={locale}
            keyword={keyword}
            onKeywordChange={setKeyword}
            agents={agents}
            isLoading={agentsQuery.isLoading}
            hasKeyword={debouncedKeyword.length > 0}
            selectedAgentId={selectedAgentId}
            onSelect={setSelectedAgentId}
          />
        ) : (
          <QueueList
            locale={locale}
            keyword={keyword}
            onKeywordChange={setKeyword}
            queues={queues}
            isLoading={queuesQuery.isLoading}
            hasKeyword={debouncedKeyword.length > 0}
            selectedQueueId={selectedQueueId}
            onSelect={setSelectedQueueId}
          />
        )}

        <DialogFooter className="pt-3 pb-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {t('ws.callbar.cancel', locale)}
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {busy && <IconLoader2 size={14} className="mr-1 animate-spin" />}
            {t(SUBMIT_KEY[mode], locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

type AgentPickerProps = {
  locale: Locale
  keyword: string
  onKeywordChange: (value: string) => void
  agents: ConsultableAgent[]
  isLoading: boolean
  hasKeyword: boolean
  selectedAgentId: number | null
  onSelect: (id: number) => void
}

function AgentPicker({
  locale,
  keyword,
  onKeywordChange,
  agents,
  isLoading,
  hasKeyword,
  selectedAgentId,
  onSelect,
}: AgentPickerProps) {
  return (
    <div className="flex flex-col gap-2">
      <input
        type="text"
        value={keyword}
        onChange={(e) => onKeywordChange(e.target.value)}
        placeholder={t('ws.callbar.agentSearchPlaceholder', locale)}
        aria-label={t('ws.callbar.agentSearchPlaceholder', locale)}
        className="h-10 w-full rounded-md border border-border px-3 text-sm outline-none focus:border-primary"
      />
      <div
        role="listbox"
        aria-label={t('ws.callbar.filterEmployee', locale)}
        className="max-h-64 min-h-32 overflow-y-auto rounded-md border border-border"
      >
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <IconLoader2 size={14} className="animate-spin" />
            {t('ws.callbar.agentListLoading', locale)}
          </div>
        ) : agents.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            {t(hasKeyword ? 'ws.callbar.agentListNoMatch' : 'ws.callbar.agentListEmpty', locale)}
          </div>
        ) : (
          agents.map((agent) => (
            <AgentRow
              key={agent.employee_id}
              locale={locale}
              agent={agent}
              selected={agent.employee_id === selectedAgentId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </div>
  )
}

function AgentRow({
  locale,
  agent,
  selected,
  onSelect,
}: {
  locale: Locale
  agent: ConsultableAgent
  selected: boolean
  onSelect: (id: number) => void
}) {
  const available = isAgentAvailable(agent.status)
  const style = STATUS_STYLE[agent.status] ?? STATUS_STYLE.offline
  const displayName = agent.name ?? String(agent.employee_id)
  const unavailableHint =
    agent.status === 'offline'
      ? t('ws.callbar.agentOfflineHint', locale)
      : t('ws.callbar.agentUnavailableHint', locale)

  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      aria-disabled={!available}
      disabled={!available}
      title={available ? undefined : unavailableHint}
      onClick={() => { if (available) onSelect(agent.employee_id) }}
      className={cn(
        'flex w-full items-center gap-3 border-b border-border/60 px-3 py-2 text-left transition-colors last:border-b-0',
        !available
          ? 'cursor-not-allowed opacity-50'
          : selected
            ? 'bg-primary/10'
            : 'hover:bg-muted/50',
      )}
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-full bg-muted">
        {agent.avatar ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={agent.avatar} alt="" className="h-full w-full object-cover" />
        ) : (
          <IconUser size={16} className="text-muted-foreground" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-foreground">{displayName}</span>
        {agent.group_names && agent.group_names.length > 0 && (
          <span className="block truncate text-xs text-muted-foreground">
            {agent.group_names.join(' · ')}
          </span>
        )}
      </span>
      <span className={cn('flex shrink-0 items-center gap-1.5 text-xs', style.text)}>
        <span className={cn('inline-block h-2 w-2 rounded-full', style.dot)} />
        {t(STATUS_LABEL_KEY[agent.status] ?? STATUS_LABEL_KEY.offline, locale)}
      </span>
    </button>
  )
}

type QueueListProps = {
  locale: Locale
  keyword: string
  onKeywordChange: (value: string) => void
  queues: TransferQueue[]
  isLoading: boolean
  hasKeyword: boolean
  selectedQueueId: number | null
  onSelect: (id: number) => void
}

function QueueList({
  locale,
  keyword,
  onKeywordChange,
  queues,
  isLoading,
  hasKeyword,
  selectedQueueId,
  onSelect,
}: QueueListProps) {
  return (
    <div className="flex flex-col gap-2">
      <input
        type="text"
        value={keyword}
        onChange={(e) => onKeywordChange(e.target.value)}
        placeholder={t('ws.callbar.queueSearchPlaceholder', locale)}
        aria-label={t('ws.callbar.queueSearchPlaceholder', locale)}
        className="h-10 w-full rounded-md border border-border px-3 text-sm outline-none focus:border-primary"
      />
      <div
        role="listbox"
        aria-label={t('ws.callbar.filterQueue', locale)}
        className="max-h-64 min-h-32 overflow-y-auto rounded-md border border-border"
      >
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <IconLoader2 size={14} className="animate-spin" />
            {t('ws.callbar.queueListLoading', locale)}
          </div>
        ) : queues.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            {t(hasKeyword ? 'ws.callbar.queueListNoMatch' : 'ws.callbar.queueListEmpty', locale)}
          </div>
        ) : (
          queues.map((queue) => (
            <QueueRow
              key={queue.queue_id}
              locale={locale}
              queue={queue}
              selected={queue.queue_id === selectedQueueId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </div>
  )
}

function QueueRow({
  locale,
  queue,
  selected,
  onSelect,
}: {
  locale: Locale
  queue: TransferQueue
  selected: boolean
  onSelect: (id: number) => void
}) {
  const availableCount = queue.available_agent_count
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      onClick={() => onSelect(queue.queue_id)}
      className={cn(
        'flex w-full items-center gap-3 border-b border-border/60 px-3 py-2 text-left transition-colors last:border-b-0',
        selected ? 'bg-primary/10' : 'hover:bg-muted/50',
      )}
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-full bg-muted">
        <IconUsersGroup size={16} className="text-muted-foreground" />
      </span>
      <span className="min-w-0 flex-1 truncate text-sm text-foreground">{queue.name}</span>
      <span
        className={cn(
          'shrink-0 text-xs',
          availableCount > 0 ? 'text-success' : 'text-muted-foreground',
        )}
      >
        {t('ws.callbar.queueAvailableCount', locale, { count: availableCount })}
      </span>
    </button>
  )
}
