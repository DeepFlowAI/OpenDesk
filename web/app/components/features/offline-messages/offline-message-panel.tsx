'use client'

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  IconArchive,
  IconInbox,
  IconLoader2,
  IconMessageCircle,
  IconRefresh,
  IconSearch,
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
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { cn } from '@/lib/utils'
import type { AgentStatus, Conversation, Message } from '@/models/conversation'
import type { UnifiedField } from '@/models/field-definition'
import type {
  OfflineMessage,
  OfflineMessageArchiveResponse,
  OfflineMessageConvertResponse,
  OfflineMessageDetail,
  OfflineMessageEntry,
} from '@/models/offline-message'
import type { QueueAssignableAgent } from '@/models/queue-workspace'
import type { User } from '@/models/user'
import {
  getNextPendingOfflineMessageId,
  useArchiveOfflineMessage,
  useAssignOfflineMessageToAgent,
  useAssignOfflineMessageToSelf,
  useOfflineMessage,
  useOfflineMessages,
  type OfflineMessageListStatus,
} from '@/service/use-offline-messages'
import { uploadAgentOfflineMessageFile } from '@/service/use-conversation-files'
import { useAssignableAgents } from '@/service/use-queue-workspace'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { useUser } from '@/service/use-users'
import { useBottomScrollAnchor } from '@/hooks/use-bottom-scroll-anchor'
import { WorkspaceMessageBubble } from '@/app/components/features/chat/workspace-message-bubble'
import { DeferredConversationComposer } from '@/app/components/features/chat/deferred-conversation-composer'
import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { getDataScope, hasPermission } from '@/utils/permissions'
import { t } from '@/utils/i18n'
import type { Socket } from 'socket.io-client'

type OfflineAssignedOptions = { openConversation?: boolean; messageSent?: boolean }

type OfflineAssignedHandler = (
  response: OfflineMessageConvertResponse,
  offlineMessageId: number,
  options?: OfflineAssignedOptions,
) => void

type OfflineArchivedHandler = (
  response: OfflineMessageArchiveResponse,
  offlineMessageId: number,
) => void

type Props = {
  status: OfflineMessageListStatus
  onAssigned?: OfflineAssignedHandler
  onArchived?: OfflineArchivedHandler
  readOnly?: boolean
  agentStatus?: AgentStatus | null
  socket?: Socket | null
  showStatusFilter?: boolean
}

type OfflineMessageListSidebarProps = {
  status: OfflineMessageListStatus
  items: OfflineMessage[]
  selectedId: number | null
  onSelect: (id: number) => void
  loading: boolean
  onRefresh: () => void
  onAssigned?: OfflineAssignedHandler
  readOnly?: boolean
  agentStatus?: AgentStatus | null
  showTitle?: boolean
}

type OfflineMessageDetailPanelProps = {
  selectedId: number | null
  onAssigned?: OfflineAssignedHandler
  onArchived?: OfflineArchivedHandler
  readOnly?: boolean
  agentStatus?: AgentStatus | null
  socket?: Socket | null
  auxiliaryPanelWidth?: number
  resizeHandle?: ReactNode
  composerInputHeight?: number
  onComposerInputHeightCommit?: (height: number) => void
}

const STATUS_COLOR: Record<string, string> = {
  online: '#22C55E',
  busy: '#F59E0B',
  offline: '#9CA3AF',
}

const SYSTEM_KEY_ALIAS: Record<string, keyof User> = {
  nickname: 'name',
  assignee: 'agent_id',
  assignee_group: 'assignee_group_id',
}

function offlineMessageDraftConversation(detail: OfflineMessageDetail): Conversation {
  return {
    id: detail.conversation?.id ?? -detail.id,
    public_id: detail.conversation?.public_id ?? detail.public_id,
    share_code: detail.conversation?.share_code ?? '',
    tenant_id: detail.tenant_id,
    visitor: detail.visitor,
    agent: null,
    channel: detail.channel,
    group: detail.target_group,
    status: detail.conversation?.status ?? 'queued',
    started_at: detail.conversation?.started_at ?? null,
    ended_at: null,
    ended_by: null,
    last_message_at: detail.last_message_at,
    last_message_preview: detail.last_message_preview,
    visitor_system: null,
    visitor_browser: null,
    visitor_ip: null,
    unread_count: 0,
    has_history_conversations: false,
    viewer_relation: 'own',
    collaborated_by_current_user: false,
    collaborators: [],
    created_at: detail.created_at,
  }
}

