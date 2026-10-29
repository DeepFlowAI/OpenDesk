'use client'

import { useMemo, useState } from 'react'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { CallEventEnvelope, CallEventTesterEvent } from '@/models/call-event-tester'

export const CALL_EVENT_TYPES = [
  'call.created',
  'call.customer.connected',
  'call.queue.entered',
  'call.agent.connected',
  'call.agent.disconnected',
  'call.transfer.completed',
  'call.ended',
  'call.recording.completed',
  'call.recording.failed',
  'call.satisfaction.completed',
] as const

export function formatClockTime(value: string | null | undefined, locale: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const time = date.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', { hour12: false })
  return `${time}.${String(date.getMilliseconds()).padStart(3, '0')}`
}

function envelopeOf(event: CallEventTesterEvent): CallEventEnvelope {
  return event.body && typeof event.body === 'object' ? event.body : {}
}

function Tag({ tone = 'muted', children }: { tone?: 'muted' | 'ok' | 'bad' | 'warn'; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center rounded-full px-2 text-xs font-medium',
        tone === 'muted' && 'bg-muted text-muted-foreground',
        tone === 'ok' && 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
        tone === 'bad' && 'bg-destructive/10 text-destructive',
        tone === 'warn' && 'bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
      )}
    >
      {children}
    </span>
  )
}

