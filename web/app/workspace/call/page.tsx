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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import {
  IconArrowLeft,
  IconCheck,
  IconChevronDown,
  IconClipboardList,
  IconDownload,
  IconMessage,
  IconMicrophoneOff,
  IconPhone,
  IconPhoneIncoming,
  IconPhoneOff,
  IconPhoneOutgoing,
  IconX,
} from '@tabler/icons-react'
import { toast } from 'sonner'

import { AgentCallBar } from '@/app/components/features/call-center/agent-call-bar'
import { controlErrorMessage } from '@/app/components/features/call-center/use-call-control'
import { AutoOutboundBusinessPanel } from '@/app/components/features/call-center/auto-outbound-business-panel'
import { CallDeviceSelector } from '@/app/components/features/call-center/call-device-selector'
import { DialBar } from '@/app/components/features/call-center/dial-bar'
import { SendSmsDialog } from '@/app/components/features/call-center/send-sms-dialog'
import { MyOutboundTargetsView } from '@/app/components/features/call-center/my-outbound-targets-view'
import { PersonalAutoOutboundView } from '@/app/components/features/call-center/personal-auto-outbound-view'
import { PersonalAutoOutboundBusinessPanel } from '@/app/components/features/call-center/personal-auto-outbound-business-panel'
import { PersonalAutoOutboundTaskPop } from '@/app/components/features/call-center/personal-auto-outbound-task-pop'
import {
  CallTranscriptHistory,
  CallTranscriptPanel,
} from '@/app/components/features/call-center/call-transcript-panel'
import { CallUserInfoPanel } from '@/app/components/features/call-center/call-user-info-panel'
import {
  callRecordCustomerNumber,
  callRecordServiceNumber,
  selectDisplayRecording,
} from '@/app/components/features/call-center/call-record-utils'
import {
  formatCallRecordState,
  formatHangupReason,
  formatWebRtcDeviceError,
} from '@/lib/call-record-labels'
import {
  autoOutboundIncomingForCallRecord,
  isAutoOutboundIncoming,
  isPersonalAutoOutboundIncoming,
  shouldAutoAcceptAutoOutbound,
  shouldShowAutoOutboundBusinessTab,
} from '@/lib/auto-outbound-incoming'
import { CallSummaryFields } from '@/app/components/features/call-summary/call-summary-fields'
import { CallTicketDraftPanel } from '@/app/components/features/call-summary/call-ticket-draft-panel'
import {
  CALL_STATUS_OPTIONS,
  useCallCenterRuntime,
} from '@/context/call-center-runtime'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { dialOutbound, useCallRecord, useResetAgentStatus } from '@/service/use-call-center'
import { useMyCallDevices, useMyCurrentCallDevice } from '@/service/use-agent-devices'
import { useSystemInfo } from '@/service/use-system'
import { useWorkspaceEmbeddedPages } from '@/service/use-embedded-pages'
import { EmbeddedPagePanel } from '@/app/components/features/chat/embedded-page-panel'
import { t } from '@/utils/i18n'
import type { AgentStatus } from '@/models/call-center'
import type { EmbeddedPageContext } from '@/models/embedded-page'
import { hasPermission } from '@/utils/permissions'
import { isCnMobileNumber } from '@/utils/validators'
import type { OutboundTarget } from '@/models/outbound-task'
import { useSmsWorkspaceTemplates } from '@/service/use-sms'
import {
  callWorkspaceHref,
  nextAnchorAfterDialNumberChange,
  nextAnchorAfterIdle,
  resolveCallWorkspaceRoute,
  taskDialBlockReason,
  type CallWorkspaceAnchor,
  type CallWorkspaceMainView,
  type CallWorkspaceRouteEvent,
} from '@/lib/call-workspace-view'