function formatTime(value: string | null | undefined, locale: string): string {
  if (!value) return '-'
  const date = new Date(value)
  return date.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function previewText(item: OfflineMessage, locale: string): string {
  if (item.last_message_preview) return item.last_message_preview
  return locale === 'zh' ? '暂无留言内容' : 'No message content'
}

function visitorLabel(item: OfflineMessage, locale: string): string {
  return item.visitor?.name || item.visitor_name || (locale === 'zh' ? '访客' : 'Visitor')
}

function statusLabel(status: OfflineMessage['status'], locale: string): string {
  if (status === 'pending') return locale === 'zh' ? '待处理' : 'Pending'
  if (status === 'archived') return locale === 'zh' ? '已归档' : 'Archived'
  return locale === 'zh' ? '已创建会话' : 'Converted'
}

function listTitle(status: OfflineMessageListStatus, locale: string): string {
  if (status === 'pending') return locale === 'zh' ? '待处理留言' : 'Pending Messages'
  if (status === 'converted') return locale === 'zh' ? '已创建会话留言' : 'Converted Messages'
  if (status === 'archived') return locale === 'zh' ? '已归档留言' : 'Archived Messages'
  return locale === 'zh' ? '全部留言' : 'All Offline Messages'
}

function statusBadgeClass(status: OfflineMessage['status']): string {
  if (status === 'pending') return 'bg-amber-50 text-amber-700'
  if (status === 'archived') return 'bg-muted text-muted-foreground'
  return 'bg-emerald-50 text-emerald-700'
}

function entryToMessage(entry: OfflineMessageEntry): Message {
  return {
    ...entry,
    conversation_id: entry.offline_message_id,
  }
}

export function OfflineMessageListSidebar({
  status,
  items,
  selectedId,
  onSelect,
  loading,
  onRefresh,
  onAssigned,
  readOnly = false,
  agentStatus = null,
  showTitle = true,
}: OfflineMessageListSidebarProps) {
  const { locale } = useLocaleStore()
  const { user } = useAuthStore()
  const assignSelf = useAssignOfflineMessageToSelf()
  const assignAgent = useAssignOfflineMessageToAgent()
  const [assigningSelfId, setAssigningSelfId] = useState<number | null>(null)
  const [assignDialogItem, setAssignDialogItem] = useState<OfflineMessage | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const canAssignSelf = hasPermission(user, 'chat.queue.assign_self')
  const canAssignOther =
    hasPermission(user, 'chat.queue.assign_other') && getDataScope(user, 'offline_message') !== 'self'

  useEffect(() => () => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
  }, [])

  const showToast = (text: string) => {
    setToast(text)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(null), 2500)
  }

  const handleAssignSelf = async (item: OfflineMessage) => {
    if (agentStatus?.status === 'offline') {
      showToast(t('ws.chat.queueAssignSelfOffline', locale))
      return
    }
    setAssigningSelfId(item.id)
    try {
      const result = await assignSelf.mutateAsync({ id: item.id })
      onAssigned?.(result, item.id)
    } catch (err) {
      const backendMessage = await readBackendErrorMessage(err)
      showToast(
        backendMessage === ACTIVE_CONVERSATION_ERROR
          ? t('ws.chat.queueAssignActiveConversation', locale)
          : t('ws.chat.queueAssignFailed', locale),
      )
    } finally {
      setAssigningSelfId(null)
    }
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-[#FAFAFA]">
      {toast && (
        <div className="pointer-events-none absolute left-1/2 top-3 z-40 -translate-x-1/2 rounded-md border border-[#D8D8D8] bg-white px-3 py-1.5 text-xs text-[#1a1a1a] shadow-sm">
          {toast}
        </div>
      )}
      {showTitle && (
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <IconInbox size={18} />
            {listTitle(status, locale)}
          </div>
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-background hover:text-foreground"
            onClick={onRefresh}
            aria-label={locale === 'zh' ? '刷新' : 'Refresh'}
            title={locale === 'zh' ? '刷新' : 'Refresh'}
          >
            <IconRefresh size={16} />
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <IconLoader2 size={20} className="animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground">
            <IconMessageCircle size={28} />
            {locale === 'zh' ? '暂无留言' : 'No offline messages'}
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {items.map((item) => {
              const selected = selectedId === item.id
              const assigningSelf = assigningSelfId === item.id
              const showAssignActions = !readOnly && item.status === 'pending' && (canAssignSelf || canAssignOther)
              const assignDisabled = item.message_count === 0
              return (
                <div
                  key={item.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(item.id)}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return
                    if (event.key !== 'Enter' && event.key !== ' ') return
                    event.preventDefault()
                    onSelect(item.id)
                  }}
                  className={cn(
                    'relative w-full cursor-pointer overflow-hidden rounded-[9px] px-3 py-2.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring',
                    selected
                      ? '-mx-2 w-[calc(100%+1rem)] rounded-none bg-white px-5'
                      : 'hover:-mx-2 hover:w-[calc(100%+1rem)] hover:rounded-none hover:bg-white/60 hover:px-5',
                  )}
                >
                  {selected && (
                    <>
                      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-px bg-[linear-gradient(to_right,color-mix(in_oklab,var(--color-success)_15%,transparent),var(--color-success))]" />
                      <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-px bg-[linear-gradient(to_right,color-mix(in_oklab,var(--color-success)_15%,transparent),var(--color-success))]" />
                      <span aria-hidden="true" className="absolute inset-y-0 right-0 w-1 bg-success" />
                    </>
                  )}
                  <div className="flex items-center justify-between gap-3">
                    <span className="min-w-0 truncate text-sm font-medium text-foreground">
                      {visitorLabel(item, locale)}
                    </span>
                    <span
                      className={cn(
                        'shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium',
                        statusBadgeClass(item.status),
                      )}
                    >
                      {statusLabel(item.status, locale)}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">
                    {previewText(item, locale)}
                  </p>
                  <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                    <span className="min-w-0 truncate">{item.channel?.name || '-'}</span>
                    {showAssignActions ? (
                      <div className="flex shrink-0 items-center gap-1">
                        {canAssignSelf && (
                          <button
                            type="button"
                            data-action="offline-assign-self"
                            onClick={(event) => {
                              event.stopPropagation()
                              void handleAssignSelf(item)
                            }}
                            disabled={assigningSelf || assignDisabled}
                            className="flex h-7 w-7 items-center justify-center rounded-md border border-[#E5E5E5] bg-white text-[#737373] transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                            aria-label={t('ws.chat.queueAssignSelf', locale)}
                            title={t('ws.chat.queueAssignSelf', locale)}
                          >
                            {assigningSelf ? (
                              <IconLoader2 size={15} stroke={1.8} className="animate-spin" />
                            ) : (
                              <IconUserCheck size={15} stroke={1.8} />
                            )}
                          </button>
                        )}
                        {canAssignOther && (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              setAssignDialogItem(item)
                            }}
                            disabled={assignDisabled}
                            className="flex h-7 w-7 items-center justify-center rounded-md border border-[#E5E5E5] bg-white text-[#737373] transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60"
                            aria-label={t('ws.chat.queueAssignOther', locale)}
                            title={t('ws.chat.queueAssignOther', locale)}
                          >
                            <IconUsers size={15} stroke={1.8} />
                          </button>
                        )}
                      </div>
                    ) : (
                      <span className="shrink-0">{formatTime(item.last_message_at || item.created_at, locale)}</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {assignDialogItem && (
        <OfflineMessageAssignDialog
          open
          offlineMessageId={assignDialogItem.id}
          detail={assignDialogItem}
          submitting={assignAgent.isPending}
          onClose={() => setAssignDialogItem(null)}
          onSubmit={async (agentId, reason) => {
            const offlineMessageId = assignDialogItem.id
            try {
              const result = await assignAgent.mutateAsync({
                id: offlineMessageId,
                agentId,
                reason,
              })
              setAssignDialogItem(null)
              onAssigned?.(result, offlineMessageId)
            } catch (err) {
              const backendMessage = await readBackendErrorMessage(err)
              showToast(
                backendMessage === ACTIVE_CONVERSATION_ERROR
                  ? t('ws.chat.queueAssignActiveConversation', locale)
                  : t('ws.chat.queueAssignFailed', locale),
              )
            }
          }}
        />
      )}
    </div>
  )
}

function displayAgentName(agent: QueueAssignableAgent): string {
  return agent.display_name || agent.name || `#${agent.id}`
}

// Backend message returned when the visitor already has an in-progress conversation.
const ACTIVE_CONVERSATION_ERROR = 'Visitor already has an active conversation'
const OFFLINE_MESSAGE_CONVERTED_ERROR = 'Offline message has already been converted'
const OFFLINE_MESSAGE_ARCHIVED_ERROR = 'Offline message has already been archived'

async function readBackendErrorMessage(err: unknown): Promise<string | null> {
  if (err && typeof err === 'object' && 'response' in err) {
    const resp = (err as { response: Response }).response
    try {
      const body = (await resp.clone().json()) as { message?: string }
      return body?.message ?? null
    } catch {
      return null
    }
  }
  return null
}

export function OfflineMessageDetailPanel({
  selectedId,
  onAssigned,
  onArchived,
  readOnly = false,
  agentStatus = null,
  socket = null,
  auxiliaryPanelWidth,
  resizeHandle,
  composerInputHeight,
  onComposerInputHeightCommit,
}: OfflineMessageDetailPanelProps) {
  const { locale } = useLocaleStore()
  const detailQuery = useOfflineMessage(selectedId)
  const archiveMessage = useArchiveOfflineMessage()
  const assignSelf = useAssignOfflineMessageToSelf()
  const assignAgent = useAssignOfflineMessageToAgent()
  const detail = detailQuery.data ?? null
  const showAuxiliaryPanel = typeof auxiliaryPanelWidth === 'number'
  const [toast, setToast] = useState<string | null>(null)
  const [assignOpen, setAssignOpen] = useState(false)
  const deferredAssignmentRef = useRef<OfflineMessageConvertResponse | null>(null)
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
  }, [])

  const showToast = useCallback((text: string) => {
    setToast(text)
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    toastTimerRef.current = setTimeout(() => setToast(null), 2500)
  }, [])

  const isOffline = agentStatus?.status === 'offline'

  const handleAssignSelf = useCallback(async () => {
    if (!detail || detail.status !== 'pending') return
    if (agentStatus?.status === 'offline') {
      showToast(t('ws.chat.queueAssignSelfOffline', locale))
      return
    }
    try {
      const result = await assignSelf.mutateAsync({ id: detail.id })
      onAssigned?.(result, detail.id)
    } catch (err) {
      const backendMessage = await readBackendErrorMessage(err)
      showToast(
        backendMessage === ACTIVE_CONVERSATION_ERROR
          ? t('ws.chat.queueAssignActiveConversation', locale)
          : t('ws.chat.queueAssignFailed', locale),
      )
      void detailQuery.refetch()
    }
  }, [agentStatus?.status, assignSelf, detail, detailQuery, locale, onAssigned, showToast])

  const handleArchive = useCallback(async () => {
    if (!detail || detail.status !== 'pending') return
    try {
      const result = await archiveMessage.mutateAsync(detail.id)
      onArchived?.(result, detail.id)
      showToast(t('ws.chat.offlineArchived', locale))
    } catch (err) {
      const backendMessage = await readBackendErrorMessage(err)
      showToast(
        backendMessage === OFFLINE_MESSAGE_ARCHIVED_ERROR
          ? t('ws.chat.offlineArchived', locale)
          : backendMessage === OFFLINE_MESSAGE_CONVERTED_ERROR
            ? t('ws.chat.offlineAlreadyConverted', locale)
            : t('ws.chat.queueAssignFailed', locale),
      )
      void detailQuery.refetch()
    }
  }, [archiveMessage, detail, detailQuery, locale, onArchived, showToast])

  const isProcessing =
    archiveMessage.isPending
    || assignSelf.isPending
    || assignAgent.isPending
  const deferredConversation = detail ? offlineMessageDraftConversation(detail) : null
  const messageScroll = useBottomScrollAnchor<HTMLDivElement>(
    `${detail?.id ?? 'none'}:${detail?.messages.length ?? 0}`,
  )
  const resolveConversationForSend = async () => {
    if (!detail || detail.status !== 'pending') throw new Error('Offline message is required')
    if (isOffline) {
      showToast(t('ws.chat.queueQuickReplyOffline', locale))
      throw new Error('Agent is offline')
    }

    try {
      const response = await assignSelf.mutateAsync({ id: detail.id })
      deferredAssignmentRef.current = response
      return { conversation: response.conversation }
    } catch (err) {
      deferredAssignmentRef.current = null
      const backendMessage = await readBackendErrorMessage(err)
      showToast(
        backendMessage === ACTIVE_CONVERSATION_ERROR
          ? t('ws.chat.queueAssignActiveConversation', locale)
          : t('ws.chat.queueQuickSendStateChanged', locale),
      )
      void detailQuery.refetch()
      throw err
    }
  }

  return (
    <>
      <main className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        {toast && (
          <div className="pointer-events-none absolute left-1/2 top-4 z-30 -translate-x-1/2 rounded-md border border-[#D8D8D8] bg-white px-3 py-1.5 text-xs text-[#1a1a1a] shadow-sm">
            {toast}
          </div>
        )}
        {!selectedId ? (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            {locale === 'zh' ? '请选择留言' : 'Select an offline message'}
          </div>
        ) : detailQuery.isLoading || !detail ? (
          <div className="flex flex-1 items-center justify-center">
            <IconLoader2 size={22} className="animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-[#E5E5E5] bg-[#FAFAFA] px-6">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-foreground">
                  {visitorLabel(detail, locale)}
                </div>
                <div className="mt-0.5 truncate text-xs text-muted-foreground">
                  {detail.channel?.name || '-'} · {detail.target_group?.name || (locale === 'zh' ? '未命中员工组' : 'No group')}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1 text-xs font-medium',
                    statusBadgeClass(detail.status),
                  )}
                >
                  {statusLabel(detail.status, locale)}
                </span>
                {!readOnly && detail.status === 'pending' && (
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={isProcessing}
                      onClick={() => void handleArchive()}
                    >
                      {archiveMessage.isPending ? (
                        <IconLoader2 size={14} className="mr-1 animate-spin" />
                      ) : (
                        <IconArchive size={14} className="mr-1" />
                      )}
                      {t('ws.chat.offlineArchive', locale)}
                    </Button>
                    {detail.can_assign_self && (
                      <Button
                        size="sm"
                        disabled={isProcessing || detail.messages.length === 0}
                        onClick={() => void handleAssignSelf()}
                      >
                        {assignSelf.isPending ? (
                          <IconLoader2 size={14} className="mr-1 animate-spin" />
                        ) : (
                          <IconUserCheck size={14} className="mr-1" />
                        )}
                        {t('ws.chat.queueAssignSelf', locale)}
                      </Button>
                    )}
                    {detail.can_assign_other && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isProcessing || detail.messages.length === 0}
                        onClick={() => setAssignOpen(true)}
                      >
                        <IconUsers size={14} className="mr-1" />
                        {t('ws.chat.queueAssignOther', locale)}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div
              ref={messageScroll.scrollRef}
              onScroll={messageScroll.onScroll}
              className="min-h-0 flex-1 overflow-y-auto bg-[#FAFAFA] px-6 py-5"
            >
              {detail.messages.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  {locale === 'zh' ? '暂无留言内容' : 'No message content'}
                </div>
              ) : (
                <div className="flex flex-col">
                  {detail.messages.map((entry) => (
                    <WorkspaceMessageBubble
                      key={entry.id}
                      message={entryToMessage(entry)}
                      locale={locale}
                      mode="preview"
                      showTimestamp
                      attachmentContext={{ kind: 'offline_message', offlineMessageId: detail.id }}
                      visitorName={detail.visitor?.name || detail.visitor_name || null}
                    />
                  ))}
                </div>
              )}
            </div>

            {!readOnly && detail.status === 'pending' && detail.can_assign_self && detail.messages.length > 0 && deferredConversation && (
              <div className="shrink-0">
                <DeferredConversationComposer
                  conversation={deferredConversation}
                  socket={socket}
                  locale={locale}
                  disabled={isProcessing || isOffline}
                  disabledReason={isOffline ? t('ws.chat.queueQuickReplyOffline', locale) : null}
                  placeholder={t('ws.chat.queueQuickReplyHint', locale)}
                  inputHeight={composerInputHeight}
                  onInputHeightCommit={onComposerInputHeightCommit}
                  resolveConversationForSend={resolveConversationForSend}
                  uploadDeferredRichTextImage={(file) => uploadAgentOfflineMessageFile({
                    offlineMessageId: detail.id,
                    file,
                  })}
                  onResolved={(_conversation, result) => {
                    const assignment = deferredAssignmentRef.current
                    if (!assignment || !detail) return
                    onAssigned?.(assignment, detail.id, {
                      openConversation: true,
                      messageSent: result.messageSent,
                    })
                  }}
                />
              </div>
            )}

            <OfflineMessageAssignDialog
              open={assignOpen}
              offlineMessageId={detail.id}
              detail={detail}
              submitting={assignAgent.isPending}
              onClose={() => setAssignOpen(false)}
              onSubmit={async (agentId, reason) => {
                try {
                  const result = await assignAgent.mutateAsync({
                    id: detail.id,
                    agentId,
                    reason,
                  })
                  setAssignOpen(false)
                  onAssigned?.(result, detail.id)
                } catch (err) {
                  const backendMessage = await readBackendErrorMessage(err)
                  showToast(
                    backendMessage === ACTIVE_CONVERSATION_ERROR
                      ? t('ws.chat.queueAssignActiveConversation', locale)
                      : t('ws.chat.queueAssignFailed', locale),
                  )
                  void detailQuery.refetch()
                }
              }}
            />
          </>
        )}
      </main>
      {showAuxiliaryPanel ? (
        <>
          {resizeHandle}
          <OfflineMessageAssistPanel
            detail={detail}
            loading={Boolean(selectedId) && detailQuery.isLoading}
            selected={Boolean(selectedId)}
            width={auxiliaryPanelWidth}
          />
        </>
      ) : null}
    </>
  )
}

function OfflineMessageAssignDialog({
  open,
  offlineMessageId,
  detail,
  submitting,
  onClose,
  onSubmit,
}: {
  open: boolean
  offlineMessageId: number
  detail: OfflineMessage
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
  }, [open, offlineMessageId])

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
  const visitorName = detail.visitor?.name || detail.visitor_name || t('ws.chat.queueVisitor', locale)
  const groupName = detail.target_group?.name || t('ws.chat.queueUnknown', locale)

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !submitting) onClose() }}>
      <DialogContent className="gap-3 pb-3 sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t('ws.chat.offlineAssignDialogTitle', locale)}</DialogTitle>
          <DialogDescription>
            {visitorName} · {groupName}
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
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-sm font-medium">
                      {agent.avatar ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={agent.avatar} alt={displayAgentName(agent)} className="h-full w-full object-cover" />
                      ) : (
                        displayAgentName(agent).charAt(0).toUpperCase()
                      )}
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

