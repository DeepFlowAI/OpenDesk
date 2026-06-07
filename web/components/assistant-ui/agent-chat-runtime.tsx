'use client'

import {
  createContext,
  useContext,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react'
import {
  useExternalStoreRuntime,
  AssistantRuntimeProvider,
  type ThreadMessageLike,
  type AppendMessage,
} from '@assistant-ui/react'
import { useChatStore } from '@/context/chat-store'
import { useAuthStore } from '@/context/auth-store'
import { uploadAgentConversationFile } from '@/service/use-conversation-files'
import type { Message, Conversation, WorkspaceConversationHistoryItem } from '@/models/conversation'
import type { SatisfactionConversationState } from '@/models/satisfaction-survey'
import type { Socket } from 'socket.io-client'

// ─── Config context ──────────────────────────────────────────────

export type AgentChatConfigValue = {
  conversation: Conversation
  locale: string
  isClosed: boolean
  isTyping: boolean
  visitorTypingContent: string
  hasMore: boolean
  loadingMore: boolean
  historyAvailable: boolean
  historyConversations: WorkspaceConversationHistoryItem[]
  historyHasMore: boolean
  historyLoading: boolean
  historyLoaded: boolean
  historyError: boolean
  historyLimitReached: boolean
  onLoadMore: () => void
  onLoadHistory: (beforeId?: number) => Promise<void>
  onEndConversation: () => void
  onCreateTicket: () => void
  canCreateTicket: boolean
  canTransfer: boolean
  onTransferred: (toName: string) => void
  satisfactionState: SatisfactionConversationState | null
  satisfactionLoading: boolean
  satisfactionSending: boolean
  onSendSatisfaction: () => Promise<boolean>
}

export type AgentImageMessage = {
  id: string
  content: string
}

type AgentChatContextValue = AgentChatConfigValue & {
  imageMessages: AgentImageMessage[]
  onFileSend: (file: File) => Promise<void>
}

const AgentChatConfigCtx = createContext<AgentChatContextValue | null>(null)

export function useAgentChatConfig() {
  const ctx = useContext(AgentChatConfigCtx)
  if (!ctx) throw new Error('useAgentChatConfig must be used within AgentChatRuntimeProvider')
  return ctx
}

// ─── Message metadata ────────────────────────────────────────────

export type AgentMessageMeta = {
  senderName: string | null
  senderAvatar: string | null
  senderType: string
  senderId: number | null
  contentType: string
  conversationId: number
  metadata?: Record<string, unknown>
  isOwn: boolean
  eventType?: string
  satisfactionRecordId?: number
  configVersion?: number
}

// ─── Helpers ─────────────────────────────────────────────────────

function mapRole(senderType: string): 'user' | 'assistant' | 'system' {
  if (senderType === 'visitor') return 'user'
  if (senderType === 'agent' || senderType === 'bot') return 'assistant'
  return 'system'
}

// ─── Provider ────────────────────────────────────────────────────

type ProviderProps = AgentChatConfigValue & {
  socket: Socket | null
  children: ReactNode
}

export function AgentChatRuntimeProvider({
  children,
  socket,
  ...chatConfig
}: ProviderProps) {
  const { conversation } = chatConfig
  const convId = conversation.id
  const messagesMap = useChatStore((s) => s.messages)
  const currentMessages = useMemo(() => messagesMap.get(convId) || [], [messagesMap, convId])
  const imageMessages = useMemo<AgentImageMessage[]>(
    () =>
      currentMessages
        .filter((msg) => msg.content_type === 'image')
        .map((msg) => ({ id: String(msg.id), content: msg.content })),
    [currentMessages],
  )
  const userId = useAuthStore((s) => s.user?.id)

  const onFileSend = useCallback(
    async (file: File) => {
      if (!socket || !convId) return

      const uploaded = await uploadAgentConversationFile({
        conversationId: convId,
        file,
      })
      const contentType = uploaded.mime_type.startsWith('image/') ? 'image' : 'file'
      const content = JSON.stringify({
        schema_version: uploaded.schema_version,
        file_id: uploaded.file_id,
        name: uploaded.name,
        size: uploaded.size,
        mime_type: uploaded.mime_type,
      })

      socket.emit('send_message', {
        conversation_id: convId,
        content,
        content_type: contentType,
      })
    },
    [socket, convId],
  )

  const convertMessage = useCallback(
    (msg: Message): ThreadMessageLike => {
      const meta: AgentMessageMeta = {
        senderName: msg.sender_name,
        senderAvatar: msg.sender_avatar,
        senderType: msg.sender_type,
        senderId: msg.sender_id,
        contentType: msg.content_type,
        conversationId: msg.conversation_id,
        metadata: msg.metadata,
        isOwn: msg.sender_type === 'agent' && msg.sender_id === userId,
        eventType: msg.event_type,
        satisfactionRecordId: msg.satisfaction_record_id,
        configVersion: msg.config_version,
      }

      return {
        role: mapRole(msg.sender_type),
        content: [{ type: 'text', text: msg.content }],
        id: String(msg.id),
        createdAt: new Date(msg.created_at),
        metadata: { custom: meta },
      }
    },
    [userId],
  )

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const textPart = message.content.find((p) => p.type === 'text')
      if (!textPart || textPart.type !== 'text') return
      if (!socket || !convId) return
      socket.emit('send_message', {
        conversation_id: convId,
        content: textPart.text,
        content_type: 'text',
      })
    },
    [socket, convId],
  )

  const runtime = useExternalStoreRuntime({
    isRunning: false,
    messages: currentMessages,
    convertMessage,
    onNew,
  })

  return (
    <AgentChatConfigCtx.Provider value={{ ...chatConfig, imageMessages, onFileSend }}>
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </AgentChatConfigCtx.Provider>
  )
}
