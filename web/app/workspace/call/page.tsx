'use client'
/**
 * Call center workspace.
 *
 * Wires the agent's UI to three real channels:
 *  - HTTPS REST for status changes and call history
 *  - WebRTC for media — set up via the `useWebRTCLeg`
 *    hook which forwards SDP/ICE through our backend's
 *    `/agents/me/webrtc/{offer,ice}` endpoints
 *  - Socket.IO (`/chat` namespace) for incoming-call hints and downward
 *    ICE candidates pushed by the orchestrator
 *
 * UI phases:
 *   mic_check → granted → idle → incoming → on_call → wrap_up
 */
import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconCheck,
  IconChevronDown,
  IconDownload,
  IconMicrophone,
  IconMicrophoneOff,
  IconPhone,
  IconPhoneIncoming,
  IconPhoneOff,
  IconPhoneOutgoing,
} from '@tabler/icons-react'
import { toast } from 'sonner'

import { DialBar } from '@/app/components/features/call-center/dial-bar'
import { CallUserInfoPanel } from '@/app/components/features/call-center/call-user-info-panel'
import {
  callRecordCustomerNumber,
  callRecordServiceNumber,
} from '@/app/components/features/call-center/call-record-utils'
import { CallSummaryFields } from '@/app/components/features/call-summary/call-summary-fields'
import { CallTicketDraftPanel } from '@/app/components/features/call-summary/call-ticket-draft-panel'
import {
  CALL_STATUS_OPTIONS,
  useCallCenterRuntime,
} from '@/context/call-center-runtime'
import { useAuthStore } from '@/context/auth-store'
import { cn } from '@/lib/utils'
import { useCallRecord } from '@/service/use-call-center'
import type { AgentStatus } from '@/models/call-center'
import { hasPermission } from '@/utils/permissions'

const STATUS_OPTIONS: {
  value: AgentStatus
  label: string
  dotClass: string
  textClass: string
}[] = CALL_STATUS_OPTIONS

function formatRelative(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return d.toLocaleDateString()
}