function OfflineMessageAssistPanel({
  detail,
  loading,
  selected,
  width,
}: {
  detail: OfflineMessageDetail | null
  loading: boolean
  selected: boolean
  width: number
}) {
  const { locale } = useLocaleStore()
  const visitorId = detail?.visitor?.id ?? 0
  const userQuery = useUser(visitorId)
  const fieldsQuery = useUnifiedFields({ domain: 'user', locale, include_metadata: true })
  const workspaceFields = useMemo(
    () =>
      (fieldsQuery.data?.items ?? [])
        .filter((field) => field.source !== 'metadata' && field.status === 'active' && field.show_in_workspace === true)
        .sort((a, b) => a.sort_order - b.sort_order),
    [fieldsQuery.data?.items],
  )

  return (
    <aside className="relative flex shrink-0 flex-col bg-[#F5F5F5]" style={{ width }}>
      {!selected ? (
        <div className="flex flex-1 items-center justify-center px-5">
          <p className="text-sm text-[#737373]">{t('ws.chat.selectHint', locale)}</p>
        </div>
      ) : loading || !detail ? (
        <div className="flex flex-1 items-center justify-center">
          <IconLoader2 size={22} className="animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          <section className="flex flex-col gap-[14px]">
            <h3 className="text-sm font-semibold text-[#1a1a1a]">
              {locale === 'zh' ? '基本信息' : 'Basic Info'}
            </h3>
            <InfoRow label={locale === 'zh' ? '留言编号' : 'Message ID'} value={detail.public_id || String(detail.id)} />
            <InfoRow
              label={t('ws.chat.visitorId', locale)}
              value={detail.visitor?.public_id || detail.visitor_external_id || '-'}
            />
            <InfoRow label={t('ws.chat.sourceChannel', locale)} value={detail.channel?.channel_type || '-'} />
            <InfoRow label={t('ws.chat.channelName', locale)} value={detail.channel?.name || '-'} />
            <InfoRow label={t('ws.chat.agentGroup', locale)} value={detail.target_group?.name || '-'} />
            <InfoRow label={locale === 'zh' ? '处理状态' : 'Status'} value={statusLabel(detail.status, locale)} />
            <InfoRow
              label={locale === 'zh' ? '处理客服' : 'Handled By'}
              value={
                detail.handled_by?.display_name
                || detail.handled_by?.name
                || (detail.handled_by_id ? `#${detail.handled_by_id}` : '-')
              }
            />
            <InfoRow label={locale === 'zh' ? '处理时间' : 'Handled At'} value={formatTime(detail.handled_at, locale)} />
            <InfoRow label={locale === 'zh' ? '留言时间' : 'Created At'} value={formatTime(detail.created_at, locale)} />
            <InfoRow label={locale === 'zh' ? '最近留言' : 'Last Message'} value={formatTime(detail.last_message_at, locale)} />
            <InfoRow label={locale === 'zh' ? '消息数' : 'Messages'} value={String(detail.message_count)} />
          </section>

          <section className="mt-5 border-t border-border pt-4">
            <h3 className="mb-3 text-sm font-semibold text-[#1a1a1a]">
              {t('ws.chat.userInfo', locale)}
            </h3>
            <OfflineMessageUserInfoSection
              locale={locale}
              visitorId={visitorId}
              user={userQuery.data ?? null}
              fields={workspaceFields}
              isLoading={userQuery.isLoading || fieldsQuery.isLoading}
              isError={userQuery.isError || fieldsQuery.isError}
              onRetry={() => {
                void userQuery.refetch()
                void fieldsQuery.refetch()
              }}
            />
          </section>
        </div>
      )}
    </aside>
  )
}

