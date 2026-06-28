'use client'

import { useState, useRef, useEffect, useMemo, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { IconChevronDown, IconLoader2, IconLock, IconPinned, IconRefresh, IconSearch } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { avatarBackgroundForName, singleAvatarLetter } from '@/lib/avatar-fallback'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { conversationKeys, setVisitorWebStatusQueryData, useUpdateAgentStatus, useVisitorWebStatus } from '@/service/use-conversations'
import { hasPermission } from '@/utils/permissions'
import { ReceptionStatsCapsule } from '@/app/components/features/chat/max-concurrent-popover'
import { t } from '@/utils/i18n'
import type { ConversationListScope } from '@/service/use-conversations'
import type { DataScopeValue } from '@/utils/permissions'
import type { Conversation, AgentStatus, AgentStats, VisitorWebStatusResponse } from '@/models/conversation'
import type { Socket } from 'socket.io-client'

export type ConversationPanelTab = ConversationListScope | 'offline' | 'queue'
export type MyConversationView = 'current' | 'collaborating' | 'history'

type Props = {
  conversations: Conversation[]
  selectedId: number | null
  onSelect: (id: number) => void
  agentStatus: AgentStatus | null
  agentStats: AgentStats | null
  scope: ConversationListScope
  onScopeChange: (scope: ConversationListScope) => void
  myView: MyConversationView
  onMyViewChange: (view: MyConversationView) => void
  activeTab: ConversationPanelTab
  onTabChange: (tab: ConversationPanelTab) => void
  canPeerTab: boolean
  canOfflineTab: boolean
  canQueueTab: boolean
  peerConversationScope: DataScopeValue | null
  myUnreadTotal?: number | null
  offlineTotal?: number | null
  queueTotal?: number | null
  loading: boolean
  onRefresh: () => void
  onTogglePin?: (conversation: Conversation) => void
  pinningConversationId?: number | null
  historyHasMore?: boolean
  historyLoadingMore?: boolean
  onHistoryLoadMore?: () => void
  hasCollaboratingConversations?: boolean
  offlineList?: ReactNode
  queueList?: ReactNode
  socket: Socket | null
}

const STATUS_OPTIONS = [
  { value: 'online', colorClass: 'bg-success', labelKey: 'ws.status.online' },
  { value: 'busy', colorClass: 'bg-warning', labelKey: 'ws.status.busy' },
  { value: 'offline', colorClass: 'bg-muted-foreground', labelKey: 'ws.status.offline' },
] as const

function formatTime(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) {
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  }
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatHistoryTime(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const time = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  const now = new Date()
  if (d.toDateString() === now.toDateString()) return time
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${time}`
}

function conversationStartTimestamp(conv: Conversation): number {
  const value = conv.started_at || conv.created_at
  if (!value) return Number.MAX_SAFE_INTEGER
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? Number.MAX_SAFE_INTEGER : timestamp
}

function pinnedTimestamp(conv: Conversation): number {
  const timestamp = new Date(conv.pinned_at || '').getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function sortPinnedConversations(conversations: Conversation[]): Conversation[] {
  return conversations
    .map((conversation, index) => ({ conversation, index }))
    .sort((a, b) => {
      const aPinned = Boolean(a.conversation.is_pinned)
      const bPinned = Boolean(b.conversation.is_pinned)
      if (aPinned !== bPinned) return aPinned ? -1 : 1
      if (aPinned && bPinned) {
        const diff = pinnedTimestamp(b.conversation) - pinnedTimestamp(a.conversation)
        if (diff !== 0) return diff
      }
      return a.index - b.index
    })
    .map((item) => item.conversation)
}

function shouldShowVisitorWebStatus(conversation: Conversation): boolean {
  return (
    String(conversation.channel?.channel_type || '').toLowerCase() === 'web'
    && Boolean(conversation.visitor?.external_id)
  )
}

function VisitorConversationAvatar({
  conversation,
  showStatus,
}: {
  conversation: Conversation
  showStatus: boolean
}) {
  const { locale } = useLocaleStore()
  const visible = showStatus && shouldShowVisitorWebStatus(conversation)
  const statusQuery = useVisitorWebStatus(conversation.id, {
    enabled: visible,
    refetchInterval: 10_000,
  })
  const status = statusQuery.isError ? 'unknown' : statusQuery.data?.status
  const canDisplay = statusQuery.data?.can_display ?? true
  const showDot = visible && canDisplay && (status === 'online' || status === 'offline')
  const title = status === 'online'
    ? t('ws.chat.visitorWebStatusOnline', locale)
    : t('ws.chat.visitorWebStatusOffline', locale)

  return (
    <div className="relative h-10 w-10 shrink-0">
      <div
        className="flex h-10 w-10 items-center justify-center rounded-full text-base font-medium text-white"
        style={{ backgroundColor: conversation.visitor?.avatar_color || '#4A8C5C' }}
      >
        {(conversation.visitor?.name || '访').charAt(0)}
      </div>
      {showDot && (
        <span
          aria-label={title}
          title={title}
          className={cn(
            'absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-[#F5F5F5]',
            status === 'online' ? 'bg-[#22C55E]' : 'bg-[#D4D4D4]',
          )}
        />
      )}
    </div>
  )
}

export function ConversationListPanel({
  conversations,
  selectedId,
  onSelect,
  agentStatus,
  agentStats,
  scope,
  onScopeChange,
  myView,
  onMyViewChange,
  activeTab,
  onTabChange,
  canPeerTab,
  canOfflineTab,
  canQueueTab,
  peerConversationScope,
  myUnreadTotal,
  offlineTotal,
  queueTotal,
  loading,
  onRefresh,
  onTogglePin,
  pinningConversationId = null,
  historyHasMore,
  historyLoadingMore,
  onHistoryLoadMore,
  hasCollaboratingConversations = false,
  offlineList,
  queueList,
  socket,
}: Props) {
  const { locale } = useLocaleStore()
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false)
  const [maxConcurrentOpen, setMaxConcurrentOpen] = useState(false)
  const [search, setSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)
  const updateStatus = useUpdateAgentStatus()

  const currentStatus = agentStatus?.status || 'offline'
  const currentOption = STATUS_OPTIONS.find((o) => o.value === currentStatus) || STATUS_OPTIONS[2]
  const searchTerm = search.trim().toLowerCase()
  const isMyTab = activeTab === 'my'
  const isHistoryView = isMyTab && myView === 'history'
  const isCollaboratingView = isMyTab && myView === 'collaborating'
  const filteredConversations = searchTerm
    ? conversations.filter((conv) => {
      const values = [
        conv.visitor?.name,
        conv.visitor?.external_id,
        conv.agent?.display_name,
        conv.agent?.name,
        conv.channel?.name,
        conv.channel?.channel_type,
        scope === 'peers' ? null : conv.last_message_preview,
      ]
      return values.some((value) => value?.toLowerCase().includes(searchTerm))
    })
    : conversations
  const baseDisplayedConversations = scope === 'peers' && !isHistoryView
    ? [...filteredConversations].sort(
      (a, b) => conversationStartTimestamp(a) - conversationStartTimestamp(b) || a.id - b.id,
    )
    : filteredConversations
  const displayedConversations = isHistoryView
    ? baseDisplayedConversations
    : sortPinnedConversations(baseDisplayedConversations)
  const scopeLabel = peerConversationScope === 'all'
    ? t('ws.chat.scopeAll', locale)
    : t('ws.chat.scopeGroup', locale)
  const emptyText = isHistoryView
    ? t('ws.chat.noHistoryConversations', locale)
    : isCollaboratingView
    ? t('ws.chat.noCollaboratingConversations', locale)
    : scope === 'peers'
    ? t('ws.chat.noPeerConversations', locale)
    : t('ws.chat.noMyConversations', locale)
  const tabCount = 1 + (canPeerTab ? 1 : 0) + (canOfflineTab ? 1 : 0) + (canQueueTab ? 1 : 0)
  const tabGridClass = tabCount >= 4 ? 'grid-cols-4' : tabCount === 3 ? 'grid-cols-3' : tabCount === 2 ? 'grid-cols-2' : 'grid-cols-1'
  const isOfflineTab = activeTab === 'offline'
  const isQueueTab = activeTab === 'queue'
  const myUnreadCount = Math.max(0, myUnreadTotal ?? 0)
  const canEditMaxConcurrent = hasPermission(user, 'chat.workspace.max_concurrent.edit')
  const visitorStatusConversationIds = useMemo(
    () => conversations.filter(shouldShowVisitorWebStatus).map((conv) => conv.id),
    [conversations],
  )

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setStatusDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  useEffect(() => {
    if (!statusDropdownOpen) return
    setMaxConcurrentOpen(false)
  }, [statusDropdownOpen])

  useEffect(() => {
    if (!socket) return

    const handleStatusUpdated = (payload: VisitorWebStatusResponse) => {
      setVisitorWebStatusQueryData(queryClient, payload)
    }

    const handleConnect = () => {
      visitorStatusConversationIds.forEach((conversationId) => {
        queryClient.invalidateQueries({
          queryKey: conversationKeys.visitorWebStatus(conversationId),
        })
      })
    }

    socket.on('visitor_web_status_updated', handleStatusUpdated)
    socket.on('connect', handleConnect)
    return () => {
      socket.off('visitor_web_status_updated', handleStatusUpdated)
      socket.off('connect', handleConnect)
    }
  }, [queryClient, socket, visitorStatusConversationIds])

  return (
    <div className="flex w-[280px] shrink-0 flex-col border-r border-[#E5E5E5] bg-[#F5F5F5]">
      {/* 客服状态区 — 2.1 pen: height 56, px 20 */}
      <div className="flex h-14 shrink-0 items-center justify-between px-5">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="relative shrink-0" ref={dropdownRef}>
            <button
              onClick={() => {
                setMaxConcurrentOpen(false)
                setStatusDropdownOpen(!statusDropdownOpen)
              }}
              className="flex items-center gap-1.5 rounded-md py-0.5 text-[12px] font-medium transition-colors hover:bg-black/[0.04]"
            >
              <span
                className={cn(
                  'h-2 w-2 rounded-full',
                  currentStatus === 'online' && 'bg-[#22C55E]',
                  currentStatus === 'busy' && 'bg-amber-500',
                  currentStatus === 'offline' && 'bg-neutral-400',
                )}
              />
              <span
                className={cn(
                  currentStatus === 'online' && 'text-[#22C55E]',
                  currentStatus !== 'online' && 'text-[#737373]',
                )}
              >
                {t(currentOption.labelKey, locale)}
              </span>
              <IconChevronDown size={14} className="text-[#999999]" />
            </button>
            {statusDropdownOpen && (
              <div className="absolute left-0 top-full z-50 mt-1 w-32 rounded-lg border border-[#E5E5E5] bg-white py-1 shadow-lg">
                {STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => {
                      updateStatus.mutate(opt.value)
                      setStatusDropdownOpen(false)
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors hover:bg-[#F5F5F5]',
                      currentStatus === opt.value && 'font-medium',
                    )}
                  >
                    <span className={cn('h-2 w-2 rounded-full', opt.colorClass)} />
                    {t(opt.labelKey, locale)}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        {agentStats && (
          <ReceptionStatsCapsule
            agentStats={agentStats}
            editable={canEditMaxConcurrent}
            maxConcurrentOpen={maxConcurrentOpen}
            onMaxConcurrentOpenChange={(open) => {
              if (open) setStatusDropdownOpen(false)
              setMaxConcurrentOpen(open)
            }}
          />
        )}
      </div>

      <div className="shrink-0 border-t border-[#E5E5E5] px-2 pb-2 pt-1">
        <div
          role="tablist"
          aria-label={t('ws.chat.conversationTabs', locale)}
          className={cn('grid gap-1 rounded-lg bg-[#EBEBEB] p-1', tabGridClass)}
        >
          <button
            role="tab"
            aria-selected={activeTab === 'my'}
            type="button"
            onClick={() => {
              onScopeChange('my')
              onTabChange('my')
            }}
            className={cn(
              'relative h-8 rounded-md px-2 text-[13px] font-medium transition-colors',
              activeTab === 'my' ? 'bg-white text-[#1a1a1a] shadow-sm' : 'text-[#737373] hover:text-[#1a1a1a]',
            )}
          >
            {t('ws.chat.tabMy', locale)}
            {myUnreadCount > 0 ? (
              <span
                title={locale === 'zh' ? '未读消息' : 'Unread messages'}
                className="absolute right-1 top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-white"
              >
                {myUnreadCount > 99 ? '99+' : myUnreadCount}
              </span>
            ) : null}
          </button>
          {canPeerTab ? (
            <button
              role="tab"
              aria-selected={activeTab === 'peers'}
              type="button"
              onClick={() => {
                onScopeChange('peers')
                onTabChange('peers')
              }}
              className={cn(
                'h-8 rounded-md px-2 text-[13px] font-medium transition-colors',
                activeTab === 'peers' ? 'bg-white text-[#1a1a1a] shadow-sm' : 'text-[#737373] hover:text-[#1a1a1a]',
              )}
            >
              {t('ws.chat.tabPeers', locale)}
            </button>
          ) : null}
          {canOfflineTab ? (
            <button
              role="tab"
              aria-selected={activeTab === 'offline'}
              type="button"
              onClick={() => onTabChange('offline')}
              className={cn(
                'h-8 rounded-md px-2 text-[13px] font-medium transition-colors',
                activeTab === 'offline' ? 'bg-white text-[#1a1a1a] shadow-sm' : 'text-[#737373] hover:text-[#1a1a1a]',
              )}
            >
              {locale === 'zh' ? '留言' : 'Offline'}
              {offlineTotal ? <span className="ml-1 text-[11px] text-[#999999]">{offlineTotal}</span> : null}
            </button>
          ) : null}
          {canQueueTab ? (
            <button
              role="tab"
              aria-selected={activeTab === 'queue'}
              type="button"
              onClick={() => onTabChange('queue')}
              className={cn(
                'h-8 rounded-md px-2 text-[13px] font-medium transition-colors',
                activeTab === 'queue' ? 'bg-white text-[#1a1a1a] shadow-sm' : 'text-[#737373] hover:text-[#1a1a1a]',
              )}
            >
              {t('ws.chat.tabQueue', locale)}
              {queueTotal ? <span className="ml-1 text-[11px] text-[#999999]">{queueTotal > 99 ? '99+' : queueTotal}</span> : null}
            </button>
          ) : null}
        </div>

        {isMyTab && (
          <div
            className="mt-2 flex items-center text-[12px] font-medium"
            role="tablist"
            aria-label={t('ws.chat.myConversationViews', locale)}
          >
            <button
              type="button"
              role="tab"
              aria-selected={myView === 'current'}
              onClick={() => onMyViewChange('current')}
              className={cn(
                'px-1.5 py-1 transition-colors',
                myView === 'current'
                  ? 'font-semibold text-[#1a1a1a]'
                  : 'text-[#737373] hover:text-[#1a1a1a]',
              )}
            >
              {t('ws.chat.myCurrent', locale)}
            </button>
            <span className="text-[#C7C7C7]">|</span>
            {hasCollaboratingConversations && (
              <>
                <button
                  type="button"
                  role="tab"
                  aria-selected={myView === 'collaborating'}
                  onClick={() => onMyViewChange('collaborating')}
                  className={cn(
                    'px-1.5 py-1 transition-colors',
                    myView === 'collaborating'
                      ? 'font-semibold text-[#1a1a1a]'
                      : 'text-[#737373] hover:text-[#1a1a1a]',
                  )}
                >
                  {t('ws.chat.myCollaborating', locale)}
                </button>
                <span className="text-[#C7C7C7]">|</span>
              </>
            )}
            <button
              type="button"
              role="tab"
              aria-selected={myView === 'history'}
              onClick={() => onMyViewChange('history')}
              className={cn(
                'px-1.5 py-1 transition-colors',
                myView === 'history'
                  ? 'font-semibold text-[#1a1a1a]'
                  : 'text-[#737373] hover:text-[#1a1a1a]',
              )}
            >
              {t('ws.chat.myHistory', locale)}
            </button>
            {isHistoryView && (
              <span className="ml-auto truncate pl-2 text-[11px] font-normal text-[#999999]">
                {t('ws.chat.last24Hours', locale)}
              </span>
            )}
          </div>
        )}

        {!isOfflineTab && !isQueueTab && (
          <div className="mt-2 flex items-center gap-2">
            <div className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md border border-[#E5E5E5] bg-white px-2">
              <IconSearch size={14} className="shrink-0 text-[#999999]" stroke={1.7} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={isHistoryView ? t('ws.chat.historySearchPlaceholder', locale) : t('ws.chat.searchPlaceholder', locale)}
                className="h-8 min-w-0 flex-1 bg-transparent text-[12px] text-[#1a1a1a] outline-none placeholder:text-[#BBBBBB]"
              />
            </div>
            <button
              type="button"
              onClick={onRefresh}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[#E5E5E5] bg-white text-[#737373] transition-colors hover:bg-[#F5F5F5] hover:text-[#1a1a1a]"
              aria-label={t('ws.chat.refreshList', locale)}
              title={t('ws.chat.refreshList', locale)}
            >
              <IconRefresh size={16} stroke={1.7} className={cn(loading && 'animate-spin')} />
            </button>
          </div>
        )}

        {activeTab === 'peers' && (
          <div className="mt-2 truncate rounded-md bg-white px-2 py-1 text-[11px] text-[#737373]">
            {t('ws.chat.peerScope', locale, { scope: scopeLabel })}
          </div>
        )}
      </div>

      {isOfflineTab ? (
        <div className="min-h-0 flex-1">{offlineList}</div>
      ) : isQueueTab ? (
        <div className="min-h-0 flex-1">{queueList}</div>
      ) : (
        <div className="flex-1 overflow-y-auto px-2 py-1">
          {displayedConversations.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <p className="px-4 text-center text-sm text-[#737373]">
                {searchTerm
                  ? isHistoryView ? t('ws.chat.noHistorySearchResults', locale) : t('ws.chat.noConversationSearchResults', locale)
                  : emptyText}
              </p>
            </div>
          ) : (
            <>
              {displayedConversations.map((conv) => {
                const selected = selectedId === conv.id
                const ownerName = conv.agent?.display_name || conv.agent?.name
                const peerAvatarName = ownerName || '?'
                const isCollaboratorConversation = conv.viewer_relation === 'collaborator'
                const pinLabel = conv.is_pinned
                  ? t('ws.chat.unpinConversation', locale)
                  : t('ws.chat.pinConversation', locale)
                const timeoutLockLabel = t('ws.chat.timeoutLocked', locale)
                const pinning = pinningConversationId === conv.id
                return (
                  <div
                    key={conv.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelect(conv.id)}
                    onKeyDown={(event) => {
                      if (event.target !== event.currentTarget) return
                      if (event.key !== 'Enter' && event.key !== ' ') return
                      event.preventDefault()
                      onSelect(conv.id)
                    }}
                    className={cn(
                      'group mb-1 flex min-h-[72px] w-full cursor-pointer items-center gap-3 rounded-[20px] px-4 py-2 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring',
                      selected
                        ? 'border border-[#E0E0E0] bg-[#FAFAFA]'
                        : 'border border-transparent hover:bg-white/60',
                    )}
                  >
                    {scope === 'peers' && !isHistoryView ? (
                      <div
                        className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full text-base font-medium text-white"
                        style={!conv.agent?.avatar ? { backgroundColor: avatarBackgroundForName(peerAvatarName) } : undefined}
                      >
                        {conv.agent?.avatar ? (
                          <img
                            src={conv.agent.avatar}
                            alt={peerAvatarName}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          singleAvatarLetter(peerAvatarName)
                        )}
                      </div>
                    ) : (
                      <VisitorConversationAvatar
                        conversation={conv}
                        showStatus={scope === 'my' && !isHistoryView}
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-1.5">
                          <span
                            className={cn(
                              'truncate text-sm text-[#1a1a1a]',
                              selected ? 'font-semibold' : 'font-medium',
                            )}
                          >
                            {conv.visitor?.name || `#${conv.id}`}
                          </span>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          {conv.is_timeout_locked && !isHistoryView && (
                            <span
                              className="flex h-6 w-6 items-center justify-center rounded-md text-primary"
                              aria-label={timeoutLockLabel}
                              title={timeoutLockLabel}
                            >
                              <IconLock size={14} stroke={1.8} />
                            </span>
                          )}
                          {onTogglePin && !isHistoryView && (
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation()
                                onTogglePin(conv)
                              }}
                              disabled={pinning}
                              className={cn(
                                'flex h-6 w-6 items-center justify-center rounded-md text-[#999999] opacity-0 transition-colors hover:bg-[#E8E8E8] hover:text-[#1a1a1a] focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100 group-focus-within:opacity-100 disabled:cursor-not-allowed disabled:opacity-60',
                                conv.is_pinned && 'text-primary opacity-100',
                                pinning && 'opacity-100',
                              )}
                              aria-label={pinLabel}
                              title={pinLabel}
                            >
                              {pinning ? (
                                <IconLoader2 size={14} stroke={1.8} className="animate-spin" />
                              ) : (
                                <IconPinned size={14} stroke={1.8} />
                              )}
                            </button>
                          )}
                          <span className="shrink-0 text-[12px] text-[#999999]">
                            {isHistoryView ? formatHistoryTime(conv.ended_at) : formatTime(conv.last_message_at)}
                          </span>
                        </div>
                      </div>
                      {isHistoryView ? (
                        <span className="mt-1 block truncate text-[13px] text-[#737373]">
                          {conv.last_message_preview || ''}
                        </span>
                      ) : (
                        <div className="mt-1 flex items-center justify-between gap-2">
                          <div className="min-w-0">
                            {(scope === 'peers' || isCollaboratorConversation) && ownerName && (
                              <div className="truncate text-[11px] text-[#999999]">
                                {t('ws.chat.handledBy', locale, { name: ownerName })}
                              </div>
                            )}
                            {scope !== 'peers' && !isCollaboratorConversation && (
                              <span className="block truncate text-[13px] text-[#737373]">
                                {conv.last_message_preview || ''}
                              </span>
                            )}
                          </div>
                          {isCollaboratorConversation ? (
                            <span className="shrink-0 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                              {t('ws.chat.collaboratingBadge', locale)}
                            </span>
                          ) : scope === 'peers' && conv.collaborated_by_current_user && (
                            <span className="shrink-0 rounded-full bg-[#E8E8E8] px-1.5 py-0.5 text-[10px] font-medium text-[#737373]">
                              {t('ws.chat.collaborated', locale)}
                            </span>
                          )}
                          {scope !== 'peers' && !isCollaboratorConversation && conv.unread_count > 0 && (
                            <span className="flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-white">
                              {conv.unread_count > 99 ? '99+' : conv.unread_count}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
              {isHistoryView && historyHasMore && (
                <button
                  type="button"
                  onClick={onHistoryLoadMore}
                  disabled={historyLoadingMore}
                  className="mx-auto my-2 flex h-8 items-center justify-center rounded-md px-3 text-[12px] font-medium text-[#737373] transition-colors hover:bg-white hover:text-[#1a1a1a] disabled:cursor-not-allowed disabled:text-[#BBBBBB]"
                >
                  {historyLoadingMore ? t('ws.chat.loadingMoreHistory', locale) : t('ws.chat.loadMoreHistory', locale)}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