function formatDuration(ms: number | null): string {
  if (!ms || ms <= 0) return '00:00'
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export default function CallWorkspacePage() {
  const router = useRouter()
  const currentUser = useAuthStore((state) => state.user)
  const {
    mic,
    leg,
    phase,
    incoming,
    callStart,
    now,
    status,
    records,
    selectedRecordId,
    setSelectedRecordId,
    setDraftDialNumber,
    setDraftOutboundNumber,
    callSummaryTab,
    setCallSummaryTab,
    selectedRecord,
    callSummaryRecordId,
    callRecordForTicket,
    screenPopNumber,
    showEmptyCallState,
    statusChangePending,
    setAgentStatus,
    accept,
    reject,
    hangup,
    completeWrapUp,
    handleDialStarted,
  } = useCallCenterRuntime()
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false)
  const statusDropdownRef = useRef<HTMLDivElement>(null)
  const canCreateTicket = hasPermission(currentUser, 'ticket.workspace.create')

  useEffect(() => {
    if (!canCreateTicket && callSummaryTab === 'ticket') {
      setCallSummaryTab('summary')
    }
  }, [canCreateTicket, callSummaryTab, setCallSummaryTab])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (statusDropdownRef.current && !statusDropdownRef.current.contains(e.target as Node)) {
        setStatusDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const currentStatus = phase === 'wrap_up' ? 'after_call_work' : (status?.status ?? 'offline')
  const currentStatusOption = STATUS_OPTIONS.find((o) => o.value === currentStatus) ?? STATUS_OPTIONS[4]
  const statusSelectorDisabled = statusChangePending || mic.state === 'checking'

  return (
    <div className="flex h-full">
      {/* ──────────────── Left panel ──────────────── */}
      <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-white">
        <div className="p-4">
          <h3 className="mb-2 text-[11px] font-semibold text-foreground/70">客服状态</h3>
          <div className="relative" ref={statusDropdownRef}>
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={statusDropdownOpen}
              disabled={statusSelectorDisabled}
              onClick={() => setStatusDropdownOpen((open) => !open)}
              className={cn(
                'flex h-10 w-full items-center gap-2 rounded-md border border-border px-3 text-left text-[13px] transition-colors',
                statusSelectorDisabled
                  ? 'cursor-not-allowed bg-muted/50 opacity-70'
                  : 'bg-white hover:bg-muted/50',
              )}
            >
              <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', currentStatusOption.dotClass)} />
              <span className={cn('min-w-0 flex-1 truncate font-medium', currentStatusOption.textClass)}>
                {currentStatusOption.label}
              </span>
              {statusChangePending ? (
                <span className="h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
              ) : (
                <IconChevronDown size={16} className="shrink-0 text-[#999999]" />
              )}
            </button>
            {statusDropdownOpen && !statusSelectorDisabled && (
              <div
                role="menu"
                className="absolute left-0 top-full z-50 mt-1 w-full overflow-hidden rounded-lg border border-[#E5E5E5] bg-white py-1 shadow-lg"
              >
                {STATUS_OPTIONS.map((option) => {
                  const active = currentStatus === option.value
                  return (
                    <button
                      key={option.value}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setStatusDropdownOpen(false)
                        if (option.value !== currentStatus) void setAgentStatus(option.value)
                      }}
                      className={cn(
                        'flex w-full items-center gap-2 px-3 py-2 text-[13px] text-[#1a1a1a] transition-colors hover:bg-[#F5F5F5]',
                        active && 'font-semibold',
                      )}
                    >
                      <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', option.dotClass)} />
                      <span className="min-w-0 flex-1 truncate text-left">{option.label}</span>
                      {active && <IconCheck size={14} className="shrink-0 text-[#22C55E]" />}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {leg.state === 'ready' && leg.callId
              ? `通话中 · WebRTC: ${leg.callId.slice(-8)}`
              : leg.state === 'connecting'
                ? '正在接通...'
                : phase === 'wrap_up'
                  ? '整理中 · 完成本次记录后恢复就绪'
                  : status?.status === 'ready'
                  ? '已就绪 · 等待来电'
                  : '请切换至「就绪」开始接收来电'}
          </p>
          {leg.error && (
            <p className="mt-1 rounded bg-red-50 px-2 py-1 text-[11px] text-red-700">
              WebRTC 错误：{leg.error}
            </p>
          )}
          {mic.error && (
            <p className="mt-1 rounded bg-red-50 px-2 py-1 text-[11px] text-red-700">
              麦克风错误：{mic.error}
            </p>
          )}
          {phase === 'mic_denied' && (
            <p className="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-700">
              麦克风权限未授权，请在浏览器中允许后刷新。
            </p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          <h3 className="px-2 text-xs font-semibold text-foreground/70">最近通话</h3>
          {(records?.items ?? []).length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">暂无通话记录</p>
          ) : (
            (records?.items ?? []).slice(0, 20).map((r) => {
              const active = r.id === selectedRecordId
              return (
                <button
                  type="button"
                  key={r.id}
                  onClick={() => setSelectedRecordId(r.id)}
                  className={`my-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition ${
                    active ? 'bg-primary/10 ring-1 ring-primary/40' : 'hover:bg-muted'
                  }`}
                >
                  {r.direction === 'inbound' ? (
                    <IconPhoneIncoming size={14} className="text-blue-500" />
                  ) : (
                    <IconPhoneOutgoing size={14} className="text-green-500" />
                  )}
                  <span className="truncate">{callRecordCustomerNumber(r) || '未知号码'}</span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                    {formatRelative(r.started_at)}
                  </span>
                </button>
              )
            })
          )}
        </div>
      </aside>

      {/* ──────────────── Right main ──────────────── */}
      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Call bar */}
        <div
          className={`border-b px-5 py-5 ${
            phase === 'incoming'
              ? 'border-amber-300 bg-amber-50'
              : phase === 'outbound_ringing'
                ? 'border-sky-300 bg-sky-50'
                : phase === 'on_call'
                  ? 'border-green-200 bg-green-50'
                  : phase === 'wrap_up'
                    ? 'bg-muted'
                    : 'bg-white'
          }`}
        >
          {phase === 'mic_check' && (
            <p className="text-sm text-muted-foreground">正在检测麦克风权限...</p>
          )}
          {phase === 'mic_denied' && (
            <div className="flex items-center gap-3">
              <IconMicrophoneOff size={20} className="text-red-600" />
              <span className="text-sm font-medium text-red-700">麦克风未授权 — 无法接听</span>
              <button
                type="button"
                onClick={() => void mic.request()}
                className="rounded-md border border-border bg-white px-3 py-1.5 text-sm hover:bg-muted"
              >
                重试授权
              </button>
            </div>
          )}
          {phase === 'idle' && (
            <DialBar
              disabled={mic.state === 'checking'}
              statusHint={leg.state === 'ready' ? '等待来电' : undefined}
              onDialNumberChange={setDraftDialNumber}
              onOutboundNumberChange={(_, phoneNumber) => setDraftOutboundNumber(phoneNumber)}
              onDialStarted={(info) => void handleDialStarted(info)}
            />
          )}
          {phase === 'incoming' && incoming && (
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100">
                  <IconPhoneIncoming size={16} className="animate-pulse text-amber-700" />
                </span>
                <span className="font-bold text-amber-800">来电</span>
              </div>
              <Field label="通话类型" value="呼入" />
              <Field label="用户号码" value={incoming.from || '未知号码'} strong />
              <Field label="服务号码" value={incoming.to || '—'} />
              <Field
                label="响铃时长"
                value={formatDuration(callStart ? now - callStart : 0)}
                strong
                color="text-amber-700"
              />
              <div className="ml-auto flex gap-2">
                <button
                  type="button"
                  onClick={reject}
                  disabled={leg.state === 'connecting'}
                  className="rounded-full bg-red-500 p-2.5 text-white disabled:opacity-50"
                  title="拒接"
                >
                  <IconPhoneOff size={16} />
                </button>
                <button
                  type="button"
                  onClick={accept}
                  disabled={leg.state === 'connecting'}
                  title={leg.state === 'connecting' ? '正在接通...' : '接听'}
                  className="rounded-full bg-green-500 p-2.5 text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <IconPhone size={16} />
                </button>
              </div>
            </div>
          )}
          {phase === 'outbound_ringing' && incoming && (
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-sky-100">
                  <IconPhoneOutgoing size={16} className="animate-pulse text-sky-700" />
                </span>
                <span className="font-bold text-sky-800">外呼中</span>
              </div>
              <Field label="通话类型" value="呼出" />
              <Field label="外呼号码" value={incoming.from || '—'} />
              <Field label="被叫号码" value={incoming.to || '—'} strong />
              <Field
                label="拨号时长"
                value={formatDuration(callStart ? now - callStart : 0)}
                strong
                color="text-sky-700"
              />
              <div className="ml-auto flex gap-2">
                <button
                  type="button"
                  onClick={hangup}
                  className="rounded-full bg-red-500 p-2.5 text-white"
                  title="取消外呼"
                >
                  <IconPhoneOff size={16} />
                </button>
              </div>
            </div>
          )}
          {phase === 'on_call' && incoming && (
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-green-100">
                  <IconPhone size={16} className="text-green-700" />
                </span>
                <span className="font-bold text-green-800">通话中</span>
              </div>
              <Field
                label="通话类型"
                value={incoming.direction === 'outbound' ? '呼出' : '呼入'}
              />
              <Field
                label={incoming.direction === 'outbound' ? '被叫号码' : '用户号码'}
                value={
                  incoming.direction === 'outbound'
                    ? incoming.to || '—'
                    : incoming.from || '未知号码'
                }
                strong
              />
              <Field
                label="通话时长"
                value={formatDuration(callStart ? now - callStart : 0)}
                strong
                color="text-green-700"
              />
              <div className="ml-auto flex gap-2">
                <button type="button" className="rounded-full border border-border p-2 text-foreground/70">
                  <IconMicrophone size={16} />
                </button>
                <button type="button" onClick={hangup} className="rounded-full bg-red-500 p-2.5 text-white">
                  <IconPhoneOff size={16} />
                </button>
              </div>
            </div>
          )}
          {phase === 'wrap_up' && (
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100">
                  <IconCheck size={16} className="text-amber-700" />
                </span>
                <div>
                  <p className="font-bold">通话已结束，请整理本次记录</p>
                  <p className="text-xs text-muted-foreground">
                    本次通话时长：{formatDuration(callStart ? Date.now() - callStart : 0)}
                  </p>
                </div>
              </div>
              <button type="button" onClick={completeWrapUp} className="ml-auto rounded-full bg-green-500 p-2.5 text-white">
                <IconCheck size={16} />
              </button>
            </div>
          )}
        </div>

        {/* Aux info area */}
        <div className={`flex-1 overflow-y-auto ${showEmptyCallState ? 'bg-white' : 'bg-muted p-5'}`}>
          {showEmptyCallState ? (
            <CallWorkspaceEmptyState />
          ) : (
            <div className="grid gap-4 xl:grid-cols-3">
              <section className="rounded-xl border border-border bg-white p-5">
                <div className="mb-3 flex items-center border-b border-border pb-2">
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <IconPhone size={16} className="text-muted-foreground" />
                    通话信息
                  </h3>
                </div>
                {selectedRecord ? (
                  <HistoryDetail recordId={selectedRecord.id} />
                ) : incoming?.direction === 'outbound' ? (
                  <dl className="grid grid-cols-2 gap-y-2 text-sm">
                    <Dt>通话类型</Dt><Dd>呼出</Dd>
                    <Dt>外呼号码</Dt><Dd>{incoming?.from || '—'}</Dd>
                    <Dt>被叫号码</Dt><Dd>{incoming?.to || '—'}</Dd>
                    <Dt>通话时长</Dt>
                    <Dd>
                      {phase === 'outbound_ringing'
                        ? '拨号中...'
                        : formatDuration(callStart ? Date.now() - callStart : 0)}
                    </Dd>
                    <Dt>发起时间</Dt>
                    <Dd>{callStart ? new Date(callStart).toLocaleTimeString() : '—'}</Dd>
                    <Dt>通话 ID</Dt>
                    <Dd>{incoming?.call_id ? <code className="font-mono text-xs">{incoming.call_id}</code> : '—'}</Dd>
                  </dl>
                ) : (
                  <dl className="grid grid-cols-2 gap-y-2 text-sm">
                    <Dt>通话类型</Dt><Dd>呼入</Dd>
                    <Dt>用户号码</Dt><Dd>{incoming?.from || '未知号码'}</Dd>
                    <Dt>服务号码</Dt><Dd>{incoming?.to || '—'}</Dd>
                    <Dt>通话时长</Dt>
                    <Dd>
                      {phase === 'incoming'
                        ? '响铃中...'
                        : formatDuration(callStart ? Date.now() - callStart : 0)}
                    </Dd>
                    <Dt>来电时间</Dt>
                    <Dd>{callStart ? new Date(callStart).toLocaleTimeString() : '—'}</Dd>
                    <Dt>通话 ID</Dt>
                    <Dd>{incoming?.call_id ? <code className="font-mono text-xs">{incoming.call_id}</code> : '—'}</Dd>
                  </dl>
                )}
              </section>

              <section className="rounded-xl border border-border bg-white p-5">
                <CallUserInfoPanel
                  recordId={callSummaryRecordId}
                  fallbackNumber={screenPopNumber}
                />
              </section>

              <section className="rounded-xl border border-border bg-white p-5">
                {callRecordForTicket && (
                  <div className="mb-3 flex items-center border-b border-border pb-2">
                    <div className="flex shrink-0 rounded-md border border-border bg-muted p-0.5">
                      <button
                        type="button"
                        onClick={() => setCallSummaryTab('summary')}
                        className={cn(
                          'rounded px-2 py-1 text-xs font-medium transition-colors',
                          callSummaryTab === 'summary'
                            ? 'bg-white text-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        通话纪要
                      </button>
                      {canCreateTicket && (
                        <button
                          type="button"
                          onClick={() => setCallSummaryTab('ticket')}
                          className={cn(
                            'rounded px-2 py-1 text-xs font-medium transition-colors',
                            callSummaryTab === 'ticket'
                              ? 'bg-white text-foreground shadow-sm'
                              : 'text-muted-foreground hover:text-foreground',
                          )}
                        >
                          新建工单
                        </button>
                      )}
                    </div>
                  </div>
                )}
                {canCreateTicket && callSummaryTab === 'ticket' && callRecordForTicket ? (
                  <CallTicketDraftPanel
                    key={callRecordForTicket.id}
                    callRecord={callRecordForTicket}
                    onClose={() => setCallSummaryTab('summary')}
                    onNotice={(type, text, payload) => {
                      if (type === 'success') {
                        const ticket = payload?.ticket
                        if (ticket) {
                          let toastId: string | number | undefined
                          const openTicket = () => {
                            if (toastId !== undefined) toast.dismiss(toastId)
                            router.push(`/workspace/tickets/${ticket.id}?from=list`)
                          }
                          toastId = toast.success(
                            <button
                              type="button"
                              onClick={openTicket}
                              className="block w-full cursor-pointer appearance-none border-0 bg-transparent p-0 text-left font-medium text-inherit underline-offset-2 hover:underline"
                            >
                              {text}
                            </button>,
                          )
                        } else {
                          toast.success(text)
                        }
                      } else {
                        toast.error(text)
                      }
                    }}
                  />
                ) : (
                  <CallSummaryFields callRecordId={callSummaryRecordId} />
                )}
              </section>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

function Field({
  label, value, strong, color,
}: {
  label: string
  value: string
  strong?: boolean
  color?: string
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`${strong ? 'font-bold' : ''} ${color ?? 'text-foreground'}`}>{value}</p>
    </div>
  )
}

function Dt({ children }: { children: React.ReactNode }) {
  return <dt className="text-foreground/70">{children}</dt>
}

function Dd({ children }: { children: React.ReactNode }) {
  return <dd className="text-foreground">{children}</dd>
}

function CallWorkspaceEmptyState() {
  return (
    <div className="flex h-full min-h-[360px] items-center justify-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#F5F5F5]">
        <IconPhone size={32} className="text-[#999999]" />
      </div>
    </div>
  )
}

function HistoryDetail({ recordId }: { recordId: number }) {
  const { data: record, isLoading, refetch } = useCallRecord(recordId)

  // Recording file may land a few seconds after hangup.
  useEffect(() => {
    if (!record || record.recording_url || record.state !== 'completed') return
    const endedAt = record.ended_at ? new Date(record.ended_at).getTime() : 0
    if (!endedAt || Date.now() - endedAt > 60_000) return
    const timer = window.setInterval(() => {
      void refetch()
    }, 3000)
    return () => window.clearInterval(timer)
  }, [record, refetch])

  if (isLoading || !record) {
    return <p className="py-4 text-sm text-muted-foreground">加载中...</p>
  }

  const started = record.started_at ? new Date(record.started_at) : null
  const ended = record.ended_at ? new Date(record.ended_at) : null
  const customerNumber = callRecordCustomerNumber(record)
  const serviceNumber = callRecordServiceNumber(record)
  return (
    <div className="space-y-4">
      <section>
        <h4 className="mb-2 text-xs font-semibold text-foreground/70">通话录音</h4>
        {record.recording_url ? (
          <div className="flex items-center gap-2">
            <audio src={record.recording_url} controls className="min-w-0 flex-1" />
            <a
              href={record.recording_url}
              download
              className="shrink-0 rounded-md border border-border p-2 hover:bg-muted"
            >
              <IconDownload size={16} />
            </a>
          </div>
        ) : (
          <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
            <IconMicrophoneOff size={16} />
            <span>暂无通话录音</span>
          </div>
        )}
      </section>
      <dl className="grid grid-cols-2 gap-y-2 text-sm">
        <Dt>通话类型</Dt><Dd>{record.direction === 'inbound' ? '呼入' : '呼出'}</Dd>
        <Dt>用户号码</Dt><Dd>{customerNumber || '—'}</Dd>
        <Dt>服务号码</Dt><Dd>{serviceNumber || '—'}</Dd>
        <Dt>通话时长</Dt><Dd>{formatDuration(record.talk_duration_ms)}</Dd>
        <Dt>响铃时长</Dt><Dd>{formatDuration(record.ring_duration_ms)}</Dd>
        <Dt>来电时间</Dt><Dd>{started ? started.toLocaleString() : '—'}</Dd>
        <Dt>结束时间</Dt><Dd>{ended ? ended.toLocaleString() : '—'}</Dd>
        <Dt>接听坐席</Dt><Dd>{record.agent_name || '—'}</Dd>
        <Dt>状态</Dt><Dd>{record.state || '—'}</Dd>
        <Dt>通话 ID</Dt>
        <Dd><code className="font-mono text-xs">{record.call_id}</code></Dd>
      </dl>
    </div>
  )
}