function OfflineMessageUserInfoSection({
  locale,
  visitorId,
  user,
  fields,
  isLoading,
  isError,
  onRetry,
}: {
  locale: 'zh' | 'en'
  visitorId: number
  user: User | null
  fields: UnifiedField[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
}) {
  if (!visitorId) {
    return <PanelStateMessage>{t('ws.chat.noLinkedUser', locale)}</PanelStateMessage>
  }

  if (isLoading) {
    return <PanelStateMessage>{t('ws.chat.userInfoLoading', locale)}</PanelStateMessage>
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
        <p className="text-xs text-destructive">{t('ws.chat.userInfoLoadFailed', locale)}</p>
        <button type="button" onClick={onRetry} className="mt-2 text-xs font-medium text-primary hover:underline">
          {t('ws.chat.retry', locale)}
        </button>
      </div>
    )
  }

  if (!user) {
    return <PanelStateMessage>{t('ws.chat.noLinkedUser', locale)}</PanelStateMessage>
  }

  if (fields.length === 0) {
    return <PanelStateMessage>{t('ws.chat.noWorkspaceFields', locale)}</PanelStateMessage>
  }

  return (
    <div className="flex flex-col gap-[14px]">
      {fields.map((field) => (
        <div key={getFieldIdentity(field)} className="flex flex-col gap-1">
          <span className="text-[12px] text-[#999999]">{field.name}</span>
          <FieldValueDisplay
            fieldType={field.field_type}
            value={getFieldRawValue(user, field)}
            typeConfig={field.type_config ?? {}}
            options={field.options}
            treeNodes={field.tree_nodes}
            className="break-words text-[13px] text-[#1a1a1a]"
          />
        </div>
      ))}
      <div aria-hidden className="h-[200px] shrink-0" />
    </div>
  )
}

