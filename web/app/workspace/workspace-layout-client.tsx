'use client'

import { useMemo, useState, useEffect, type ComponentType } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  IconAddressBook,
  IconBook2,
  IconCalendarStats,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconPhone,
  IconSchool,
  IconSend,
  IconSettings,
  IconTicket,
} from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useChatStore } from '@/context/chat-store'
import { useSocketStore } from '@/context/socket-store'
import { CallCenterProvider } from '@/context/call-center-runtime'
import { useRefreshCurrentUser } from '@/hooks/use-refresh-current-user'
import { useWorkspaceSocket } from '@/hooks/use-workspace-socket'
import { useApplyAccountLocale } from '@/hooks/use-apply-account-locale'
import {
  useConversations,
  conversationKeys,
  patchConversationListCache,
  prependConversationToListCache,
} from '@/service/use-conversations'
import { GlobalCallBar } from '@/app/components/features/call-center/global-call-bar'
import { ExportTaskEntry } from '@/app/components/features/export-task-entry'
import { NetworkMonitor } from '@/app/components/features/network-monitor'
import { UserDropdown } from '@/app/components/features/user-dropdown'
import { KnowledgeFloatingDrawer } from '@/app/components/features/knowledge/knowledge-floating-drawer'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  WORKSPACE_NAV_ITEMS,
  getWorkspaceRouteRule,
  isWorkspacePathMatch,
  type WorkspaceNavIconKey,
  type WorkspaceNavItem,
} from '@/config/workspace-permissions'
import {
  getDefaultAccessiblePath,
  getDefaultAdminPath,
  hasAnyPermission,
  hasAllPermissions,
  hasPermission,
} from '@/utils/permissions'
import type { Conversation, Message } from '@/models/conversation'
import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import { logAuthEvent } from '@/utils/auth-log'
import { adoptNewerTokenIfAny } from '@/utils/auth-session'
import {
  SESSION_EXPIRED_REASON,
  SESSION_REPLACED_REASON,
  redirectToSessionExpiredLogin,
  redirectToSessionReplacedLogin,
} from '@/utils/session-replacement'
import { useWorkspaceNotificationAlert } from '@/hooks/use-workspace-notification-alert'
import { useWorkspaceTitleBlink } from '@/hooks/use-workspace-title-blink'
import { CollaborationInvitationDialog } from '@/app/components/features/chat/collaboration-invitation-dialog'
import {
  conversationCollaborationKeys,
  setPendingCollaborationInvitationCache,
  usePendingCollaborationInvitations,
} from '@/service/use-conversation-collaboration'
import type { CollaborationInvitation } from '@/models/conversation-collaboration'
import { useCallControlOwnership } from '@/hooks/use-call-control-ownership'

const WORKSPACE_NAV_ICONS: Record<WorkspaceNavIconKey, ComponentType<{ size?: number; className?: string }>> = {
  tickets: IconTicket,
  chat: IconMessageCircle,
  call: IconPhone,
  engagement: IconSend,
  records: IconHistory,
  learning: IconSchool,
  scheduling: IconCalendarStats,
  contacts: IconAddressBook,
  knowledge: IconBook2,
}

function canAccessWorkspaceRoute(
  user: Parameters<typeof hasAnyPermission>[0],
  rule: ReturnType<typeof getWorkspaceRouteRule>,
) {
  if (!rule) return true
  if (rule.requireAll) return hasAllPermissions(user, rule.permissions)
  return hasAnyPermission(user, rule.permissions)
    || rule.permissionSets?.some((permissions) => hasAllPermissions(user, permissions))
}

function buildMessagePreview(msg: Message): string {
  if (msg.content_type === 'text' || msg.content_type === 'system') return msg.content
  if (isWelcomeLikeContentType(msg.content_type)) {
    return msg.content
      .replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .replace(/\s+/g, ' ')
      .trim() || '欢迎语'
  }
  if (msg.content_type === 'image') return '[图片]'
  if (msg.content_type === 'file') {
    try {
      const payload = JSON.parse(msg.content) as { name?: string }
      return payload.name ? `[附件] ${payload.name}` : '[附件]'
    } catch {
      return '[附件]'
    }
  }
  return `[${msg.content_type}]`
}

