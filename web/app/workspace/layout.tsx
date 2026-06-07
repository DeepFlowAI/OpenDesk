'use client'

import { useMemo, useState, useEffect, type ComponentType } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  IconAddressBook,
  IconHeadset,
  IconHistory,
  IconMessageCircle,
  IconPhone,
  IconSettings,
  IconTicket,
} from '@tabler/icons-react'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useChatStore } from '@/context/chat-store'
import { useSocketStore } from '@/context/socket-store'
import { CallCenterProvider } from '@/context/call-center-runtime'
import {
  useConversations,
  conversationKeys,
  patchConversationListCache,
} from '@/service/use-conversations'
import { GlobalCallBar } from '@/app/components/features/call-center/global-call-bar'
import { UserDropdown } from '@/app/components/features/user-dropdown'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  WORKSPACE_NAV_ITEMS,
  getWorkspaceRouteRule,
  type WorkspaceNavIconKey,
} from '@/config/workspace-permissions'
import {
  getDefaultAccessiblePath,
  getDefaultAdminPath,
  hasAnyPermission,
  hasPermission,
} from '@/utils/permissions'
import type { Conversation, Message } from '@/models/conversation'

type NavItem = {
  labelKey: string
  href: string
  iconKey: WorkspaceNavIconKey
  permissions: string[]
}

const WORKSPACE_NAV_ICONS: Record<WorkspaceNavIconKey, ComponentType<{ size?: number; className?: string }>> = {
  tickets: IconTicket,
  chat: IconMessageCircle,
  call: IconPhone,
  records: IconHistory,
  contacts: IconAddressBook,
}

function buildMessagePreview(msg: Message): string {
  if (msg.content_type === 'text' || msg.content_type === 'system') return msg.content
  if (msg.content_type === 'welcome') {
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
  const isChatPage = pathname.startsWith('/workspace/chat')
  const canUseChat = hasPermission(user, 'chat.workspace.use')
  const syncChatNotifications = mounted && Boolean(token) && canUseChat && !isChatPage
  const { data: convData } = useConversations({ enabled: syncChatNotifications })
  const { socket, connected, connecting, connect } = useSocketStore()
  const {
    conversations,
    setConversations,
    addConversation,
    updateConversation,
    removeConversation,
    addMessage,
  } = useChatStore()
  const totalUnreadCount = useMemo(
    () => conversations.reduce((sum, conv) => sum + Math.max(0, conv.unread_count || 0), 0),
    [conversations],
  )
  const visibleNavItems: NavItem[] = useMemo(
    () => WORKSPACE_NAV_ITEMS.filter((item) => hasAnyPermission(user, item.permissions)),
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
    if (!mounted || !token || !user) return
    const routeRule = getWorkspaceRouteRule(pathname)
    if (routeRule && !hasAnyPermission(user, routeRule.permissions)) {
      router.replace(getDefaultAccessiblePath(user))
    }
  }, [mounted, token, user, pathname, router])

  useEffect(() => {
    if (syncChatNotifications && token && !connected && !connecting) {
      connect(token)
    }
  }, [syncChatNotifications, token, connected, connecting, connect])

  useEffect(() => {
    if (syncChatNotifications && convData?.items) {
      setConversations(convData.items)
    }
  }, [syncChatNotifications, convData, setConversations])

  useEffect(() => {
    if (!syncChatNotifications) return

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const sock = useSocketStore.getState().socket
        if (sock && !sock.connected) {
          sock.connect()
        }
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [syncChatNotifications, queryClient])

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
    if (!syncChatNotifications || !socket) return

    const handleNewConversation = (data: { conversation_id: number; visitor: Conversation['visitor'] }) => {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
      fetch(`${apiBase}v1/conversations/${data.conversation_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((conv: Conversation) => addConversation(conv))
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
        // Mirror chat-page logic: the conversation the agent is currently
        // viewing must never accumulate unread inside the workspace badge.
        const selected = useChatStore.getState().selectedConversationId
        updates.unread_count = data.conversation_id === selected ? 0 : data.unread_count
      }
      updateConversation(data.conversation_id, updates)
      patchConversationListCache(queryClient, data.conversation_id, updates)
    }

    socket.on('new_conversation', handleNewConversation)
    socket.on('new_message', handleNewMessage)
    socket.on('conversation_ended', handleConversationEnded)
    socket.on('conversation_updated', handleConversationUpdated)

    return () => {
      socket.off('new_conversation', handleNewConversation)
      socket.off('new_message', handleNewMessage)
      socket.off('conversation_ended', handleConversationEnded)
      socket.off('conversation_updated', handleConversationUpdated)
    }
  }, [
    syncChatNotifications,
    socket,
    token,
    addConversation,
    addMessage,
    updateConversation,
    removeConversation,
    queryClient,
  ])

  if (!mounted || !token || !user) return null
  const routeRule = getWorkspaceRouteRule(pathname)
  if (routeRule && !hasAnyPermission(user, routeRule.permissions)) return null
  if (visibleNavItems.length === 0) return null

  return (
    <CallCenterProvider>
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
              const active = pathname.startsWith(item.href)
              const Icon = WORKSPACE_NAV_ICONS[item.iconKey]
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={t(item.labelKey, locale)}
                  className={cn(
                    'group relative flex h-11 w-11 items-center justify-center rounded-xl transition-colors',
                    active
                      ? 'bg-[#E5E5E5] text-[#1a1a1a]'
                      : 'text-[#999999] hover:text-[#1a1a1a]'
                  )}
                >
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
          {/* Top Bar */}
          <header className="relative flex h-14 shrink-0 items-center justify-end border-b border-border bg-white px-6">
            <div className="absolute left-1/2 top-1/2 flex min-w-0 -translate-x-1/2 -translate-y-1/2 items-center justify-center">
              <GlobalCallBar hidden={pathname.startsWith('/workspace/call')} />
            </div>
            <UserDropdown />
          </header>

          {/* Content Area */}
          <main className="flex-1 overflow-y-auto bg-surface">
            {children}
          </main>
        </div>
      </div>
    </CallCenterProvider>
  )
}