function PanelStateMessage({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
      <p className="text-xs text-[#737373]">{children}</p>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[12px] text-[#999999]">{label}</span>
      <span className="min-w-0 break-all text-[13px] text-[#1a1a1a]">{value}</span>
    </div>
  )
}

function OfflineStatusFilter({
  value,
  onChange,
}: {
  value: OfflineMessageListStatus
  onChange: (status: OfflineMessageListStatus) => void
}) {
  const { locale } = useLocaleStore()
  const options: OfflineMessageListStatus[] = ['all', 'pending', 'converted', 'archived']

  return (
    <div className="border-b border-border bg-[#FAFAFA] px-3 py-2">
      <div className="grid grid-cols-2 gap-1.5">
        {options.map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => onChange(status)}
            className={cn(
              'rounded-md border px-2 py-1.5 text-xs font-medium transition-colors',
              value === status
                ? 'border-border bg-background text-foreground shadow-sm'
                : 'border-transparent text-muted-foreground hover:bg-background hover:text-foreground',
            )}
          >
            {status === 'all' ? (locale === 'zh' ? '全部' : 'All') : statusLabel(status, locale)}
          </button>
        ))}
      </div>
    </div>
  )
}

function getFieldIdentity(field: UnifiedField): string {
  return field.key ?? `custom:${field.id ?? field.name}`
}

