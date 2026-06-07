'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { IconDownload, IconLoader2, IconMicrophoneOff, IconX } from '@tabler/icons-react'

import { useLocaleStore } from '@/context/locale-store'
import { useCallRecord } from '@/service/use-call-center'
import type { CallRecordDetail, CallRecordListItem } from '@/models/call-center'
import { t } from '@/utils/i18n'
import { CallSummaryFields } from '@/app/components/features/call-summary/call-summary-fields'
import {
  callRecordCustomerNumber,
  callRecordServiceNumber,
  formatCallRecordDate,
  formatCallRecordDuration,
  formatQueueDurationSeconds,
} from '@/app/components/features/call-center/call-record-utils'

export {
  callRecordCustomerNumber,
  callRecordServiceNumber,
  formatCallRecordDate,
  formatCallRecordDuration,
  formatQueueDurationSeconds,
}

type CallRecordDetailDrawerProps = {
  recordId: number
  onClose: () => void
}

export function CallRecordDetailDrawer({ recordId, onClose }: CallRecordDetailDrawerProps) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const { data, isLoading } = useCallRecord(recordId)
  const [summaryDirty, setSummaryDirty] = useState(false)
  const [recordingDownloading, setRecordingDownloading] = useState(false)
  const [recordingDownloadError, setRecordingDownloadError] = useState(false)

  const requestClose = useCallback(() => {
    if (summaryDirty) {
      const confirmed = window.confirm(t('ws.call.unsavedBody', locale))
      if (!confirmed) return
    }
    onClose()
  }, [locale, onClose, summaryDirty])

  useEffect(() => {
    setSummaryDirty(false)
    setRecordingDownloading(false)
    setRecordingDownloadError(false)
  }, [recordId])

  const handleDownloadRecording = useCallback(async () => {
    if (!data?.recording_url || recordingDownloading) return

    setRecordingDownloadError(false)
    setRecordingDownloading(true)
    try {
      const response = await fetch(data.recording_url, { credentials: 'omit' })
      if (!response.ok) throw new Error('Failed to fetch recording')
      const blob = await response.blob()
      triggerRecordingDownload(blob, recordingFileName(data))
    } catch {
      setRecordingDownloadError(true)
    } finally {
      setRecordingDownloading(false)
    }
  }, [data, recordingDownloading])

  useEffect(() => {
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') requestClose()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [requestClose])

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={requestClose} />
      <div className="relative z-10 flex h-full w-full max-w-[1120px] flex-col bg-white shadow-2xl sm:w-[80%]">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold">
            {isZh ? '通话详情' : 'Call Details'}
          </h2>
          <button
            type="button"
            onClick={requestClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <IconX size={18} />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          {isLoading || !data ? (
            <div className="flex min-h-[180px] items-center justify-center">
              <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              <section className="rounded-xl border border-border p-4">
                <h3 className="mb-3 text-sm font-semibold">
                  {isZh ? '通话录音' : 'Recording'}
                </h3>
                {data.recording_url ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-3">
                      <audio src={data.recording_url} controls className="flex-1" />
                      <button
                        type="button"
                        onClick={handleDownloadRecording}
                        disabled={recordingDownloading}
                        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                        aria-label={isZh ? '下载录音' : 'Download recording'}
                        title={isZh ? '下载录音' : 'Download recording'}
                      >
                        {recordingDownloading ? (
                          <IconLoader2 size={16} className="animate-spin" />
                        ) : (
                          <IconDownload size={16} />
                        )}
                      </button>
                    </div>
                    {recordingDownloadError && (
                      <p className="text-xs text-destructive">
                        {isZh ? '录音下载失败，请重试' : 'Failed to download recording. Please try again.'}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center gap-2 py-6 text-muted-foreground">
                    <IconMicrophoneOff size={24} />
                    <p className="text-sm">
                      {isZh ? '暂无通话录音' : 'No recording yet'}
                    </p>
                  </div>
                )}
              </section>

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]">
                <section className="rounded-xl border border-border p-4">
                  <h3 className="mb-3 text-sm font-semibold">
                    {isZh ? '通话信息' : 'Call Info'}
                  </h3>
                  <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-sm">
                    <Dt>{isZh ? '通话 ID' : 'Call ID'}</Dt>
                    <Dd mono>{data.call_id}</Dd>
                    <Dt>{isZh ? '通话类型' : 'Direction'}</Dt>
                    <Dd>
                      {data.direction === 'inbound'
                        ? (isZh ? '呼入' : 'Inbound')
                        : (isZh ? '呼出' : 'Outbound')}
                    </Dd>
                    <Dt>{isZh ? '用户号码' : 'User Number'}</Dt>
                    <Dd>{callRecordCustomerNumber(data) || (isZh ? '未知号码' : 'Unknown')}</Dd>
                    <Dt>{isZh ? '服务号码' : 'Service Number'}</Dt>
                    <Dd>{callRecordServiceNumber(data) || '-'}</Dd>
                    <Dt>{t('ws.records.calls.detail.lastAssignedQueue', locale)}</Dt>
                    <Dd>
                      <CallQueueName queue={data.last_assigned_queue} locale={locale} />
                    </Dd>
                    <Dt>{t('ws.records.calls.detail.queueDuration', locale)}</Dt>
                    <Dd>{formatQueueDurationSeconds(data.queue_duration_seconds)}</Dd>
                    <Dt>{isZh ? '关联用户' : 'Linked User'}</Dt>
                    <Dd>
                      <AssociatedUserDetail record={data} isZh={isZh} />
                    </Dd>
                    <Dt>{isZh ? '相关工单' : 'Related Tickets'}</Dt>
                    <Dd>
                      <RelatedTicketsDetail record={data} />
                    </Dd>
                    <Dt>{isZh ? '接待客服' : 'Agent'}</Dt>
                    <Dd>{data.agent_name || '-'}</Dd>
                    <Dt>{isZh ? '开始时间' : 'Started At'}</Dt>
                    <Dd>{formatCallRecordDate(data.started_at, isZh)}</Dd>
                    <Dt>{isZh ? '结束时间' : 'Ended At'}</Dt>
                    <Dd>{formatCallRecordDate(data.ended_at, isZh)}</Dd>
                    <Dt>{isZh ? '通话时长' : 'Talk Time'}</Dt>
                    <Dd>{formatCallRecordDuration(data.talk_duration_ms)}</Dd>
                    <Dt>{isZh ? '响铃时长' : 'Ring Time'}</Dt>
                    <Dd>{formatCallRecordDuration(data.ring_duration_ms)}</Dd>
                    <Dt>{isZh ? '挂断原因' : 'Hangup Reason'}</Dt>
                    <Dd>{data.hangup_reason || '-'}</Dd>
                  </dl>
                </section>

                <section className="rounded-xl border border-border p-4">
                  <div className="mb-3 border-b border-border pb-2">
                    <h3 className="text-sm font-semibold">
                      {isZh ? '通话纪要' : 'Call Summary'}
                    </h3>
                  </div>
                  <CallSummaryFields callRecordId={data.id} onDirtyChange={setSummaryDirty} />
                </section>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function associatedUserLabel(
  record: Pick<CallRecordListItem, 'user_name' | 'user_public_id'>,
): string | null {
  return record.user_name || record.user_public_id
}

function associatedUserHref(record: Pick<CallRecordListItem, 'user_id' | 'user_public_id'>): string | null {
  const ref = record.user_public_id || record.user_id
  return ref ? `/workspace/users/${ref}` : null
}

function associationStatusLabel(status: CallRecordListItem['user_association_status'], isZh: boolean): string {
  if (!isZh) {
    switch (status) {
      case 'linked':
        return 'Linked'
      case 'created':
        return 'Created'
      case 'multiple':
        return 'Needs selection'
      case 'unknown':
        return 'Unknown number'
      case 'failed':
        return 'Failed'
      default:
        return 'Unmatched'
    }
  }

  switch (status) {
    case 'linked':
      return '已关联'
    case 'created':
      return '已新建'
    case 'multiple':
      return '待选择'
    case 'unknown':
      return '未知号码'
    case 'failed':
      return '识别失败'
    default:
      return '待匹配'
  }
}

function AssociatedUserDetail({
  record,
  isZh,
}: {
  record: CallRecordDetail
  isZh: boolean
}) {
  const label = associatedUserLabel(record)
  const href = associatedUserHref(record)

  if (!label || !href) {
    return (
      <span className="inline-flex rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
        {associationStatusLabel(record.user_association_status, isZh)}
      </span>
    )
  }

  return (
    <Link
      href={href}
      className="inline-flex max-w-full flex-col rounded-sm text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="truncate text-sm font-medium">{label}</span>
    </Link>
  )
}

function CallQueueName({
  queue,
  locale,
}: {
  queue: CallRecordDetail['last_assigned_queue']
  locale: 'zh' | 'en'
}) {
  if (!queue?.name) return <span />
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <span className="min-w-0 break-words">{queue.name}</span>
      {queue.queue_type === 'employee' && (
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] leading-4 text-muted-foreground">
          {t('ws.records.queue.personalQueue', locale)}
        </span>
      )}
    </span>
  )
}

function RelatedTicketsDetail({ record }: { record: CallRecordDetail }) {
  const tickets = record.related_tickets ?? []

  if (!tickets.length) {
    return <span>-</span>
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

function triggerRecordingDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.URL.revokeObjectURL(url)
}

function recordingFileName(record: CallRecordDetail): string {
  const safeCallId = record.call_id.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[.-]+|[.-]+$/g, '')
  let suffix = '.wav'
  try {
    const pathname = new URL(record.recording_url || '', window.location.href).pathname
    const matched = pathname.match(/\.(wav|mp3|m4a|aac|ogg|webm|flac)$/i)
    if (matched) suffix = `.${matched[1].toLowerCase()}`
  } catch {
    // Keep the default extension for malformed legacy URLs.
  }
  return `call-recording-${safeCallId || record.id}${suffix}`
}

function Dt({ children }: { children: React.ReactNode }) {
  return <dt className="text-foreground/70">{children}</dt>
}

function Dd({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <dd className={mono ? 'min-w-0 break-all font-mono text-xs text-foreground' : 'min-w-0 break-words text-foreground'}>
      {children}
    </dd>
  )
}
