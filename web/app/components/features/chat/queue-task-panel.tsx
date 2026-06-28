'use client'

import { useEffect, useMemo, useRef, useState, type ClipboardEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import {
  IconCheck,
  IconChevronDown,
  IconClock,
  IconLoader2,
  IconRefresh,
  IconSearch,
  IconSend,
  IconUserCheck,
  IconUsers,
} from '@tabler/icons-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { getWorkspaceHumanAgentLabel } from '@/lib/workspace-agent-display'
import {
  useAssignableAgents,
  useAssignAndSendQueueTaskToSelf,
  useAssignQueueTaskToAgent,
  useAssignQueueTaskToSelf,
  useQueueTask,
} from '@/service/use-queue-workspace'
import type { AgentStatus, Message } from '@/models/conversation'
import type {
  QueueAssignableAgent,
  QueueAssignmentWorkspaceResponse,
  QueueWorkspaceQueueBrief,
  QueueWorkspaceTask,
} from '@/models/queue-workspace'

type QueueFilter = {
  queueType: string | null
  queueId: number | null
}

type QueueTaskListSidebarProps = {
  items: QueueWorkspaceTask[]
  visibleQueues: QueueWorkspaceQueueBrief[]
  itemsUpdatedAt: number
  selectedId: number | null
  loading: boolean
  queueFilter: QueueFilter
  onQueueFilterChange: (filter: QueueFilter) => void
  onSelect: (id: number) => void
  onRefresh: () => void
}

type QueueTaskPanelProps = {
  selectedId: number | null
  agentStatus: AgentStatus | null
  onAssigned: (
    response: QueueAssignmentWorkspaceResponse,
    options?: { openConversation?: boolean; messageSent?: boolean },
  ) => void
}

const QUICK_REPLY_MAX_LENGTH = 5000

const STATUS_COLOR: Record<string, string> = {
  online: '#22C55E',
  busy: '#F59E0B',
  offline: '#9CA3AF',
}

function formatWait(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function getLiveWaitSeconds(baseSeconds: number, updatedAt: number, now: number | null): number {
  const base = Number.isFinite(baseSeconds) ? Math.max(0, Math.floor(baseSeconds)) : 0
  if (!now || updatedAt <= 0) return base
  return base + Math.max(0, Math.floor((now - updatedAt) / 1000))
}

function useLiveNow(active: boolean, resetKey: number): number | null {
  const [now, setNow] = useState<number | null>(null)

  useEffect(() => {
    if (!active) {
      setNow(null)
      return
    }

    const update = () => {
      if (document.visibilityState !== 'hidden') setNow(Date.now())
    }

    update()
    const intervalId = window.setInterval(update, 1000)
    document.addEventListener('visibilitychange', update)

    return () => {
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', update)
    }
  }, [active, resetKey])

  return now
}

function formatTime(value: string | null): string {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function sourceLabel(value: string, locale: Locale): string {
  if (value === 'open_agent_handoff' || value === 'bot_handoff') {
    return locale === 'zh' ? '转人工' : 'Handoff'
  }
  if (value === 'visitor_waiting') {
    return locale === 'zh' ? '新会话' : 'New'
  }
  return locale === 'zh' ? '手动入队' : 'Manual'
}

function messagePreview(message: Message, locale: Locale): string {
  if (message.content_type === 'text' || message.content_type === 'system' || message.content_type === 'internal_note') {
    return message.content
  }
  if (message.content_type === 'image') return locale === 'zh' ? '[图片]' : '[Image]'
  if (message.content_type === 'file') return locale === 'zh' ? '[附件]' : '[File]'
  return `[${message.content_type}]`
}

function displayAgentName(agent: QueueAssignableAgent): string {
  return agent.display_name || agent.name || `#${agent.id}`
}

function queueLabel(queue: QueueWorkspaceQueueBrief): string {
  return queue.name || `#${queue.queue_id}`
}

export function QueueTaskListSidebar({
  items,
  visibleQueues,
  itemsUpdatedAt,
  selectedId,
  loading,
  queueFilter,
  onQueueFilterChange,
  onSelect,
  onRefresh,
}: QueueTaskListSidebarProps) {
  const { locale } = useLocaleStore()
  const [queueMenuOpen, setQueueMenuOpen] = useState(false)
  const queueMenuRef = useRef<HTMLDivElement>(null)

  const queueValue = queueFilter.queueType && queueFilter.queueId
    ? `${queueFilter.queueType}:${queueFilter.queueId}`
    : ''
  const selectedQueue = queueValue
    ? visibleQueues.find((queue) => `${queue.queue_type}:${queue.queue_id}` === queueValue) ?? null
    : null
  const totalQueueCount = visibleQueues.reduce((sum, queue) => sum + queue.waiting_count, 0)
  const selectedQueueLabel = selectedQueue ? queueLabel(selectedQueue) : t('ws.chat.queueAllVisible', locale)
  const selectedQueueCount = selectedQueue ? selectedQueue.waiting_count : totalQueueCount
  const liveNow = useLiveNow(items.length > 0 && itemsUpdatedAt > 0, itemsUpdatedAt)

  useEffect(() => {
    if (!queueMenuOpen) return
    const handlePointerDown = (event: MouseEvent) => {
      if (!queueMenuRef.current?.contains(event.target as Node)) setQueueMenuOpen(false)
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setQueueMenuOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [queueMenuOpen])

  const selectQueue = (filter: QueueFilter) => {
    onQueueFilterChange(filter)
    setQueueMenuOpen(false)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-[#E5E5E5] px-2 py-2">
        <div className="flex items-center gap-2">
          <div ref={queueMenuRef} className="relative min-w-0 flex-1">
            <button
              type="button"
              onClick={() => setQueueMenuOpen((open) => !open)}
              className="flex h-8 w-full min-w-0 items-center gap-1.5 rounded-md border border-[#E5E5E5] bg-white px-2 text-left text-[12px] text-[#1a1a1a] outline-none transition-colors hover:bg-[#F8F8F8]"
              aria-haspopup="listbox"
              aria-expanded={queueMenuOpen}
            >
              <span className="min-w-0 flex-1 truncate">{selectedQueueLabel}</span>
              <span className="shrink-0 text-[#999999]">{selectedQueueCount}</span>
              <IconChevronDown
                size={14}
                stroke={1.7}
                className={cn('shrink-0 text-[#999999] transition-transform', queueMenuOpen && 'rotate-180')}
              />
            </button>
            {queueMenuOpen && (
              <div
                role="listbox"
                className="absolute left-0 top-full z-30 mt-1 max-h-64 w-full min-w-[220px] overflow-y-auto rounded-xl border border-[#E5E5E5] bg-white p-1 shadow-lg"
              >
                <QueueFilterMenuItem
                  active={!queueValue}
                  label={t('ws.chat.queueAllVisible', locale)}
                  count={totalQueueCount}
                  onClick={() => selectQueue({ queueType: null, queueId: null })}
                />
                {visibleQueues.map((queue) => {
                  const value = `${queue.queue_type}:${queue.queue_id}`
                  return (
                    <QueueFilterMenuItem
                      key={value}
                      active={queueValue === value}
                      label={queueLabel(queue)}
                      count={queue.waiting_count}
                      onClick={() => selectQueue({ queueType: queue.queue_type, queueId: queue.queue_id })}
                    />
                  )
                })}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[#E5E5E5] bg-white text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1a1a1a]"
            aria-label={t('ws.chat.queueRefresh', locale)}
            title={t('ws.chat.queueRefresh', locale)}
          >
            <IconRefresh size={16} stroke={1.7} className={cn(loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-1">
        {loading && items.length === 0 ? (
          <div className="space-y-2 py-2">
            {[0, 1, 2].map((item) => (
              <div key={item} className="h-[86px] animate-pulse rounded-[18px] bg-white/70" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-full items-center justify-center px-4 text-center text-sm text-[#737373]">
            {t('ws.chat.queueEmpty', locale)}
          </div>
        ) : (
          items.map((item) => {
            const selected = selectedId === item.id
            const waitSeconds = getLiveWaitSeconds(item.wait_seconds, itemsUpdatedAt, liveNow)
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelect(item.id)}
                className={cn(
                  'mb-1 flex min-h-[88px] w-full gap-3 rounded-[18px] border px-3 py-2 text-left transition-colors',
                  selected ? 'border-[#E0E0E0] bg-white shadow-sm' : 'border-transparent hover:bg-white/70',
                )}
              >
                <div
                  className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
                  style={{ backgroundColor: item.visitor?.avatar_color || '#4A8C5C' }}
                >
                  {(item.visitor?.name || '访').charAt(0)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-semibold text-[#1a1a1a]">
                      {item.visitor?.name || `${t('ws.chat.queueVisitor', locale)} #${item.conversation_id || item.id}`}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-[#737373]">
                    <span className="truncate">{item.queue.name || t('ws.chat.queueUnknown', locale)}</span>
                    <span className="shrink-0">·</span>
                    <span className="shrink-0">{sourceLabel(item.source_type, locale)}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 text-[11px] text-[#999999]">
                    <IconClock size={12} stroke={1.7} />
                    <span>{t('ws.chat.queueWaited', locale, { time: formatWait(waitSeconds) })}</span>
                    {item.position_in_priority ? (
                      <span>#{item.position_in_priority}</span>
                    ) : null}
                  </div>
                  <div className="mt-1 truncate text-[12px] text-[#737373]">
                    {item.last_message_preview || t('ws.chat.queueSystemPreview', locale)}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}

function QueueFilterMenuItem({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean
  label: string
  count: number
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'flex h-9 w-full items-center gap-2 rounded-lg px-2 text-left text-[12px] transition-colors',
        'text-[#1a1a1a] hover:bg-[#F5F5F5]',
      )}
    >
      <IconCheck size={14} stroke={1.8} className={cn('shrink-0', active ? 'opacity-100' : 'opacity-0')} />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="shrink-0 text-[#999999]">{count}</span>
    </button>
  )
}

export function QueueTaskPanel({ selectedId, agentStatus, onAssigned }: QueueTaskPanelProps) {
  const { locale } = useLocaleStore()
  const { data, isLoading, refetch, dataUpdatedAt } = useQueueTask(selectedId)
  const assignSelf = useAssignQueueTaskToSelf()
  const assignAgent = useAssignQueueTaskToAgent()
  const assignAndSend = useAssignAndSendQueueTaskToSelf()
  const [toast, setToast] = useState<string | null>(null)
  const [assignOpen, setAssignOpen] = useState(false)
  const [capacityConfirmOpen, setCapacityConfirmOpen] = useState(false)
  const [pendingQuickReply, setPendingQuickReply] = useState('')
  const [pendingQuickReplyTaskId, setPendingQuickReplyTaskId] = useState<number | null>(null)
  const [quickReplyDrafts, setQuickReplyDrafts] = useState<Record<number, string>>({})
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const liveNow = useLiveNow(Boolean(data && dataUpdatedAt > 0), dataUpdatedAt)
  const liveWaitSeconds = data ? getLiveWaitSeconds(data.wait_seconds, dataUpdatedAt, liveNow) : 0
  const quickReplyDraft = selectedId ? quickReplyDrafts[selectedId] ?? '' : ''
  const quickReplyLength = quickReplyDraft.length
  const isOffline = agentStatus?.status === 'offline'
  const capacityReached = Boolean(
    agentStatus
    && agentStatus.max_concurrent > 0
    && agentStatus.current_count >= agentStatus.max_concurrent,
  )

  useEffect(() => () => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
  }, [])

  const showToast = (text: string) => {
    setToast(text)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(null), 2500)
  }

  const handleAssignSelf = async () => {
    if (!selectedId) return
    if (agentStatus?.status === 'offline') {
      showToast(t('ws.chat.queueAssignSelfOffline', locale))
      return
    }
    try {
      const response = await assignSelf.mutateAsync({ taskId: selectedId })
      showToast(t('ws.chat.queueAssignedToMe', locale))
      onAssigned(response)
    } catch {
      showToast(t('ws.chat.queueAssignFailed', locale))
      void refetch()
    }
  }

  const updateQuickReplyDraft = (taskId: number, value: string) => {
    setQuickReplyDrafts((prev) => ({ ...prev, [taskId]: value }))
  }

  const submitQuickReply = async (taskId: number, content: string) => {
    try {
      const response = await assignAndSend.mutateAsync({ taskId, content })
      if (response.message_sent) {
        setQuickReplyDrafts((prev) => {
          const next = { ...prev }
          delete next[taskId]
          return next
        })
      } else {
        updateQuickReplyDraft(taskId, content)
      }
      onAssigned(response, { openConversation: true, messageSent: response.message_sent })
    } catch {
      showToast(t('ws.chat.queueQuickSendStateChanged', locale))
      void refetch()
    }
  }

  const handleQuickReplySend = () => {
    if (!selectedId) return
    if (isOffline) {
      showToast(t('ws.chat.queueQuickReplyOffline', locale))
      return
    }
    const content = quickReplyDraft.trim()
    if (!content) {
      showToast(t('ws.chat.queueQuickReplyEmpty', locale))
      return
    }
    if (content.length > QUICK_REPLY_MAX_LENGTH) {
      showToast(t('ws.chat.queueQuickReplyTooLong', locale))
      return
    }
    const taskId = selectedId
    if (capacityReached) {
      setPendingQuickReply(content)
      setPendingQuickReplyTaskId(taskId)
      setCapacityConfirmOpen(true)
      return
    }
    void submitQuickReply(taskId, content)
  }

  const handleQuickReplyKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    handleQuickReplySend()
  }

  const handleQuickReplyPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    if (event.clipboardData.files.length === 0) return
    event.preventDefault()
    showToast(t('ws.chat.queueQuickReplyPasteAttachment', locale))
  }

  if (!selectedId) {
    return <QueueEmptyState text={t('ws.chat.queueSelectHint', locale)} />
  }

  if (isLoading) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 items-center justify-center bg-white">
        <IconLoader2 size={22} className="animate-spin text-[#737373]" />
      </div>
    )
  }

  if (!data) {
    return <QueueEmptyState text={t('ws.chat.queueLoadFailed', locale)} />
  }

  const showQuickReply = data.can_assign_self && data.conversation_id !== null
  const quickReplyDisabled = assignAndSend.isPending || isOffline
  const visitorName = data.visitor?.name || `${t('ws.chat.queueVisitor', locale)} #${data.conversation_id || data.id}`

  return (
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-white">
      {toast && (
        <div className="pointer-events-none absolute left-1/2 top-4 z-30 -translate-x-1/2 rounded-md border border-[#D8D8D8] bg-white px-3 py-1.5 text-xs text-[#1a1a1a] shadow-sm">
          {toast}
        </div>
      )}
      <div className="flex min-h-[72px] shrink-0 items-center justify-between gap-4 border-b border-[#E5E5E5] px-6 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-base font-semibold text-[#1a1a1a]">
              {data.visitor?.name || `${t('ws.chat.queueVisitor', locale)} #${data.conversation_id || data.id}`}
            </h2>
            <span className="rounded-full bg-[#EBEBEB] px-2 py-0.5 text-[11px] font-medium text-[#737373]">
              {t('ws.chat.queueStatusQueued', locale)}
            </span>
          </div>
          <p className="mt-1 truncate text-xs text-[#737373]">
            {data.channel?.name || data.channel?.channel_type || 'Web'} · {data.queue.name || t('ws.chat.queueUnknown', locale)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {data.can_assign_self && (
            <Button size="sm" onClick={handleAssignSelf} disabled={assignSelf.isPending}>
              {assignSelf.isPending ? <IconLoader2 size={14} className="mr-1 animate-spin" /> : <IconUserCheck size={14} className="mr-1" />}
              {t('ws.chat.queueAssignSelf', locale)}
            </Button>
          )}
          {data.can_assign_other && (
            <Button size="sm" variant="outline" onClick={() => setAssignOpen(true)}>
              <IconUsers size={14} className="mr-1" />
              {t('ws.chat.queueAssignOther', locale)}
            </Button>
          )}
        </div>
      </div>

      <div className="border-b border-[#E5E5E5] px-6 py-4">
        <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
          <QueueMeta label={t('ws.chat.queueName', locale)} value={data.queue.name || '-'} />
          <QueueMeta label={t('ws.chat.queueEnqueuedAt', locale)} value={formatTime(data.enqueued_at)} />
          <QueueMeta label={t('ws.chat.queueWaitTime', locale)} value={formatWait(liveWaitSeconds)} />
        </div>
        {!showQuickReply && (
          <div className="mt-3 rounded-md bg-[#F5F5F5] px-3 py-2 text-xs text-[#737373]">
            {t('ws.chat.queueReadOnlyHint', locale)}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {data.messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-[#737373]">
            {t('ws.chat.queueNoMessages', locale)}
          </div>
        ) : (
          <div className="space-y-3">
            {data.messages.map((message) => (
              <QueueMessageRow key={message.id} message={message} locale={locale} />
            ))}
          </div>
        )}
      </div>

      {showQuickReply ? (
        <div className="shrink-0 border-t border-[#E5E5E5] bg-[#FAFAFA] px-6 pb-4 pt-3">
          <div className="mb-2 text-xs text-muted-foreground">
            {isOffline ? t('ws.chat.queueQuickReplyOffline', locale) : t('ws.chat.queueQuickReplyHint', locale)}
          </div>
          <div className="relative flex flex-col gap-2 rounded-2xl border border-[#E5E5E5] bg-white pl-3.5 pr-3.5 pt-3 pb-2.5 transition-colors">
            <textarea
              value={quickReplyDraft}
              onChange={(event) => selectedId && updateQuickReplyDraft(selectedId, event.target.value)}
              onKeyDown={handleQuickReplyKeyDown}
              onPaste={handleQuickReplyPaste}
              placeholder={t('ws.chat.queueQuickReplyPlaceholder', locale)}
              disabled={quickReplyDisabled}
              rows={2}
              className="max-h-[168px] min-h-[44px] w-full resize-none overflow-y-auto border-0 bg-transparent p-0 text-sm leading-[22px] text-[#1a1a1a] outline-none ring-0 transition-colors placeholder:text-[#BBBBBB] focus-visible:ring-0 disabled:cursor-not-allowed disabled:text-muted-foreground"
            />
            <div className="flex items-center justify-between">
              <span className={cn(
                'text-[11px]',
                quickReplyLength > QUICK_REPLY_MAX_LENGTH ? 'text-destructive' : 'text-[#999999]',
              )}>
                {quickReplyLength} / {QUICK_REPLY_MAX_LENGTH}
              </span>
              <button
                type="button"
                onClick={handleQuickReplySend}
                disabled={quickReplyDisabled}
                title={t('ws.chat.queueQuickReplySendAria', locale)}
                aria-label={t('ws.chat.queueQuickReplySendAria', locale)}
                className="flex shrink-0 items-center gap-1.5 rounded-2xl bg-[#1a1a1a] px-4 py-1.5 text-[13px] font-medium leading-none text-white transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-40"
              >
                {assignAndSend.isPending ? (
                  <IconLoader2 size={15} className="animate-spin" />
                ) : (
                  <IconSend size={15} />
                )}
                {t('ws.chat.queueQuickReplySend', locale)}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="shrink-0 border-t border-border bg-background px-6 py-3 text-xs text-muted-foreground">
          {t('ws.chat.queueReadOnlyHint', locale)}
        </div>
      )}

      <QueueAssignDialog
        open={assignOpen}
        taskId={selectedId}
        task={data}
        waitSeconds={liveWaitSeconds}
        submitting={assignAgent.isPending}
        onClose={() => setAssignOpen(false)}
        onSubmit={async (agentId, reason) => {
          try {
            const response = await assignAgent.mutateAsync({ taskId: selectedId, agentId, reason })
            const name = response.assigned_agent?.display_name || response.assigned_agent?.name || `#${agentId}`
            showToast(t('ws.chat.queueAssignedToAgent', locale, { name }))
            setAssignOpen(false)
            onAssigned(response)
          } catch {
            showToast(t('ws.chat.queueAssignFailed', locale))
            void refetch()
          }
        }}
      />

      <Dialog open={capacityConfirmOpen} onOpenChange={(open) => { if (!assignAndSend.isPending) setCapacityConfirmOpen(open) }}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle>{t('ws.chat.queueQuickReplyCapacityTitle', locale)}</DialogTitle>
            <DialogDescription>
              {t('ws.chat.queueQuickReplyCapacityDescription', locale)}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 rounded-md border border-border bg-muted px-3 py-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">{t('ws.chat.receptionLabel', locale)}</span>
              <span className="font-medium text-foreground">
                {(agentStatus?.current_count ?? 0)} / {(agentStatus?.max_concurrent ?? 0)}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">{t('ws.chat.queueVisitor', locale)}</span>
              <span className="min-w-0 truncate font-medium text-foreground">{visitorName}</span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCapacityConfirmOpen(false)} disabled={assignAndSend.isPending}>
              {t('ws.common.cancel', locale)}
            </Button>
            <Button
              onClick={() => {
                setCapacityConfirmOpen(false)
                if (pendingQuickReplyTaskId) void submitQuickReply(pendingQuickReplyTaskId, pendingQuickReply)
              }}
              disabled={assignAndSend.isPending}
            >
              {assignAndSend.isPending && <IconLoader2 size={14} className="mr-1 animate-spin" />}
              {t('ws.chat.queueQuickReplyCapacityConfirm', locale)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function QueueAssignDialog({
  open,
  taskId,
  task,
  waitSeconds,
  submitting,
  onClose,
  onSubmit,
}: {
  open: boolean
  taskId: number
  task: QueueWorkspaceTask
  waitSeconds: number
  submitting: boolean
  onClose: () => void
  onSubmit: (agentId: number, reason: string) => Promise<void>
}) {
  const { locale } = useLocaleStore()
  const { user } = useAuthStore()
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!open) return
    setKeyword('')
    setDebouncedKeyword('')
    setSelectedId(null)
    setReason('')
  }, [open, taskId])

  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => setDebouncedKeyword(keyword), 300)
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [keyword])

  const { data, isLoading, isFetching } = useAssignableAgents(debouncedKeyword, open)
  const currentUserId = user?.id ?? null
  const agents = useMemo(
    () => (data?.items ?? []).filter((agent) => agent.id !== currentUserId),
    [data?.items, currentUserId],
  )
  const selectedAgent = useMemo(() => agents.find((agent) => agent.id === selectedId) ?? null, [agents, selectedId])
  const canSubmit = !!selectedAgent && selectedAgent.selectable && !submitting

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !submitting) onClose() }}>
      <DialogContent className="gap-3 pb-3 sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t('ws.chat.queueAssignDialogTitle', locale)}</DialogTitle>
          <DialogDescription>
            {task.visitor?.name || t('ws.chat.queueVisitor', locale)} · {task.queue.name || t('ws.chat.queueUnknown', locale)} · {formatWait(waitSeconds)}
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <IconSearch size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder={t('ws.chat.queueAgentSearch', locale)}
            className="pl-8 pr-8"
            autoFocus
          />
          {isFetching && <IconLoader2 size={16} className="absolute right-2.5 top-1/2 -translate-y-1/2 animate-spin text-muted-foreground" />}
        </div>

        <div className="-mx-1 max-h-[300px] min-h-[180px] overflow-y-auto px-1">
          {isLoading ? (
            <div className="space-y-2 py-2">
              {[0, 1, 2].map((item) => <div key={item} className="h-12 animate-pulse rounded-md bg-muted/60" />)}
            </div>
          ) : agents.length === 0 ? (
            <div className="flex min-h-[180px] items-center justify-center text-sm text-muted-foreground">
              {t('ws.chat.queueNoAssignableAgents', locale)}
            </div>
          ) : (
            <ul className="divide-y divide-border/60">
              {agents.map((agent) => {
                const selected = agent.id === selectedId
                return (
                  <li
                    key={agent.id}
                    aria-disabled={!agent.selectable}
                    onClick={() => {
                      if (agent.selectable) setSelectedId(agent.id)
                    }}
                    className={cn(
                      'flex items-center gap-3 rounded-md px-2 py-2 transition-colors',
                      agent.selectable ? 'cursor-pointer hover:bg-muted' : 'cursor-not-allowed opacity-60',
                      selected && 'bg-primary/10 hover:bg-primary/10',
                    )}
                  >
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium">
                      {displayAgentName(agent).charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{displayAgentName(agent)}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {agent.group_names.join(', ') || '-'} · {agent.current_count} / {agent.max_concurrent}
                        {agent.current_count >= agent.max_concurrent ? ` · ${t('ws.chat.queueWillExceedCapacity', locale)}` : ''}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: STATUS_COLOR[agent.online_status] || '#9CA3AF' }} />
                      <span>{t(`ws.chat.transferStatus${agent.online_status.charAt(0).toUpperCase()}${agent.online_status.slice(1)}`, locale)}</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value.slice(0, 200))}
          placeholder={t('ws.chat.queueAssignReasonPlaceholder', locale)}
          className="min-h-[72px] resize-none rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />

        <DialogFooter className="pt-2 pb-0">
          <Button variant="outline" onClick={onClose} disabled={submitting}>{t('ws.common.cancel', locale)}</Button>
          <Button onClick={() => selectedId && onSubmit(selectedId, reason)} disabled={!canSubmit}>
            {submitting && <IconLoader2 size={14} className="mr-1 animate-spin" />}
            {t('ws.chat.queueAssignConfirm', locale)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function QueueMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-[#E5E5E5] px-3 py-2">
      <div className="text-[11px] text-[#999999]">{label}</div>
      <div className="mt-1 truncate text-sm font-medium text-[#1a1a1a]">{value}</div>
    </div>
  )
}

function QueueMessageRow({ message, locale }: { message: Message; locale: Locale }) {
  const isVisitor = message.sender_type === 'visitor'
  const isSystem = message.sender_type === 'system'
  const isBot = message.sender_type === 'bot'

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <div className="max-w-[68%] rounded-lg bg-[#F5F5F5] px-3 py-2 text-xs text-[#737373]">
          <div className="whitespace-pre-wrap break-words">{messagePreview(message, locale)}</div>
        </div>
      </div>
    )
  }

  if (isVisitor) {
    return (
      <div className="flex justify-start">
        <div className="flex min-w-0 max-w-[68%] flex-col items-start">
          <span className="mb-1 text-[11px] text-[#737373]">
            {message.sender_name || t('ws.chat.queueVisitor', locale)}
          </span>
          <div className="rounded-lg bg-[#F5F5F5] px-3 py-2 text-sm text-[#1a1a1a]">
            <div className="whitespace-pre-wrap break-words">{messagePreview(message, locale)}</div>
          </div>
        </div>
      </div>
    )
  }

  const senderLabel = isBot
    ? (message.sender_name || (locale === 'zh' ? '智能助手' : 'Assistant'))
    : (message.sender_name || getWorkspaceHumanAgentLabel(locale))

  return (
    <div className="flex justify-end">
      <div className="flex min-w-0 max-w-[68%] flex-col items-end">
        {senderLabel && (
          <span className="mb-1 text-[11px] text-[#737373]">{senderLabel}</span>
        )}
        <div
          className={cn(
            'rounded-lg px-3 py-2 text-sm',
            isBot
              ? cn('bg-[#DBEAFE] text-[#1a1a1a]', markdownTextRootClass, richTextListStyleClass)
              : 'bg-[#1a1a1a] text-white',
          )}
        >
          {isBot && message.content_type === 'text' ? (
            <MarkdownText>{message.content}</MarkdownText>
          ) : (
            <div className="whitespace-pre-wrap break-words">{messagePreview(message, locale)}</div>
          )}
        </div>
      </div>
    </div>
  )
}

function QueueEmptyState({ text }: { text: string }) {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center bg-white">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#F5F5F5]">
          <IconClock size={32} className="text-[#999999]" />
        </div>
        <p className="text-sm text-[#737373]">{text}</p>
      </div>
    </div>
  )
}
