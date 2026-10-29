'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { IconDownload, IconLoader2, IconMicrophoneOff, IconX } from '@tabler/icons-react'

import { useLocaleStore } from '@/context/locale-store'
import type { Locale } from '@/lib/languages'
import { formatHangupReason } from '@/lib/call-record-labels'
import { useCallRecord } from '@/service/use-call-center'
import type { CallRecordDetail, CallRecordListItem, CallRecordingItem } from '@/models/call-center'
import { t } from '@/utils/i18n'
import { CallSummaryFields } from '@/app/components/features/call-summary/call-summary-fields'
import { CallTrajectoryPanel } from '@/app/components/features/call-center/call-trajectory-panel'
import {
  callRecordCustomerNumber,
  callRecordServiceNumber,
  formatCallRecordDate,
  formatCallRecordDuration,
  recordingPhaseLabel,
  selectDisplayRecording,
} from '@/app/components/features/call-center/call-record-utils'

export {
  callRecordCustomerNumber,
  callRecordServiceNumber,
  formatCallRecordDate,
  formatCallRecordDuration,
}

type CallRecordDetailDrawerProps = {
  recordId: string
  onClose: () => void
}

export function CallRecordDetailDrawer({ recordId, onClose }: CallRecordDetailDrawerProps) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const { data, isLoading } = useCallRecord(recordId)
  const displayRecording = selectDisplayRecording(data?.recordings)
  const displayRecordingPhase = displayRecording
    ? recordingPhaseLabel(displayRecording.phase, isZh)
    : null
  const [summaryDirty, setSummaryDirty] = useState(false)
  const [activeTab, setActiveTab] = useState<'overview' | 'trajectory'>('overview')
  const [recordingDownloading, setRecordingDownloading] = useState<string | null>(null)
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
    setActiveTab('overview')
    setRecordingDownloading(null)
    setRecordingDownloadError(false)
  }, [recordId])

  const handleDownloadRecording = useCallback(async (recording: CallRecordingItem) => {
    if (!data || !recording.access_url || recordingDownloading) return

    setRecordingDownloadError(false)
    setRecordingDownloading(recording.recording_id)
    try {
      const response = await fetch(recording.access_url, { credentials: 'omit' })
      if (!response.ok) throw new Error('Failed to fetch recording')
      const blob = await response.blob()
      triggerRecordingDownload(blob, recordingFileName(data, recording))
    } catch {
      setRecordingDownloadError(true)
    } finally {
      setRecordingDownloading(null)
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
      <div className="relative z-10 flex h-full w-full max-w-[1120px] flex-col bg-background shadow-2xl sm:w-[80%]">
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

        <div className="flex h-12 shrink-0 items-end gap-7 border-b border-border px-6 text-sm" role="tablist">
          {(['overview', 'trajectory'] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className={`flex h-full items-center border-b-2 px-0.5 ${activeTab === tab ? 'border-foreground font-semibold text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
            >
              {tab === 'overview'
                ? t('ws.records.calls.trajectory.overview', locale)
                : t('ws.records.calls.trajectory.tab', locale)}
            </button>
          ))}
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          {isLoading || !data ? (
            <div className="flex min-h-[180px] items-center justify-center">
              <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              <div className={activeTab === 'overview' ? 'space-y-4' : 'hidden'}>
              <section className="rounded-xl border border-border p-4">
                <h3 className="mb-3 text-sm font-semibold">
                  {isZh ? '通话录音' : 'Recording'}
                </h3>
                {displayRecording ? (
                  <div className="space-y-3">
                    <div className="space-y-2 rounded-lg border border-border p-3">
                        {displayRecordingPhase ? (
                          <p className="text-xs font-medium text-foreground">
                            {displayRecordingPhase}
                          </p>
                        ) : null}
                        {displayRecording.access_url ? (
                          <div className="flex items-center gap-3">
                            <audio src={displayRecording.access_url} controls className="min-w-0 flex-1" />
                            <button
                              type="button"
                              onClick={() => handleDownloadRecording(displayRecording)}
                              disabled={recordingDownloading !== null}
                              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                              aria-label={isZh ? '下载录音' : 'Download recording'}
                              title={isZh ? '下载录音' : 'Download recording'}
                            >
                              {recordingDownloading === displayRecording.recording_id ? (
                                <IconLoader2 size={16} className="animate-spin" />
                              ) : (
                                <IconDownload size={16} />
                              )}
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <IconMicrophoneOff size={16} />
                            {recordingArtifactStatus(displayRecording.status, isZh)}
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {recordingArtifactStatus(displayRecording.status, isZh)}
                          {displayRecording.duration_ms != null ? ` · ${formatCallRecordDuration(displayRecording.duration_ms)}` : ''}
                        </p>
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

              {data.custom_business_info ? (
                <section className="rounded-xl border border-border p-4">
                  <h3 className="mb-3 text-sm font-semibold">
                    {isZh ? '自定义业务信息' : 'Custom Business Information'}
                  </h3>
                  <p className="whitespace-pre-wrap break-words text-sm text-foreground">
                    {data.custom_business_info}
                  </p>
                </section>
              ) : null}

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)]">
                <section className="rounded-xl border border-border p-4">
                  <h3 className="mb-3 text-sm font-semibold">
                    {isZh ? '通话信息' : 'Call Info'}
                  </h3>
                  <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-sm">
                    <Dt>{t('ws.records.calls.col.callId', locale)}</Dt>
                    <Dd mono>{data.call_id}</Dd>
                    <Dt>{t('ws.records.calls.col.direction', locale)}</Dt>
                    <Dd>{optionLabel('direction', data.direction, locale)}</Dd>
                    <Dt>{t('ws.records.calls.col.callSource', locale)}</Dt>
                    <Dd>{optionLabel('callSource', data.call_source, locale)}</Dd>
                    <Dt>{t('ws.records.calls.col.customerNumber', locale)}</Dt>
                    <Dd>
                      {callRecordCustomerNumber(data)
                        || t('ws.records.calls.unknownNumber', locale)}
                    </Dd>
                    <Dt>{t('ws.records.calls.col.serviceNumber', locale)}</Dt>
                    <Dd>{callRecordServiceNumber(data) || '-'}</Dd>
                    <Dt>{t('ws.records.calls.col.user', locale)}</Dt>
                    <Dd>
                      <AssociatedUserDetail record={data} isZh={isZh} />
                    </Dd>
                    <Dt>{t('ws.records.calls.col.userAssociationStatus', locale)}</Dt>
                    <Dd>{optionLabel('association', data.user_association_status, locale)}</Dd>
                    <Dt>{isZh ? '相关工单' : 'Related Tickets'}</Dt>
                    <Dd>
                      <RelatedTicketsDetail record={data} />
                    </Dd>
                    <Dt>{t('ws.records.calls.col.initiatorAgent', locale)}</Dt>
                    <Dd>{data.initiator_agent_name || '-'}</Dd>
                    <Dt>{t('ws.records.calls.col.lastQueue', locale)}</Dt>
                    <Dd>
                      <CallQueueName queue={data.last_queue} locale={locale} />
                    </Dd>
                    <Dt>{t('ws.records.calls.col.lastServingAgent', locale)}</Dt>
                    <Dd>{data.last_serving_agent_name || '-'}</Dd>
                    <Dt>{t('ws.records.calls.col.lifecycleStatus', locale)}</Dt>
                    <Dd>{optionLabel('lifecycleStatus', data.lifecycle_status, locale)}</Dd>
                    <Dt>{t('ws.records.calls.col.finalizationStatus', locale)}</Dt>
                    <Dd>{optionLabel('finalizationStatus', data.finalization_status, locale)}</Dd>
                    <Dt>{t('ws.records.calls.col.receptionType', locale)}</Dt>
                    <Dd>{optionLabel('receptionType', data.actual_reception_type, locale)}</Dd>
                    <Dt>{t('ws.records.calls.col.callResult', locale)}</Dt>
                    <Dd>
                      {optionLabel(
                        'callResult',
                        data.call_result || data.lifecycle_status,
                        locale,
                      )}
                    </Dd>
                    <Dt>{t('ws.records.calls.col.hangupParty', locale)}</Dt>
                    <Dd>{optionLabel('hangupParty', data.hangup_party, locale)}</Dd>
                    <Dt>{t('ws.records.calls.col.hangupReason', locale)}</Dt>
                    <Dd>
                      {optionLabel('hangupReason', data.hangup_reason_code, locale)
                        || formatHangupReason(data.hangup_reason_code, isZh)
                        || '-'}
                    </Dd>
                    <Dt>{t('ws.records.calls.col.startedAt', locale)}</Dt>
                    <Dd>{formatCallRecordDate(data.started_at, isZh)}</Dd>
                    <Dt>{t('ws.records.calls.col.customerConnectedAt', locale)}</Dt>
                    <Dd>{formatCallRecordDate(data.customer_connected_at, isZh)}</Dd>
                    <Dt>{t('ws.records.calls.col.firstAgentConnectedAt', locale)}</Dt>
                    <Dd>{formatCallRecordDate(data.first_agent_connected_at, isZh)}</Dd>
                    <Dt>{t('ws.records.calls.col.humanServiceEndedAt', locale)}</Dt>
                    <Dd>{formatCallRecordDate(data.human_service_ended_at, isZh)}</Dd>
                    <Dt>{t('ws.records.calls.col.endedAt', locale)}</Dt>
                    <Dd>{formatCallRecordDate(data.ended_at, isZh)}</Dd>
                    <Dt>{t('ws.records.calls.col.totalDuration', locale)}</Dt>
                    <Dd>{formatCallRecordDuration(data.total_duration_ms)}</Dd>
                    <Dt>{t('ws.records.calls.col.customerRingDuration', locale)}</Dt>
                    <Dd>{formatCallRecordDuration(data.customer_ring_duration_ms)}</Dd>
                    <Dt>{t('ws.records.calls.col.agentWaitDuration', locale)}</Dt>
                    <Dd>{formatCallRecordDuration(data.agent_wait_duration_ms)}</Dd>
                    <Dt>{t('ws.records.calls.col.talkDuration', locale)}</Dt>
                    <Dd>{formatCallRecordDuration(data.customer_agent_talk_duration_ms)}</Dd>
                    <Dt>{t('ws.records.calls.col.recordingStatus', locale)}</Dt>
                    <Dd>
                      {optionLabel('recordingStatus', data.recording_status, locale)}
                    </Dd>
                    <Dt>{t('ws.records.calls.col.satisfactionResult', locale)}</Dt>
                    <Dd>
                      <SatisfactionResultSummary record={data} locale={locale} />
                    </Dd>
                    <Dt>{t('ws.records.calls.col.satisfactionSource', locale)}</Dt>
                    <Dd>
                      {optionLabel(
                        'satisfactionSource',
                        data.satisfaction_trigger_source,
                        locale,
                      )}
                    </Dd>
                    <Dt>{t('ws.records.calls.col.satisfactionPrimaryOption', locale)}</Dt>
                    <Dd>{data.satisfaction_primary_option_label || '-'}</Dd>
                    <Dt>{t('ws.records.calls.col.satisfactionAnswerCount', locale)}</Dt>
                    <Dd>
                      {data.satisfaction_answer_count == null
                        ? '-'
                        : String(data.satisfaction_answer_count)}
                    </Dd>
                    <Dt>{t('ws.records.calls.col.satisfactionDuration', locale)}</Dt>
                    <Dd>{formatCallRecordDuration(data.satisfaction_duration_ms)}</Dd>
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
              <SatisfactionResultSection record={data} isZh={isZh} />
              </div>
              <div className={activeTab === 'trajectory' ? 'block' : 'hidden'}>
                <CallTrajectoryPanel recordId={data.public_id} enabled={activeTab === 'trajectory'} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function SatisfactionResultSection({ record, isZh }: { record: CallRecordDetail; isZh: boolean }) {
  const satisfaction = record.satisfaction
  return (
    <section className="rounded-xl border border-border p-4">
      <h3 className="mb-3 text-sm font-semibold">
        {isZh ? '满意度结果' : 'Satisfaction Result'}
      </h3>
      {record.satisfaction_result == null ? (
        <p className="text-sm text-muted-foreground">—</p>
      ) : !satisfaction ? (
        <p className="text-sm text-muted-foreground">
          {isZh ? '本次通话未触发满意度调查' : 'No satisfaction survey was triggered for this call.'}
        </p>
      ) : (
        <div className="space-y-4">
          <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-sm sm:grid-cols-[120px_1fr_120px_1fr]">
            <Dt>{isZh ? '状态' : 'Status'}</Dt>
            <Dd>{satisfactionStatusLabel(satisfaction.status, isZh)}</Dd>
            <Dt>{isZh ? '触发来源' : 'Trigger'}</Dt>
            <Dd>{satisfaction.trigger_source === 'auto_transfer' ? (isZh ? '自动转入' : 'Automatic') : (isZh ? '客服主动邀请' : 'Agent invite')}</Dd>
            <Dt>{isZh ? '调查流程' : 'Flow'}</Dt>
            <Dd>{satisfaction.flow_name} · V{satisfaction.flow_version_no}</Dd>
            <Dt>{isZh ? '满意度耗时' : 'Duration'}</Dt>
            <Dd>{formatCallRecordDuration(satisfaction.duration_ms)}</Dd>
            <Dt>{isZh ? '开始时间' : 'Started At'}</Dt>
            <Dd>{formatCallRecordDate(satisfaction.started_at, isZh)}</Dd>
            <Dt>{isZh ? '结束时间' : 'Ended At'}</Dt>
            <Dd>{formatCallRecordDate(satisfaction.ended_at, isZh)}</Dd>
            <Dt>{isZh ? '归属客服' : 'Assigned Agent'}</Dt>
            <Dd>{satisfaction.agent_name || '-'}</Dd>
            <Dt>{isZh ? '归属队列' : 'Assigned Queue'}</Dt>
            <Dd>{satisfaction.queue_name || '-'}</Dd>
            {satisfaction.termination_reason && satisfaction.status !== 'completed' && (
              <>
                <Dt>{isZh ? '未完成说明' : 'Incomplete Reason'}</Dt>
                <Dd>{satisfactionReasonLabel(satisfaction.termination_reason, isZh)}</Dd>
              </>
            )}
          </dl>
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground">
              {isZh ? '问题结果' : 'Question Results'}
            </h4>
            {satisfaction.answers.map((answer, index) => (
              <div key={answer.question_node_id} className="flex items-start justify-between gap-4 rounded-lg bg-muted/40 px-3 py-2 text-sm">
                <div>
                  <p className="font-medium">{index + 1}. {answer.question_name}</p>
                  <p className={answer.option_label ? 'mt-0.5' : 'mt-0.5 text-muted-foreground'}>
                    {answer.option_label || (isZh ? '未回答' : 'Not answered')}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {answer.answered_at ? formatCallRecordDate(answer.answered_at, isZh) : '—'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function satisfactionStatusLabel(status: string, isZh: boolean): string {
  const labels: Record<string, [string, string]> = {
    preparing: ['准备中', 'Preparing'],
    in_progress: ['进行中', 'In progress'],
    completed: ['已完成', 'Completed'],
    partial: ['部分完成', 'Partially completed'],
    unanswered: ['未作答', 'Unanswered'],
    failed: ['启动失败', 'Failed to start'],
  }
  return labels[status]?.[isZh ? 0 : 1] ?? status
}

function satisfactionReasonLabel(reason: string, isZh: boolean): string {
  const labels: Record<string, [string, string]> = {
    customer_hangup: ['客户挂断', 'Customer hung up'],
    // Older executions stored the kernel SIP reason before it was normalized.
    remote_bye: ['客户挂断', 'Customer hung up'],
    bye: ['客户挂断', 'Customer hung up'],
    caller_hangup: ['客户挂断', 'Customer hung up'],
    no_input_exhausted: ['无输入重试耗尽', 'No-input retries exhausted'],
    no_match_exhausted: ['无匹配重试耗尽', 'Invalid-input retries exhausted'],
    workflow_error: ['流程执行异常', 'Workflow error'],
    handoff_failed: ['满意度调查启动失败', 'Survey handoff failed'],
  }
  return labels[reason]?.[isZh ? 0 : 1] ?? reason.replaceAll('_', ' ')
}

function recordingArtifactStatus(status: CallRecordingItem['status'], isZh: boolean): string {
  switch (status) {
    case 'recording':
      return isZh ? '录音中' : 'Recording'
    case 'completed':
      return isZh ? '已完成' : 'Completed'
    case 'partial':
      return isZh ? '录音分段' : 'Segmented'
    case 'failed':
      return isZh ? '录音失败' : 'Failed'
    default:
      return status
  }
}

function optionLabel(group: string, value: string | null | undefined, locale: Locale): string {
  if (!value) return '-'
  const key = `ws.records.calls.option.${group}.${value}`
  const translated = t(key, locale)
  return translated === key ? value : translated
}

function SatisfactionResultSummary({
  record,
  locale,
}: {
  record: Pick<
    CallRecordListItem,
    | 'satisfaction_result'
    | 'satisfaction_primary_option_label'
    | 'satisfaction_answer_count'
  >
  locale: Locale
}) {
  if (!record.satisfaction_result) return <span>-</span>
  const result = optionLabel('satisfactionResult', record.satisfaction_result, locale)
  if (!record.satisfaction_primary_option_label) {
    return <span>{result}</span>
  }
  return (
    <span className="inline-flex max-w-full flex-wrap items-center gap-1.5">
      <span>{record.satisfaction_primary_option_label}</span>
      {(record.satisfaction_answer_count ?? 0) > 1 && (
        <span className="text-xs text-muted-foreground">
          {t('ws.records.calls.satisfaction.answerCount', locale, {
            count: record.satisfaction_answer_count ?? 0,
          })}
        </span>
      )}
      {record.satisfaction_result === 'partial' && (
        <span className="text-xs text-warning">{result}</span>
      )}
    </span>
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
  queue: CallRecordDetail['last_queue']
  locale: Locale
}) {
  if (!queue?.name) return <span>-</span>
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <span className="min-w-0 break-words">{queue.name}</span>
      <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] leading-4 text-muted-foreground">
        {t(
          `ws.records.calls.filter.${queue.queue_type === 'employee' ? 'personalQueue' : 'groupQueue'}`,
          locale,
        )}
      </span>
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

function recordingFileName(record: CallRecordDetail, recording: CallRecordingItem): string {
  const safeCallId = record.call_id.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[.-]+|[.-]+$/g, '')
  let suffix = '.wav'
  try {
    const pathname = new URL(recording.access_url || '', window.location.href).pathname
    const matched = pathname.match(/\.(wav|mp3|m4a|aac|ogg|webm|flac)$/i)
    if (matched) suffix = `.${matched[1].toLowerCase()}`
  } catch {
    // Keep the default extension for malformed legacy URLs.
  }
  return `call-recording-${safeCallId || record.id}-${recording.recording_id}${suffix}`
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