function getSystemKey(field: UnifiedField): keyof User | null {
  if (field.source === 'custom') return null
  if (!field.key) return null
  return SYSTEM_KEY_ALIAS[field.key] ?? (field.key as keyof User)
}

function getFieldRawValue(user: User, field: UnifiedField): unknown {
  const systemKey = getSystemKey(field)
  if (systemKey) return user[systemKey]
  if (field.key) return user.custom_fields?.[field.key] ?? (field.id != null ? user.custom_fields?.[String(field.id)] : null)
  if (field.id != null) return user.custom_fields?.[String(field.id)] ?? null
  return null
}

export function OfflineMessagePanel({
  status,
  onAssigned,
  onArchived,
  readOnly = false,
  agentStatus = null,
  socket = null,
  showStatusFilter = false,
}: Props) {
  const [activeStatus, setActiveStatus] = useState<OfflineMessageListStatus>(status)
  const listQuery = useOfflineMessages({ status: activeStatus })
  const items = listQuery.data?.items ?? []
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const skipAutoSelectRef = useRef(false)
  const selectedExists = useMemo(
    () => items.some((item) => item.id === selectedId),
    [items, selectedId],
  )

  useEffect(() => {
    setActiveStatus(status)
  }, [status])

  useEffect(() => {
    setSelectedId(null)
    skipAutoSelectRef.current = false
  }, [activeStatus])

  useEffect(() => {
    if (selectedId && selectedExists) return
    if (skipAutoSelectRef.current) {
      skipAutoSelectRef.current = false
      return
    }
    setSelectedId(items[0]?.id ?? null)
  }, [items, selectedExists, selectedId])

  const handleAssigned = useCallback(
    (response: OfflineMessageConvertResponse, offlineMessageId: number) => {
      const nextId = getNextPendingOfflineMessageId(items, offlineMessageId)
      skipAutoSelectRef.current = nextId == null
      setSelectedId(nextId)
      onAssigned?.(response, offlineMessageId)
    },
    [items, onAssigned],
  )

  const handleArchived = useCallback(
    (response: OfflineMessageArchiveResponse, offlineMessageId: number) => {
      const nextId = getNextPendingOfflineMessageId(items, offlineMessageId)
      skipAutoSelectRef.current = nextId == null
      setSelectedId(nextId)
      onArchived?.(response, offlineMessageId)
    },
    [items, onArchived],
  )

  return (
    <div className="flex h-full min-h-0 bg-white">
      <aside className="flex w-[320px] shrink-0 flex-col border-r border-border bg-[#FAFAFA]">
        {showStatusFilter && (
          <OfflineStatusFilter
            value={activeStatus}
            onChange={setActiveStatus}
          />
        )}
        <OfflineMessageListSidebar
          status={activeStatus}
          items={items}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={listQuery.isLoading}
          onRefresh={() => void listQuery.refetch()}
          onAssigned={handleAssigned}
          readOnly={readOnly}
          agentStatus={agentStatus}
        />
      </aside>
      <OfflineMessageDetailPanel
        selectedId={selectedId}
        onAssigned={handleAssigned}
        onArchived={handleArchived}
        readOnly={readOnly}
        agentStatus={agentStatus}
        socket={socket}
      />
    </div>
  )
}