function EventRow({
  event,
  isZh,
  locale,
  onReissue,
}: {
  event: CallEventTesterEvent
  isZh: boolean
  locale: string
  onReissue: (recordingId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const envelope = envelopeOf(event)
  const recording = envelope.data?.event?.recording
  const expired =
    recording?.download_url_expires_at && new Date(recording.download_url_expires_at) < new Date()

  return (
    <div className="rounded-lg border border-border bg-background">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left"
      >
        {open ? <IconChevronDown className="size-4 text-muted-foreground" /> : <IconChevronRight className="size-4 text-muted-foreground" />}
        <span className="font-mono text-sm font-medium text-foreground">{envelope.type ?? (isZh ? '（非 JSON）' : '(not JSON)')}</span>
        <Tag>seq {envelope.data?.sequence ?? '-'}</Tag>
        <span className="text-xs text-muted-foreground">
          {isZh ? '发生' : 'At'} {formatClockTime(envelope.time, locale)} · {isZh ? '收到' : 'Received'}{' '}
          {formatClockTime(event.received_at, locale)}
        </span>
        {event.secret_checked ? (
          <Tag tone={event.secret_ok ? 'ok' : 'bad'}>
            {event.secret_ok ? 'Secret OK' : isZh ? 'Secret 不匹配' : 'Secret mismatch'}
          </Tag>
        ) : null}
        {event.duplicate ? <Tag tone="warn">{isZh ? '重复投递' : 'Duplicate'}</Tag> : null}
        {envelope.test ? <Tag tone="warn">test</Tag> : null}
      </button>
      {recording ? (
        <div className="mx-3 mb-2 flex flex-wrap items-center gap-2 rounded-md bg-muted/60 px-2 py-1.5 text-xs text-muted-foreground">
          <span>
            {isZh ? '录音' : 'Recording'} <code className="font-mono">{recording.public_id}</code> · {recording.phase} ·{' '}
            {recording.status} · {recording.duration_ms ?? '-'}ms
          </span>
          {recording.download_url ? (
            <>
              <a href={recording.download_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                {isZh ? '下载' : 'Download'}
              </a>
              <span>
                {isZh ? '过期' : 'Expires'} {formatClockTime(recording.download_url_expires_at, locale)}
              </span>
              {expired ? <Tag tone="bad">{isZh ? '已过期' : 'Expired'}</Tag> : null}
            </>
          ) : null}
          {recording.failure_reason ? (
            <span>
              {isZh ? '失败原因' : 'Failure'} {recording.failure_reason}
            </span>
          ) : null}
          {recording.public_id ? (
            <Button size="xs" variant="outline" onClick={() => onReissue(recording.public_id as string)}>
              {isZh ? '重新签发链接' : 'Reissue link'}
            </Button>
          ) : null}
        </div>
      ) : null}
      {open ? (
        <pre className="mx-3 mb-3 max-h-96 overflow-auto rounded-md bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">
          {JSON.stringify(
            { delivery_id: event.delivery_id, user_agent: event.user_agent, body: event.body },
            null,
            2,
          )}
        </pre>
      ) : null}
    </div>
  )
}

export function CallEventTesterEvents({
  events,
  isZh,
  locale,
  onQueryRecordings,
  onReissue,
}: {
  events: CallEventTesterEvent[]
  isZh: boolean
  locale: string
  onQueryRecordings: (callId: string) => void
  onReissue: (recordingId: string) => void
}) {
  const groups = useMemo(() => {
    const bySubject = new Map<string, CallEventTesterEvent[]>()
    for (const event of events) {
      const key = envelopeOf(event).subject || (isZh ? '（无 subject）' : '(no subject)')
      const list = bySubject.get(key) ?? []
      list.push(event)
      bySubject.set(key, list)
    }
    return [...bySubject.entries()]
      .map(([subject, list]) => {
        const sorted = [...list].sort(
          (a, b) =>
            (envelopeOf(a).data?.sequence ?? 0) - (envelopeOf(b).data?.sequence ?? 0) ||
            String(envelopeOf(a).time).localeCompare(String(envelopeOf(b).time)),
        )
        const latestSeq = Math.max(...list.map((event) => event.seq))
        return { subject, sorted, latestSeq }
      })
      .sort((a, b) => b.latestSeq - a.latestSeq)
  }, [events, isZh])

  if (!events.length) {
    return <p className="py-10 text-center text-sm text-muted-foreground">{isZh ? '还没收到事件。' : 'No events yet.'}</p>
  }

  return (
    <div className="space-y-4">
      {groups.map(({ subject, sorted }) => {
        const call = envelopeOf(sorted[sorted.length - 1]).data?.call ?? {}
        const types = new Set(sorted.map((event) => envelopeOf(event).type))
        const callId = subject.startsWith('call/') ? subject.slice(5) : ''
        const agent =
          (call.last_serving_agent as { name?: string } | null)?.name ||
          (call.initiator_agent as { name?: string } | null)?.name
        return (
          <div key={subject} className="rounded-xl border border-border bg-muted/30 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm font-semibold text-foreground">{subject}</span>
              {call.direction ? <Tag>{call.direction}</Tag> : null}
              {call.source ? <Tag>{call.source}</Tag> : null}
              {call.lifecycle_status ? <Tag>{call.lifecycle_status}</Tag> : null}
              <span className="text-xs text-muted-foreground">
                {isZh ? '客户' : 'Customer'} {call.customer_number ?? '-'} · {isZh ? '服务号' : 'Service'}{' '}
                {call.service_number ?? '-'}
                {agent ? ` · ${isZh ? '坐席' : 'Agent'} ${agent}` : ''}
              </span>
              {callId ? (
                <Button size="xs" variant="outline" className="ml-auto" onClick={() => onQueryRecordings(callId)}>
                  {isZh ? '查录音' : 'Recordings'}
                </Button>
              ) : null}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {CALL_EVENT_TYPES.map((type) => (
                <span
                  key={type}
                  className={cn(
                    'rounded-md border px-1.5 py-0.5 font-mono text-[11px]',
                    types.has(type)
                      ? 'border-primary/30 bg-primary/10 text-primary'
                      : 'border-dashed border-border text-muted-foreground/70',
                  )}
                >
                  {type.replace('call.', '')}
                </span>
              ))}
            </div>
            <div className="mt-3 space-y-2">
              {sorted.map((event) => (
                <EventRow key={event.seq} event={event} isZh={isZh} locale={locale} onReissue={onReissue} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