type PopTab = 'system' | `embedded:${number}`

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
  const searchParams = useSearchParams()
  const currentUser = useAuthStore((state) => state.user)
  const { locale } = useLocaleStore()
  const { data: systemInfo } = useSystemInfo()
  const {
    mic,
    leg,
    callControl,
    phase,
    incoming,
    callStart,
    screenPopIncoming,
    screenPopCallStart,
    now,
    status,
    records,
    recordsPage,
    setRecordsPage,
    selectedRecordId,
    setSelectedRecordId,
    draftDialNumber,
    setDraftDialNumber,
    draftOutboundNumber,
    setDraftOutboundNumber,
    callSummaryTab,
    setCallSummaryTab,
    selectedRecord,
    currentRecord,
    callSummaryRecordId,
    callRecordForTicket,
    screenPopNumber,
    showEmptyCallState,
    statusChangePending,
    wrapUpUntil,
    setAgentStatus,
    accept,
    reject,
    hangup,
    completeWrapUp,
    handleDialStarted,
  } = useCallCenterRuntime()
  const isAutoOutbound = isAutoOutboundIncoming(screenPopIncoming)
  const autoOutboundBusinessIncoming = selectedRecord
    ? autoOutboundIncomingForCallRecord(selectedRecord)
    : screenPopIncoming
  const showAutoOutboundTab = shouldShowAutoOutboundBusinessTab(autoOutboundBusinessIncoming)
  const showPersonalAutoOutboundTab =
    isPersonalAutoOutboundIncoming(screenPopIncoming) &&
    Number(screenPopIncoming?.record_id) > 0
  const autoAccepting =
    phase === 'incoming' &&
    shouldAutoAcceptAutoOutbound({
      source: incoming?.source,
      deviceType: incoming?.device_type,
    })
  const autoOutboundUserNumber =
    screenPopIncoming?.to ||
    screenPopIncoming?.customer_from ||
    screenPopIncoming?.from ||
    '未知号码'
  const callTypeInboundLabel = isPersonalAutoOutboundIncoming(screenPopIncoming)
    ? t(screenPopIncoming?.personal_assignment_type === 'fallback' ? 'personalAuto.callTypeFallback' : 'personalAuto.callTypePrimary', locale)
    : isAutoOutbound
    ? t('ws.autoOutbound.agent.callType', locale)
    : '呼入'
  const screenPopDuration = formatDuration(
    currentRecord?.customer_agent_talk_duration_ms ??
      (screenPopCallStart ? Math.max(0, now - screenPopCallStart) : 0),
  )
  const screenPopDurationLabel =
    phase === 'outbound_ringing'
      ? '拨号中...'
      : phase === 'incoming'
        ? '响铃中...'
        : screenPopDuration
  const { data: devicesData } = useMyCallDevices({ refetchInterval: 15_000 })
  const { data: currentDevice } = useMyCurrentCallDevice()
  const resetStatus = useResetAgentStatus()
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false)
  const [callCenterNoticeDismissed, setCallCenterNoticeDismissed] = useState(false)
  const statusDropdownRef = useRef<HTMLDivElement>(null)
  const canCreateTicket = hasPermission(currentUser, 'ticket.workspace.create')
  const canDialOutbound = hasPermission(currentUser, 'call.dial.outbound')
  const canSendSms = hasPermission(currentUser, 'call.workspace.sms.send')
  const workspaceSmsTemplatesQuery = useSmsWorkspaceTemplates({ enabled: canSendSms })
  const workspaceSmsTemplates = workspaceSmsTemplatesQuery.data?.items ?? []
  const showSmsEntry = canSendSms && workspaceSmsTemplates.length > 0
  const [smsDialog, setSmsDialog] = useState<{
    phone: string
    phoneReadonly: boolean
    callId: string | null
  } | null>(null)
  const callCustomerNumber = incoming?.direction === 'outbound' ? incoming?.to : incoming?.from
  const callSmsDisabledReason = isCnMobileNumber(callCustomerNumber)
    ? null
    : t('sms.send.disabledNoCallNumber', locale)
  // The in-call strip shares the console's semantic tone instead of stacking a
  // taller card under the dial area.
  const onCallStripClass =
    callControl.mode === 'hold' ||
    callControl.mode === 'consult_ringing' ||
    callControl.mode === 'consult_active'
      ? 'border-warning/30 bg-warning/10'
      : callControl.mode === 'transferring' || callControl.mode === 'conference_ringing'
        ? 'border-border bg-muted/40'
        : 'border-success/30 bg-success/10'
  const canExecuteOutboundTasks = hasPermission(currentUser, 'engagement.outbound_task.execute')
  const canPersonalAutoOutbound = hasPermission(currentUser, 'call.personal_auto_outbound.use')
  const requestedView = searchParams.get('view')
  const requestedTaskId = useMemo(() => {
    const raw = Number(searchParams.get('taskId'))
    return Number.isInteger(raw) && raw > 0 ? raw : null
  }, [searchParams])
  const showingOutboundTasks =
    canExecuteOutboundTasks && requestedView === 'outbound-tasks'
  const showingPersonalAutoOutbound =
    canPersonalAutoOutbound && requestedView === 'personal-auto-outbound'
  const currentMainView: CallWorkspaceMainView = showingPersonalAutoOutbound
    ? 'personal-auto-outbound'
    : showingOutboundTasks
      ? 'outbound-tasks'
      : 'screen-pop'
  const [workspaceAnchor, setWorkspaceAnchor] = useState<CallWorkspaceAnchor>(null)
  // In-memory only: switching to the screen pop keeps the task view mounted
  // (and the URL unchanged), so drafts survive and a refresh returns to the task.
  const [screenPopOverride, setScreenPopOverride] = useState(false)
  const [draftOutboundId, setDraftOutboundId] = useState('')
  const workspaceRouteRef = useRef({ view: currentMainView, anchor: workspaceAnchor, urlTaskId: requestedTaskId })
  workspaceRouteRef.current = { view: currentMainView, anchor: workspaceAnchor, urlTaskId: requestedTaskId }
  const taskDialRef = useRef({
    phase,
    canDialOutbound,
    hasUsableDevice: false,
    micChecking: mic.state === 'checking',
    outboundNumberId: '',
    outboundNumber: '',
    agentStatus: 'offline',
  })
  const applyWorkspaceRoute = useCallback((event: CallWorkspaceRouteEvent) => {
    const { view, anchor, urlTaskId } = workspaceRouteRef.current
    const next = resolveCallWorkspaceRoute({ currentView: view, anchor, event })
    setWorkspaceAnchor(next.anchor)
    // Also navigate when the anchored task differs from the task in the URL —
    // e.g. the agent returned to the task list mid-call, then reselects the
    // live call and lands back on that task's exec page.
    const taskIdChanged =
      next.view === 'outbound-tasks' &&
      view === 'outbound-tasks' &&
      (next.anchor?.taskId ?? urlTaskId) !== urlTaskId
    if (next.view !== view || taskIdChanged) {
      router.push(callWorkspaceHref(next.view, next.anchor))
    }
  }, [router])
  useEffect(() => {
    if (requestedView === 'personal-auto-outbound' && !canPersonalAutoOutbound) {
      router.replace('/403')
    }
  }, [canPersonalAutoOutbound, requestedView, router])
  useEffect(() => {
    if (phase !== 'incoming' || !incoming) return
    applyWorkspaceRoute({
      type: 'incoming',
      source: incoming.source,
      callId: incoming.call_id,
    })
  }, [applyWorkspaceRoute, incoming, phase])
  useEffect(() => {
    if (phase === 'idle' || phase === 'mic_check' || phase === 'mic_denied') {
      setWorkspaceAnchor((current) => nextAnchorAfterIdle(current))
    }
  }, [phase])
  useEffect(() => {
    if (!showingOutboundTasks) setScreenPopOverride(false)
  }, [showingOutboundTasks])
  // A task call that ends drops back to the task view's wrap-up screen by default.
  useEffect(() => {
    if (phase === 'wrap_up' && workspaceAnchor?.view === 'outbound-tasks') {
      setScreenPopOverride(false)
    }
  }, [phase, workspaceAnchor?.view])
  // Selecting the live call's own record must still show the live panel +
  // realtime transcript (not HistoryDetail). Only other records count as history.
  const isViewingHistory = Boolean(
    selectedRecord &&
      !(
        screenPopIncoming?.call_id &&
        selectedRecord.call_id === screenPopIncoming.call_id
      ),
  )
  const viewingHistoryDuringLiveCall =
    isViewingHistory &&
    !!screenPopIncoming?.call_id &&
    (phase === 'on_call' ||
      phase === 'incoming' ||
      phase === 'wrap_up' ||
      phase === 'outbound_ringing')

  const embeddedPagesQuery = useWorkspaceEmbeddedPages('call_screen_pop')
  const embeddedPages = useMemo(() => embeddedPagesQuery.data?.items ?? [], [embeddedPagesQuery.data?.items])
  const embeddedAgent = embeddedPagesQuery.data?.agent ?? null
  const [popTab, setPopTab] = useState<PopTab>('system')
  const [mountedEmbeddedIds, setMountedEmbeddedIds] = useState<ReadonlySet<number>>(new Set())
  const showPopTabs = embeddedPages.length > 0
  // If the active embedded page gets disabled or deleted, fall back to the system pop.
  const visiblePopTab: PopTab =
    popTab.startsWith('embedded:') && !embeddedPages.some((page) => `embedded:${page.id}` === popTab)
      ? 'system'
      : popTab

  const prevPopCallIdRef = useRef<string | null>(null)
  const popTabDecisionRef = useRef<string | null>(null)
  useEffect(() => {
    const callId = screenPopIncoming?.call_id ?? null
    if (callId !== prevPopCallIdRef.current) {
      prevPopCallIdRef.current = callId
      popTabDecisionRef.current = null
    }
    if (!callId) return
    if (popTabDecisionRef.current === callId) return
    // Wait for the page list so default focus is honored on first pop; viewing a
    // history record never re-triggers it (applied when the agent returns to the live call).
    if (embeddedPagesQuery.isPending || isViewingHistory) return
    popTabDecisionRef.current = callId
    const defaultFocusPage = embeddedPages.find((page) => page.default_focus)
    setPopTab(defaultFocusPage ? `embedded:${defaultFocusPage.id}` : 'system')
  }, [screenPopIncoming?.call_id, embeddedPages, embeddedPagesQuery.isPending, isViewingHistory])

  useEffect(() => {
    if (!visiblePopTab.startsWith('embedded:')) return
    const id = Number(visiblePopTab.slice('embedded:'.length))
    setMountedEmbeddedIds((prev) => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      return next
    })
  }, [visiblePopTab])

  const embeddedContext = useMemo<EmbeddedPageContext>(() => {
    const record = callRecordForTicket
    return {
      location: 'call_screen_pop',
      agent: embeddedAgent
        ? { id: embeddedAgent.id, name: embeddedAgent.name, email: embeddedAgent.email }
        : null,
      conversation: null,
      visitor: null,
      call:
        record || screenPopIncoming
          ? {
              recordId: record?.id ?? 0,
              direction: record?.direction ?? screenPopIncoming?.direction ?? 'inbound',
              customerNumber: record ? callRecordCustomerNumber(record) ?? '' : screenPopNumber,
              queueId: record?.last_queue?.queue_id ?? screenPopIncoming?.queue_id ?? null,
              startedAt:
                record?.started_at ??
                (screenPopCallStart ? new Date(screenPopCallStart).toISOString() : null),
            }
          : null,
      user: record?.user_id
        ? { id: record.user_id, name: record.user_name ?? '', phone: record.user_phone }
        : null,
    }
  }, [
    callRecordForTicket,
    embeddedAgent,
    screenPopIncoming,
    screenPopNumber,
    screenPopCallStart,
  ])

  useEffect(() => {
    if (!canCreateTicket && callSummaryTab === 'ticket') {
      setCallSummaryTab('summary')
    }
    if (!showAutoOutboundTab && callSummaryTab === 'auto_outbound') {
      setCallSummaryTab('summary')
    }
    if (!showPersonalAutoOutboundTab && callSummaryTab === 'personal_auto_outbound') {
      setCallSummaryTab('summary')
    }
  }, [canCreateTicket, callSummaryTab, setCallSummaryTab, showAutoOutboundTab, showPersonalAutoOutboundTab])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (statusDropdownRef.current && !statusDropdownRef.current.contains(e.target as Node)) {
        setStatusDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const showCallCenterNotice =
    systemInfo != null && !systemInfo.call_center_enabled && !callCenterNoticeDismissed

  // While ringing / on a live call, show 忙碌 even if the polled PG status
  // still says 就绪 (common for consult targets before status catches up).
  const currentStatus =
    phase === 'wrap_up'
      ? 'after_call_work'
      : phase === 'on_call' ||
          phase === 'incoming' ||
          phase === 'outbound_ringing'
        ? 'busy'
        : (status?.status ?? 'offline')
  const currentStatusOption = STATUS_OPTIONS.find((o) => o.value === currentStatus) ?? STATUS_OPTIONS[4]
  const statusFrozen =
    phase === 'incoming' || phase === 'outbound_ringing' || phase === 'on_call'
  const statusSelectorDisabled =
    statusChangePending || mic.state === 'checking' || statusFrozen

  // A usable current device is required before the agent can go "ready" or dial.
  // The server enforces the same rule (409); the UI disables it as a first line.
  const activeDevice = (devicesData?.items ?? []).find(
    (device) => device.device_type === currentDevice?.device_type,
  )
  const hasUsableDevice = !!currentDevice?.device_type && !!activeDevice?.available
  const dialBlockedOffline = currentStatus === 'offline'
  taskDialRef.current = {
    phase,
    canDialOutbound,
    hasUsableDevice,
    micChecking: mic.state === 'checking',
    outboundNumberId: draftOutboundId,
    outboundNumber: draftOutboundNumber,
    agentStatus: currentStatus,
  }
  const startTaskCall = useCallback(async (phone: string, taskId?: number) => {
    const destination = phone.trim()
    setDraftDialNumber(destination)
    applyWorkspaceRoute({ type: 'task-call-armed', phone: destination, taskId })
    const blocked = taskDialBlockReason(taskDialRef.current)
    if (blocked) {
      toast.error(blocked)
      return
    }
    try {
      const resp = await dialOutbound({
        outbound_phone_number_id: taskDialRef.current.outboundNumberId,
        destination,
      })
      applyWorkspaceRoute({
        type: 'dial-started',
        destination,
        callId: resp.call_id,
      })
      await handleDialStarted({
        callId: resp.call_id,
        destination,
        outboundNumber: taskDialRef.current.outboundNumber,
      })
    } catch (err) {
      toast.error(await controlErrorMessage(err, '外呼失败'))
    }
  }, [applyWorkspaceRoute, handleDialStarted, setDraftDialNumber])

  // Pure UI switch: prefill the dial number so the idle screen pop resolves the
  // customer by number; a live call keeps its own context via `incoming`.
  const openScreenPopFromTask = useCallback((target: OutboundTarget) => {
    setDraftDialNumber(target.phone_number)
    setScreenPopOverride(true)
  }, [setDraftDialNumber])

  return (
    <div className="flex h-full flex-col">
      {showCallCenterNotice && (
        <CallCenterDisabledBanner onClose={() => setCallCenterNoticeDismissed(true)} />
      )}
      <div className="flex min-h-0 flex-1">
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
                  const readyBlocked = option.value === 'ready' && !hasUsableDevice
                  return (
                    <button
                      key={option.value}
                      type="button"
                      role="menuitem"
                      disabled={readyBlocked}
                      title={readyBlocked ? '请先选择可用呼叫设备' : undefined}
                      onClick={() => {
                        setStatusDropdownOpen(false)
                        if (option.value !== currentStatus) void setAgentStatus(option.value)
                      }}
                      className={cn(
                        'flex w-full items-center gap-2 px-3 py-2 text-[13px] text-[#1a1a1a] transition-colors',
                        readyBlocked ? 'cursor-not-allowed opacity-50' : 'hover:bg-[#F5F5F5]',
                        active && 'font-semibold',
                      )}
                    >
                      <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', option.dotClass)} />
                      <span className="min-w-0 flex-1 truncate text-left">{option.label}</span>
                      {active && <IconCheck size={14} className="shrink-0 text-[#22C55E]" />}
                    </button>
                  )
                })}
                {/* Escape hatch: force-free a stranded call resource when a
                    lost call-end event leaves the agent stuck (409 occupied). */}
                <div className="my-1 border-t border-[#EEE]" />
                <button
                  type="button"
                  role="menuitem"
                  disabled={resetStatus.isPending}
                  onClick={async () => {
                    setStatusDropdownOpen(false)
                    try {
                      await resetStatus.mutateAsync()
                      toast.success('已重置通话状态，可重新切换')
                    } catch {
                      toast.error('重置失败，请重试')
                    }
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-[13px] text-muted-foreground transition-colors hover:bg-[#F5F5F5] disabled:opacity-50"
                >
                  <span className="h-2.5 w-2.5 shrink-0" />
                  <span className="min-w-0 flex-1 truncate text-left">重置通话状态</span>
                </button>
              </div>
            )}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {phase === 'on_call'
              ? (incoming?.device_type === 'sip_phone' ||
                  currentDevice?.device_type === 'sip_phone')
                ? '通话中 · 话机接听'
                : leg.state === 'ready' && leg.callId
                  ? `通话中 · WebRTC: ${leg.callId.slice(-8)}`
                  : leg.state === 'connecting'
                    ? '正在接通...'
                    : '通话中'
              : phase === 'incoming' || phase === 'outbound_ringing'
                ? '振铃中 · 无法切换状态'
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
              WebRTC 错误：{formatWebRtcDeviceError(leg.error)}
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
          <CallDeviceSelector />
          {canExecuteOutboundTasks && (
            <Link
              href="/workspace/call?view=outbound-tasks"
              aria-current={showingOutboundTasks ? 'page' : undefined}
              className={cn(
                'mt-3 flex h-9 items-center justify-center gap-2 rounded-md border border-border text-sm font-medium transition-colors',
                showingOutboundTasks ? 'bg-muted/50' : 'bg-white hover:bg-muted/50',
              )}
            >
              <IconClipboardList size={16} />
              {t('ws.outboundExec.entry', locale)}
            </Link>
          )}
          {canPersonalAutoOutbound && (
            <Link
              href="/workspace/call?view=personal-auto-outbound"
              aria-current={showingPersonalAutoOutbound ? 'page' : undefined}
              className={cn(
                'mt-2 flex h-9 items-center justify-center gap-2 rounded-md border border-border text-sm font-medium transition-colors',
                showingPersonalAutoOutbound ? 'bg-muted/50' : 'bg-white hover:bg-muted/50',
              )}
            >
              <IconPhoneOutgoing size={16} />
              {t('personalAuto.title', locale)}
            </Link>
          )}
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-2 py-2">
          <h3 className="px-2 text-xs font-semibold text-foreground/70">最近通话（近 24 小时）</h3>
          <div className="min-h-0 flex-1 overflow-y-auto">
          {(records?.items ?? []).length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">近 24 小时暂无通话记录</p>
          ) : (
            (records?.items ?? []).map((r) => {
              const isCurrentLive =
                !!incoming?.call_id &&
                r.call_id === incoming.call_id &&
                (phase === 'on_call' ||
                  phase === 'incoming' ||
                  phase === 'wrap_up' ||
                  phase === 'outbound_ringing')
              const active =
                !showingOutboundTasks &&
                !showingPersonalAutoOutbound &&
                (selectedRecordId === r.id || (selectedRecordId == null && isCurrentLive))
              return (
                <button
                  type="button"
                  key={r.id}
                  onClick={() => {
                    // Clicking the live call should restore the live panel
                    // (incl. realtime transcript), not HistoryDetail.
                    setSelectedRecordId(isCurrentLive ? null : r.id)
                    applyWorkspaceRoute({ type: 'select-recent', isCurrentLive })
                  }}
                  className={`my-1 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm outline-none transition ${
                    active ? 'bg-muted' : 'hover:bg-muted'
                  }`}
                >
                  {r.direction === 'inbound' ? (
                    <IconPhoneIncoming size={14} className="text-blue-500" />
                  ) : (
                    <IconPhoneOutgoing size={14} className="text-green-500" />
                  )}
                  <span className="min-w-0 flex-1 truncate">
                    {r.user_name || callRecordCustomerNumber(r) || '未知号码'}
                    {r.user_name && callRecordCustomerNumber(r) ? (
                      <span className="ml-1 text-xs text-muted-foreground">
                        {callRecordCustomerNumber(r)}
                      </span>
                    ) : null}
                  </span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                    {formatRelative(r.started_at)}
                  </span>
                </button>
              )
            })
          )}
          </div>
          {(records?.pages ?? 0) > 1 && (
            <div className="mt-2 flex shrink-0 items-center justify-between gap-2 border-t border-border px-2 pt-2">
              <button
                type="button"
                disabled={recordsPage <= 1}
                onClick={() => setRecordsPage(Math.max(1, recordsPage - 1))}
                className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted disabled:opacity-40"
              >
                上一页
              </button>
              <span className="text-[11px] text-muted-foreground">
                {recordsPage}/{records?.pages ?? 1}
              </span>
              <button
                type="button"
                disabled={recordsPage >= (records?.pages ?? 1)}
                onClick={() => setRecordsPage(recordsPage + 1)}
                className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted disabled:opacity-40"
              >
                下一页
              </button>
            </div>
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
                  ? onCallStripClass
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
          {phase === 'idle' && canDialOutbound && (
            <DialBar
              value={draftDialNumber}
              disabled={mic.state === 'checking' || !hasUsableDevice || dialBlockedOffline}
              statusHint={
                !hasUsableDevice
                  ? '请先选择可用呼叫设备'
                  : dialBlockedOffline
                    ? '请先将客服状态切换为就绪'
                    : leg.state === 'ready'
                      ? '等待来电'
                      : undefined
              }
              smsButton={
                showSmsEntry ? (
                  <button
                    type="button"
                    disabled={!isCnMobileNumber(draftDialNumber)}
                    title={
                      isCnMobileNumber(draftDialNumber)
                        ? t('sms.send.entry', locale)
                        : t('sms.send.disabledNoNumber', locale)
                    }
                    aria-label={t('sms.send.entry', locale)}
                    onClick={() =>
                      setSmsDialog({
                        phone: draftDialNumber.trim(),
                        phoneReadonly: false,
                        callId: null,
                      })
                    }
                    className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-border bg-background text-foreground shadow-sm transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <IconMessage size={18} />
                  </button>
                ) : undefined
              }
              onDialNumberChange={(number) => {
                setDraftDialNumber(number)
                setWorkspaceAnchor((current) => nextAnchorAfterDialNumberChange(current, number))
              }}
              onOutboundNumberChange={(id, phoneNumber) => {
                setDraftOutboundId(id)
                setDraftOutboundNumber(phoneNumber)
              }}
              onDialStarted={(info) => {
                applyWorkspaceRoute({
                  type: 'dial-started',
                  destination: info.destination,
                  callId: info.callId,
                })
                void handleDialStarted(info)
              }}
            />
          )}
          {phase === 'incoming' && incoming && (
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-full bg-amber-100">
                  <IconPhoneIncoming size={16} className="animate-pulse text-amber-700" />
                </span>
                <span className="font-bold text-amber-800">
                  {incoming.call_type === 'internal_consult'
                    ? '咨询请求'
                    : incoming.call_type === 'internal_transfer'
                      ? '转接请求'
                      : incoming.call_type === 'internal_conference'
                        ? '会议邀请'
                        : autoAccepting
                          ? t('ws.autoOutbound.agent.connecting', locale)
                          : '来电'}
                </span>
              </div>
              {incoming.call_type === 'internal_consult' ||
              incoming.call_type === 'internal_transfer' ||
              incoming.call_type === 'internal_conference' ? (
                <Field
                  label={
                    incoming.call_type === 'internal_transfer'
                      ? '转接自'
                      : incoming.call_type === 'internal_conference'
                        ? '邀请自'
                        : '咨询自'
                  }
                  value={incoming.from || '同事'}
                  strong
                />
              ) : (
                <>
                  <Field label="通话类型" value={callTypeInboundLabel} />
                  <Field
                    label="用户号码"
                    value={isAutoOutbound ? autoOutboundUserNumber : (incoming.from || '未知号码')}
                    strong
                  />
                  <Field
                    label="服务号码"
                    value={isAutoOutbound ? (incoming.from || '—') : (incoming.to || '—')}
                  />
                </>
              )}
              <Field
                label="响铃时长"
                value={formatDuration(callStart ? now - callStart : 0)}
                strong
                color="text-amber-700"
              />
              <div className="ml-auto flex items-center gap-2">
                {incoming.device_type === 'sip_phone' && (
                  <span className="whitespace-nowrap text-xs text-muted-foreground">
                    话机响铃中
                  </span>
                )}
                {autoAccepting ? (
                  <span className="whitespace-nowrap text-xs text-muted-foreground">
                    {leg.state === 'connecting'
                      ? t('ws.autoOutbound.agent.connecting', locale)
                      : t('ws.autoOutbound.agent.autoAnswer', locale)}
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={reject}
                      disabled={leg.state === 'connecting'}
                      className="rounded-full bg-red-500 p-2.5 text-white disabled:opacity-50"
                      title="拒接"
                    >
                      <IconPhoneOff size={16} />
                    </button>
                    {/* A desk phone is answered by lifting the handset; the browser
                        has no leg to accept, so an 接听 button here would do
                        nothing. Rejecting still works — that runs server-side. */}
                    {incoming.device_type !== 'sip_phone' && (
                      <button
                        type="button"
                        onClick={accept}
                        disabled={leg.state === 'connecting'}
                        title={leg.state === 'connecting' ? '正在接通...' : '接听'}
                        className="rounded-full bg-green-500 p-2.5 text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <IconPhone size={16} />
                      </button>
                    )}
                  </>
                )}
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
              <div className="ml-auto flex items-center gap-2">
                {/* The handset rings first and then carries the call; without
                    this the browser looks like it should be making the sound. */}
                {currentDevice?.device_type === 'sip_phone' && (
                  <span className="whitespace-nowrap text-xs text-muted-foreground">
                    正在呼叫你的话机
                    {currentDevice.extension_number
                      ? ` ${currentDevice.extension_number}`
                      : ''}{' '}
                    · 接通后声音在话机上
                  </span>
                )}
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
            <AgentCallBar
              onSendSms={
                showSmsEntry
                  ? () =>
                      setSmsDialog({
                        phone: callCustomerNumber ?? '',
                        phoneReadonly: true,
                        callId: incoming.call_id ?? null,
                      })
                  : undefined
              }
              smsDisabledReason={showSmsEntry ? callSmsDisabledReason : null}
            />
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
              {showSmsEntry && (
                <button
                  type="button"
                  disabled={!!callSmsDisabledReason}
                  title={callSmsDisabledReason ?? t('sms.send.entry', locale)}
                  aria-label={t('sms.send.entry', locale)}
                  onClick={() =>
                    setSmsDialog({
                      phone: callCustomerNumber ?? '',
                      phoneReadonly: true,
                      callId: incoming?.call_id ?? null,
                    })
                  }
                  className="ml-auto grid h-10 w-10 place-items-center rounded-lg border border-border bg-background text-foreground shadow-sm transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <IconMessage size={16} />
                </button>
              )}
              {wrapUpUntil != null && (
                <span className={`font-mono text-sm tabular-nums text-muted-foreground${showSmsEntry ? '' : ' ml-auto'}`}>
                  {t('cs.wrapupRemaining', locale, {
                    time: formatDuration(Math.max(0, wrapUpUntil - now)),
                  })}
                </span>
              )}
              <button type="button" onClick={completeWrapUp} className={showSmsEntry || wrapUpUntil != null ? 'rounded-full bg-green-500 p-2.5 text-white' : 'ml-auto rounded-full bg-green-500 p-2.5 text-white'}>
                <IconCheck size={16} />
              </button>
            </div>
          )}
        </div>

        {/* Aux info area */}
        {showingPersonalAutoOutbound ? (
          <div className="min-h-0 flex-1">
            <PersonalAutoOutboundView
              initialTaskId={requestedTaskId}
              agentReady={currentStatus === 'ready'}
              deviceAvailable={hasUsableDevice}
              incoming={incoming}
              phase={phase}
              onWrapupSubmitted={completeWrapUp}
            />
          </div>
        ) : isPersonalAutoOutboundIncoming(incoming) &&
          (phase === 'incoming' || phase === 'on_call' || phase === 'wrap_up') ? (
          <div className="min-h-0 flex-1 overflow-y-auto bg-background p-6">
            <PersonalAutoOutboundTaskPop
              incoming={incoming}
              phase={phase}
              onSubmitted={completeWrapUp}
            />
          </div>
        ) : (
          <>
          {showingOutboundTasks && (
            <div className={screenPopOverride ? 'hidden' : 'min-h-0 flex-1'}>
              <MyOutboundTargetsView
                taskId={requestedTaskId}
                onStartCall={startTaskCall}
                onOpenScreenPop={openScreenPopFromTask}
              />
            </div>
          )}
          {(!showingOutboundTasks || screenPopOverride) && (
          <div className={`flex min-h-0 flex-1 flex-col ${visiblePopTab === 'system' && showEmptyCallState ? 'bg-white' : 'bg-muted p-5'}`}>
          {screenPopOverride && showingOutboundTasks && (
            <div className={visiblePopTab === 'system' && showEmptyCallState ? 'shrink-0 px-5 pt-5 pb-4' : 'shrink-0 pb-4'}>
              <button
                type="button"
                onClick={() => setScreenPopOverride(false)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-primary shadow-sm hover:bg-muted"
              >
                <IconArrowLeft size={13} />
                {t('ws.outboundExec.screenPop.back', locale)}
              </button>
            </div>
          )}
          {showPopTabs && (
            <div className={`flex shrink-0 ${visiblePopTab === 'system' && showEmptyCallState ? 'px-5 pt-5 pb-4' : 'pb-4'}`}>
              <div className="flex rounded-md border border-border bg-background p-0.5">
                <button
                  type="button"
                  onClick={() => setPopTab('system')}
                  className={cn(
                    'rounded px-3 py-1.5 text-xs font-medium transition-colors',
                    visiblePopTab === 'system'
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t('ep.ws.systemPop', locale)}
                </button>
                {embeddedPages.map((page) => (
                  <button
                    key={page.id}
                    type="button"
                    onClick={() => setPopTab(`embedded:${page.id}`)}
                    className={cn(
                      'max-w-[160px] truncate rounded px-3 py-1.5 text-xs font-medium transition-colors',
                      visiblePopTab === `embedded:${page.id}`
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {page.name}
                  </button>
                ))}
              </div>
            </div>
          )}
          {visiblePopTab !== 'system' ? (
            <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-white">
              {embeddedPages
                .filter((page) => mountedEmbeddedIds.has(page.id))
                .map((page) => (
                  <EmbeddedPagePanel
                    key={page.id}
                    page={page}
                    context={embeddedContext}
                    hidden={visiblePopTab !== `embedded:${page.id}`}
                  />
                ))}
            </section>
          ) : showEmptyCallState ? (
            <div className="min-h-0 flex-1 overflow-y-auto">
              <CallWorkspaceEmptyState />
            </div>
          ) : (
            <div className="grid min-h-0 w-full flex-1 gap-4 xl:grid-cols-3 xl:items-stretch">
              {/* Full column height; 实时对话 flex-grows to the bottom. */}
              <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5 xl:h-full">
                <div className="mb-3 flex shrink-0 items-center justify-between gap-2 border-b border-border pb-2">
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <IconPhone size={16} className="text-muted-foreground" />
                    通话信息
                  </h3>
                  {viewingHistoryDuringLiveCall && (
                    <button
                      type="button"
                      onClick={() => setSelectedRecordId(null)}
                      className="shrink-0 text-xs font-medium text-primary underline-offset-2 hover:underline"
                    >
                      返回当前通话
                    </button>
                  )}
                </div>
                {isViewingHistory ? (
                  <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                    <HistoryDetail recordId={selectedRecord!.public_id} />
                  </div>
                ) : (
                  <>
                    <div className="shrink-0">
                      {screenPopIncoming?.direction === 'outbound' ? (
                        <dl className="grid grid-cols-2 gap-y-2 text-sm">
                          <Dt>通话类型</Dt><Dd>呼出</Dd>
                          <Dt>外呼号码</Dt><Dd>{screenPopIncoming?.from || '—'}</Dd>
                          <Dt>被叫号码</Dt><Dd>{screenPopIncoming?.to || '—'}</Dd>
                          <Dt>通话时长</Dt><Dd>{screenPopDurationLabel}</Dd>
                          <Dt>发起时间</Dt>
                          <Dd>{screenPopCallStart ? new Date(screenPopCallStart).toLocaleTimeString() : '—'}</Dd>
                          <Dt>通话 ID</Dt>
                          <Dd>
                            {screenPopIncoming?.call_id ? (
                              <code className="font-mono text-xs">{screenPopIncoming.call_id}</code>
                            ) : (
                              '—'
                            )}
                          </Dd>
                        </dl>
                      ) : screenPopIncoming?.call_type === 'internal_consult' ||
                        screenPopIncoming?.call_type === 'internal_transfer' ||
                        screenPopIncoming?.call_type === 'internal_conference' ? (
                        <dl className="grid grid-cols-2 gap-y-2 text-sm">
                          <Dt>通话类型</Dt>
                          <Dd>
                            {screenPopIncoming.call_type === 'internal_transfer'
                              ? '转接'
                              : screenPopIncoming.call_type === 'internal_conference'
                                ? '会议'
                                : '咨询'}
                          </Dd>
                          <Dt>
                            {screenPopIncoming.call_type === 'internal_transfer'
                              ? '转接自'
                              : screenPopIncoming.call_type === 'internal_conference'
                                ? '邀请自'
                                : '咨询自'}
                          </Dt>
                          <Dd>{screenPopIncoming.from || '同事'}</Dd>
                          <Dt>用户号码</Dt>
                          <Dd>{screenPopIncoming.customer_from || '未知号码'}</Dd>
                          <Dt>服务号码</Dt>
                          <Dd>{screenPopIncoming.customer_to || '—'}</Dd>
                          <Dt>通话时长</Dt><Dd>{screenPopDurationLabel}</Dd>
                          <Dt>来电时间</Dt>
                          <Dd>{screenPopCallStart ? new Date(screenPopCallStart).toLocaleTimeString() : '—'}</Dd>
                          <Dt>客户通话 ID</Dt>
                          <Dd>
                            {screenPopIncoming.source_call_id ? (
                              <code className="font-mono text-xs">{screenPopIncoming.source_call_id}</code>
                            ) : (
                              '—'
                            )}
                          </Dd>
                        </dl>
                      ) : (
                        <dl className="grid grid-cols-2 gap-y-2 text-sm">
                          <Dt>通话类型</Dt><Dd>{callTypeInboundLabel}</Dd>
                          <Dt>用户号码</Dt>
                          <Dd>
                            {isAutoOutbound
                              ? autoOutboundUserNumber
                              : (screenPopIncoming?.from || '未知号码')}
                          </Dd>
                          <Dt>服务号码</Dt>
                          <Dd>
                            {isAutoOutbound
                              ? (screenPopIncoming?.from || '—')
                              : (screenPopIncoming?.to || '—')}
                          </Dd>
                          <Dt>通话时长</Dt><Dd>{screenPopDurationLabel}</Dd>
                          <Dt>来电时间</Dt>
                          <Dd>{screenPopCallStart ? new Date(screenPopCallStart).toLocaleTimeString() : '—'}</Dd>
                          <Dt>通话 ID</Dt>
                          <Dd>
                            {screenPopIncoming?.call_id ? (
                              <code className="font-mono text-xs">{screenPopIncoming.call_id}</code>
                            ) : (
                              '—'
                            )}
                          </Dd>
                        </dl>
                      )}
                    </div>
                    {screenPopIncoming?.call_id &&
                      (phase === 'on_call' || phase === 'wrap_up' || phase === 'idle') && (
                        <CallTranscriptPanel
                          callId={screenPopIncoming.call_id}
                          live={phase === 'on_call'}
                          fallbackRecordId={currentRecord?.public_id}
                          sourceCallId={screenPopIncoming.source_call_id}
                        />
                      )}
                  </>
                )}
              </section>

              <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5 xl:h-full">
                <div className="min-h-0 flex-1 overflow-y-auto">
                <CallUserInfoPanel
                  recordId={callRecordForTicket?.public_id}
                  fallbackNumber={screenPopNumber}
                  userRef={
                    callSummaryRecordId
                      ? null
                      : (screenPopIncoming?.user_public_id ??
                        screenPopIncoming?.user_id ??
                        null)
                  }
                />
                </div>
              </section>

              <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-white p-5 xl:h-full">
                <div className="min-h-0 flex-1 overflow-y-auto">
                {(callRecordForTicket || showAutoOutboundTab || showPersonalAutoOutboundTab) && (
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
                      {showAutoOutboundTab && (
                        <button
                          type="button"
                          onClick={() => setCallSummaryTab('auto_outbound')}
                          className={cn(
                            'rounded px-2 py-1 text-xs font-medium transition-colors',
                            callSummaryTab === 'auto_outbound'
                              ? 'bg-white text-foreground shadow-sm'
                              : 'text-muted-foreground hover:text-foreground',
                          )}
                        >
                          {t('ws.autoOutbound.agent.tab', locale)}
                        </button>
                      )}
                      {showPersonalAutoOutboundTab && (
                        <button
                          type="button"
                          onClick={() => setCallSummaryTab('personal_auto_outbound')}
                          className={cn(
                            'rounded px-2 py-1 text-xs font-medium transition-colors',
                            callSummaryTab === 'personal_auto_outbound'
                              ? 'bg-white text-foreground shadow-sm'
                              : 'text-muted-foreground hover:text-foreground',
                          )}
                        >
                          {t('personalAuto.businessTab', locale)}
                        </button>
                      )}
                    </div>
                  </div>
                )}
                {showPersonalAutoOutboundTab && callSummaryTab === 'personal_auto_outbound' ? (
                  <PersonalAutoOutboundBusinessPanel
                    incoming={screenPopIncoming}
                    onSubmitted={completeWrapUp}
                  />
                ) : showAutoOutboundTab && callSummaryTab === 'auto_outbound' ? (
                  <AutoOutboundBusinessPanel
                    incoming={autoOutboundBusinessIncoming}
                    phase={phase}
                    callRecordId={currentRecord?.id ?? callSummaryRecordId}
                    onSubmitted={() => {
                      if (phase === 'wrap_up' && !selectedRecord) completeWrapUp()
                    }}
                  />
                ) : canCreateTicket && callSummaryTab === 'ticket' && callRecordForTicket ? (
                  <CallTicketDraftPanel
                    key={callRecordForTicket.id}
                    callRecord={callRecordForTicket}
                    onClose={() => setCallSummaryTab('summary')}
                    onNotice={(type, text, payload) => {
                      if (type === 'success') {
                        const ticket = payload?.ticket
                        if (ticket) {
                          const toastId = toast.success(
                            <button
                              type="button"
                              onClick={() => {
                                toast.dismiss(toastId)
                                router.push(`/workspace/tickets/${ticket.id}?from=list`)
                              }}
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
                </div>
              </section>
            </div>
          )}
          </div>
          )}
          </>
        )}
      </main>

      <SendSmsDialog
        open={smsDialog !== null}
        onOpenChange={(open) => {
          if (!open) setSmsDialog(null)
        }}
        defaultPhone={smsDialog?.phone ?? ''}
        phoneReadonly={smsDialog?.phoneReadonly ?? false}
        callId={smsDialog?.callId}
        templates={workspaceSmsTemplates}
      />
      </div>
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

function CallCenterDisabledBanner({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-amber-800">
      <IconPhoneOff size={16} className="shrink-0" />
      <p className="min-w-0 flex-1 text-xs">
        <span className="font-semibold">暂未启用语音内核</span>
        <span className="ml-1.5 text-amber-700/90">
          当前部署尚未接入语音通话服务，外呼与呼入功能暂不可用，如需开通请联系系统管理员。
        </span>
      </p>
      <button
        type="button"
        onClick={onClose}
        title="关闭提示"
        className="shrink-0 rounded p-1 text-amber-700/70 transition-colors hover:bg-amber-100 hover:text-amber-900"
      >
        <IconX size={15} />
      </button>
    </div>
  )
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

function HistoryDetail({ recordId }: { recordId: string }) {
  const { data: record, isLoading, refetch } = useCallRecord(recordId)
  const playableRecording = selectDisplayRecording(record?.recordings)

  // Recording file may land a few seconds after hangup.
  useEffect(() => {
    if (!record || playableRecording || record.lifecycle_status !== 'ended') return
    const endedAt = record.ended_at ? new Date(record.ended_at).getTime() : 0
    if (!endedAt || Date.now() - endedAt > 60_000) return
    const timer = window.setInterval(() => {
      void refetch()
    }, 3000)
    return () => window.clearInterval(timer)
  }, [playableRecording, record, refetch])

  if (isLoading || !record) {
    return <p className="py-4 text-sm text-muted-foreground">加载中...</p>
  }

  const started = record.started_at ? new Date(record.started_at) : null
  const ended = record.ended_at ? new Date(record.ended_at) : null
  const customerNumber = callRecordCustomerNumber(record)
  const serviceNumber = callRecordServiceNumber(record)
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <section className="shrink-0">
        <h4 className="mb-2 text-xs font-semibold text-foreground/70">通话录音</h4>
        {playableRecording?.access_url ? (
          <div className="flex items-center gap-2">
            <audio src={playableRecording.access_url} controls className="min-w-0 flex-1" />
            <a
              href={playableRecording.access_url}
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
      <dl className="grid shrink-0 grid-cols-2 gap-y-2 text-sm">
        <Dt>通话类型</Dt><Dd>{record.direction === 'inbound' ? '呼入' : '呼出'}</Dd>
        <Dt>用户号码</Dt><Dd>{customerNumber || '—'}</Dd>
        <Dt>服务号码</Dt><Dd>{serviceNumber || '—'}</Dd>
        <Dt>通话时长</Dt><Dd>{formatDuration(record.customer_agent_talk_duration_ms)}</Dd>
        <Dt>客户响铃时长</Dt>
        <Dd>{formatDuration(record.customer_ring_duration_ms)}</Dd>
        <Dt>来电时间</Dt><Dd>{started ? started.toLocaleString() : '—'}</Dd>
        <Dt>结束时间</Dt><Dd>{ended ? ended.toLocaleString() : '—'}</Dd>
        <Dt>接听坐席</Dt><Dd>{record.last_serving_agent_name || '—'}</Dd>
        <Dt>状态</Dt><Dd>{formatCallRecordState(record.lifecycle_status)}</Dd>
        <Dt>挂断原因</Dt><Dd>{formatHangupReason(record.hangup_reason_code) || '—'}</Dd>
        <Dt>机器人接待</Dt><Dd>{record.actual_reception_type === 'bot' || record.actual_reception_type === 'bot_agent' ? '是' : '—'}</Dd>
        <Dt>通话 ID</Dt>
        <Dd><code className="font-mono text-xs">{record.call_id}</code></Dd>
      </dl>
      <CallTranscriptHistory recordId={record.public_id} />
    </div>
  )
}