function formatUnreadCount(count: number): string {
  return count > 99 ? '99+' : String(count)
}

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { token, user } = useAuthStore()
  const { locale } = useLocaleStore()
  const queryClient = useQueryClient()
  const [mounted, setMounted] = useState(false)
  const { isRefreshing: authRefreshing } = useRefreshCurrentUser(mounted)
  useApplyAccountLocale()
  const isChatPage = pathname.startsWith('/workspace/chat')
  const showKnowledgeFloatingDrawer =
    hasPermission(user, 'knowledge.workspace.view') &&
    !pathname.startsWith('/workspace/chat') &&
    !pathname.startsWith('/workspace/knowledge')
  const canUseChat = hasPermission(user, 'chat.workspace.use')
  const canUseCall = hasPermission(user, 'call.workspace.use')
  const callOwnership = useCallControlOwnership(mounted && canUseCall && Boolean(token))
  const canViewCallRecords = hasPermission(user, 'call.record.view')
  const canRespondCollaboration = hasPermission(user, 'chat.conversation.collaboration.respond')
  // The workspace socket also carries call-center pushes and agent presence,
  // so agents who only work the phone must connect even without chat access.
  // Permission gaps heal themselves: once the refreshed user lands, this flips
  // and the connection effect re-runs — waiting on the refresh here would let a
  // failed one keep the agent offline indefinitely.
  const syncWorkspaceSocket = mounted && Boolean(token) && (canUseChat || canUseCall)
  const syncChatNotifications = syncWorkspaceSocket && canUseChat && !isChatPage
  const syncCollaborationInvitations = syncWorkspaceSocket && canUseChat && canRespondCollaboration
  const { data: convData } = useConversations({ enabled: syncChatNotifications })
  const pendingCollaborationInvitationsQuery = usePendingCollaborationInvitations(syncCollaborationInvitations)
  const pendingCollaborationInvitation = pendingCollaborationInvitationsQuery.data?.items[0] ?? null
  const { socket, authFailed, sessionReplaced } = useSocketStore()
  const {
    conversations,
    setConversations,
    selectConversation,
    setConversationScope,
    setMyConversationView,
    setWorkspaceChatTab,
    addConversation,
    updateConversation,
    removeConversation,
    addMessage,
  } = useChatStore()
  const { playSessionAlert } = useWorkspaceNotificationAlert()
  const totalUnreadCount = useMemo(
    () => conversations
      .filter((conv) => conv.viewer_relation !== 'peer')
      .reduce((sum, conv) => sum + Math.max(0, conv.unread_count || 0), 0),
    [conversations],
  )
  useWorkspaceTitleBlink({
    enabled: mounted && canUseChat,
    unreadCount: totalUnreadCount,
    locale,
  })
  const visibleNavItems: WorkspaceNavItem[] = useMemo(
    () => WORKSPACE_NAV_ITEMS.filter((item) => (
      hasAnyPermission(user, item.permissions)
      || item.permissionSets?.some((permissions) => hasAllPermissions(user, permissions))
    )),
    [user],
  )

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    if (mounted && !token) {
      router.replace('/login')
    }
  }, [mounted, token, router])

  useEffect(() => {
    if (!mounted || !token || !user || authRefreshing) return
    const routeRule = getWorkspaceRouteRule(pathname)
    if (!canAccessWorkspaceRoute(user, routeRule)) {
      router.replace(getDefaultAccessiblePath(user))
    }
  }, [authRefreshing, mounted, token, user, pathname, router])

  useEffect(() => {
    if (!authFailed) return

    // Prefer the token the socket actually rejected; memory may already have
    // been updated by a cross-tab storage listener before this effect runs.
    const staleToken =
      useSocketStore.getState().authFailureToken ?? useAuthStore.getState().token
    if (adoptNewerTokenIfAny(staleToken)) {
      void logAuthEvent('session_clear_skipped', { trigger: 'socket_auth_failed' }, { immediate: true })
      useSocketStore.setState({
        authFailed: false,
        sessionReplaced: false,
        authFailureToken: null,
      })
      return
    }

    // Always hard-navigate with an honest reason. clearAuth() + soft
    // replace('/login') races the notice URL and can flash a bare login page.
    const redirectReason = sessionReplaced ? SESSION_REPLACED_REASON : SESSION_EXPIRED_REASON
    void logAuthEvent(
      'session_cleared',
      {
        trigger: 'socket_auth_failed',
        redirect_reason: redirectReason,
        session_replaced: sessionReplaced,
      },
      { immediate: true },
    ).then(() => {
      if (sessionReplaced) {
        redirectToSessionReplacedLogin()
      } else {
        redirectToSessionExpiredLogin()
      }
    })
  }, [authFailed, sessionReplaced])

  useWorkspaceSocket(syncWorkspaceSocket, token)

  useEffect(() => {
    if (syncChatNotifications && convData?.items) {
      setConversations(convData.items)
    }
  }, [syncChatNotifications, convData, setConversations])

  useEffect(() => {
    if (!syncChatNotifications && !syncCollaborationInvitations) return

    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return
      if (syncChatNotifications) {
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
      }
      if (syncCollaborationInvitations) {
        queryClient.invalidateQueries({ queryKey: conversationCollaborationKeys.pending() })
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [syncChatNotifications, syncCollaborationInvitations, queryClient])

  useEffect(() => {
    if (!syncChatNotifications || !socket) return

    const handleConnect = () => {
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
    }

    socket.on('connect', handleConnect)
    return () => {
      socket.off('connect', handleConnect)
    }
  }, [syncChatNotifications, socket, queryClient])

  useEffect(() => {
    if (!syncCollaborationInvitations || !socket) return

    const handleConnect = () => {
      queryClient.invalidateQueries({ queryKey: conversationCollaborationKeys.pending() })
    }

    const handleCollaborationInvitationReceived = (invitation?: CollaborationInvitation) => {
      playSessionAlert()
      if (invitation) {
        setPendingCollaborationInvitationCache(queryClient, invitation)
      }
      queryClient.invalidateQueries({ queryKey: conversationCollaborationKeys.pending() })
    }

    const handleCollaborationInvitationUpdated = (invitation?: CollaborationInvitation) => {
      if (invitation) {
        setPendingCollaborationInvitationCache(queryClient, invitation)
      }
      queryClient.invalidateQueries({ queryKey: conversationCollaborationKeys.pending() })
      queryClient.invalidateQueries({ queryKey: conversationCollaborationKeys.all })
    }

    socket.on('connect', handleConnect)
    socket.on('collaboration_invitation_received', handleCollaborationInvitationReceived)
    socket.on('collaboration_invitation_updated', handleCollaborationInvitationUpdated)

    return () => {
      socket.off('connect', handleConnect)
      socket.off('collaboration_invitation_received', handleCollaborationInvitationReceived)
      socket.off('collaboration_invitation_updated', handleCollaborationInvitationUpdated)
    }
  }, [syncCollaborationInvitations, socket, queryClient, playSessionAlert])

  useEffect(() => {
    if (!syncChatNotifications || !socket) return

    const handleNewConversation = (data: { conversation_id: number; visitor: Conversation['visitor'] }) => {
      playSessionAlert()
      const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
      fetch(`${apiBase}v1/conversations/${data.conversation_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((conv: Conversation) => {
          // Only enqueue + light the unread badge. Auto-selecting here would
          // mark the conversation read and drop the badge the agent needs to
          // notice a new assignment from another page.
          addConversation(conv)
          // Keep the HTTP list cache in sync so navigating to the chat page
          // (which replaces the store from this cache) does not drop the new
          // conversation before the next poll.
          prependConversationToListCache(queryClient, conv)
        })
        .catch(() => {
          queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
        })
    }

    const handleNewMessage = (msg: Message) => {
      addMessage(msg.conversation_id, msg)
      const preview = buildMessagePreview(msg)
      const updates: Partial<Conversation> = {
        last_message_at: msg.created_at,
        last_message_preview: preview.slice(0, 200),
      }

      if (msg.sender_type === 'visitor') {
        const conv = useChatStore.getState().conversations.find((item) => item.id === msg.conversation_id)
        if (conv) {
          updates.unread_count = conv.unread_count + 1
        } else {
          queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
        }
      }

      updateConversation(msg.conversation_id, updates)
      patchConversationListCache(queryClient, msg.conversation_id, updates)
    }

    const handleConversationEnded = (data: { conversation_id: number }) => {
      removeConversation(data.conversation_id)
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
    }

    const handleConversationUpdated = (data: {
      conversation_id: number
      last_message_preview?: string
      last_message_at?: string
      unread_count?: number
    }) => {
      const updates: Partial<Conversation> = {}
      if (data.last_message_preview !== undefined) updates.last_message_preview = data.last_message_preview
      if (data.last_message_at !== undefined) updates.last_message_at = data.last_message_at
      if (data.unread_count !== undefined) {
        updates.unread_count = data.unread_count
      }
      updateConversation(data.conversation_id, updates)
      patchConversationListCache(queryClient, data.conversation_id, updates)
    }

    const handleConversationTransferred = (data: {
      conversation_id: number
      from_agent_id: number | null
      to_agent_id: number
      conversation?: Conversation
    }) => {
      const me = useAuthStore.getState().user?.id
      if (data.from_agent_id != null && data.from_agent_id === me) {
        removeConversation(data.conversation_id)
      }
      if (data.to_agent_id === me) {
        playSessionAlert()
        if (data.conversation) {
          addConversation(data.conversation)
          prependConversationToListCache(queryClient, data.conversation)
        } else {
          const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
          fetch(`${apiBase}v1/conversations/${data.conversation_id}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
            .then((r) => r.json())
            .then((conv: Conversation) => {
              addConversation(conv)
              prependConversationToListCache(queryClient, conv)
            })
            .catch(() => {
              queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
            })
        }
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
      }
    }

    socket.on('new_conversation', handleNewConversation)
    socket.on('new_message', handleNewMessage)
    socket.on('conversation_ended', handleConversationEnded)
    socket.on('conversation_updated', handleConversationUpdated)
    socket.on('conversation_transferred', handleConversationTransferred)

    return () => {
      socket.off('new_conversation', handleNewConversation)
      socket.off('new_message', handleNewMessage)
      socket.off('conversation_ended', handleConversationEnded)
      socket.off('conversation_updated', handleConversationUpdated)
      socket.off('conversation_transferred', handleConversationTransferred)
    }
  }, [
    syncChatNotifications,
    socket,
    token,
    addConversation,
    addMessage,
    updateConversation,
    removeConversation,
    playSessionAlert,
    queryClient,
  ])

  if (!mounted || authRefreshing || !token || !user) return null
  const routeRule = getWorkspaceRouteRule(pathname)
  if (!canAccessWorkspaceRoute(user, routeRule)) return null
  if (visibleNavItems.length === 0) return null

  const workspaceShell = (
    <div className="flex h-screen">
        {/* Sidebar — full height icon navigation */}
        <aside className="relative z-30 flex w-16 shrink-0 flex-col justify-between border-r border-[#E5E5E5] bg-[#F5F5F5] py-4">
        {/* Top: Logo + Nav — 2.1 pen: Sidebar 64px #F5F5F5 */}
        <div className="flex flex-col items-center gap-4">
          {/* Logo */}
          <div className="flex h-12 w-full items-center justify-center">
            <IconHeadset size={28} className="text-[#1a1a1a]" />
          </div>

          {/* Nav items */}
          <nav className="flex flex-col items-center gap-1">
            {visibleNavItems.map((item) => {
              const active = isWorkspacePathMatch(pathname, item.href)
                || item.activePrefixes?.some((prefix) => isWorkspacePathMatch(pathname, prefix))
              const Icon = WORKSPACE_NAV_ICONS[item.iconKey]
              const className = cn(
                'group relative flex h-11 w-11 items-center justify-center rounded-xl transition-colors',
                active
                  ? 'bg-[#E5E5E5] text-[#1a1a1a]'
                  : 'text-[#999999] hover:text-[#1a1a1a]'
              )
              const content = (
                <>
                  <Icon size={22} />
                  {!active && item.href === '/workspace/chat' && totalUnreadCount > 0 && (
                    <span className="absolute right-0.5 top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-[#F5F5F5]">
                      {formatUnreadCount(totalUnreadCount)}
                    </span>
                  )}
                  {/* Tooltip */}
                  <span className="pointer-events-none absolute left-full ml-3 whitespace-nowrap rounded-md bg-foreground px-2.5 py-1.5 text-xs text-background opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                    {t(item.labelKey, locale)}
                  </span>
                </>
              )
              if (item.openInNewTab) {
                return (
                  <a
                    key={item.href}
                    href={item.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={t(item.labelKey, locale)}
                    className={className}
                  >
                    {content}
                  </a>
                )
              }
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={t(item.labelKey, locale)}
                  className={className}
                >
                  {content}
                </Link>
              )
            })}
          </nav>
        </div>

        {/* Bottom: Management backend (admin only) — use /employees, not / (root redirects to /login) */}
        <div className="flex flex-col items-center gap-1">
          {hasPermission(user, 'admin.access') && (
            <a
              href={getDefaultAdminPath(user)}
              target="_blank"
              rel="noopener noreferrer"
              title={t('ws.nav.admin', locale)}
              className="group relative flex h-11 w-11 items-center justify-center rounded-xl text-[#999999] transition-colors hover:text-[#1a1a1a]"
            >
              <IconSettings size={22} />
              <span className="pointer-events-none absolute left-full ml-3 whitespace-nowrap rounded-md bg-foreground px-2.5 py-1.5 text-xs text-background opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                {t('ws.nav.admin', locale)}
              </span>
            </a>
          )}
        </div>
        </aside>

        {/* Right Panel */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Top Bar. min-h-14 (not h-14): the global call bar grows this header
              downward when expanded. */}
          <header className="flex min-h-14 shrink-0 items-start gap-3 border-b border-border bg-white px-6">
            <div className="flex min-w-0 flex-1 justify-center py-1">
              {canUseCall && <GlobalCallBar hidden={pathname.startsWith('/workspace/call')} />}
            </div>
            <div className="flex shrink-0 items-center gap-2 py-2.5">
              <NetworkMonitor />
              <ExportTaskEntry />
              <UserDropdown />
            </div>
          </header>

          {/* Content Area */}
          <main className="flex-1 overflow-y-auto bg-surface">
            {children}
          </main>
          <CollaborationInvitationDialog
            invitation={pendingCollaborationInvitation}
            onAccepted={(conversation) => {
              addConversation(conversation)
              selectConversation(conversation.id)
              setConversationScope('my')
              setMyConversationView('collaborating')
              setWorkspaceChatTab('messages')
              queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
              router.push('/workspace/chat')
            }}
            onDeclined={() => {
              queryClient.invalidateQueries({ queryKey: conversationCollaborationKeys.pending() })
            }}
          />
          {showKnowledgeFloatingDrawer && <KnowledgeFloatingDrawer />}
        </div>
    </div>
  )

  if (!canUseCall) return workspaceShell

  return (
    <CallCenterProvider
      recordsEnabled={canViewCallRecords}
      controlEnabled={callOwnership.isOwner}
    >
      {callOwnership.hasControlConflict ? (
        <div className="fixed left-1/2 top-1/2 z-[70] flex -translate-x-1/2 -translate-y-1/2 items-center gap-3 rounded-lg border border-warning/30 bg-background px-4 py-3 text-sm shadow-lg">
          <span>{locale === 'zh' ? '通话正在另一窗口处理' : 'Call is controlled in another window'}</span>
          <button
            type="button"
            onClick={() => {
              const confirmed = window.confirm(
                locale === 'zh' ? '确认在此窗口接管通话控制？' : 'Take call control in this window?',
              )
              if (confirmed) void callOwnership.takeover()
            }}
            className="rounded-md bg-primary px-3 py-1.5 font-medium text-primary-foreground"
          >
            {locale === 'zh' ? '在此处接管' : 'Take over'}
          </button>
        </div>
      ) : null}
      {workspaceShell}
    </CallCenterProvider>
  )
}
