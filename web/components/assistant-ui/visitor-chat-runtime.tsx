'use client'

import {
  createContext,
  useContext,
  useCallback,
  type ReactNode,
} from 'react'
import {
  useExternalStoreRuntime,
  AssistantRuntimeProvider,
  type ThreadMessageLike,
  type AppendMessage,
} from '@assistant-ui/react'
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import type { Message, VisitorConversationHistoryItem } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import type { ChannelPublicConfig } from '@/service/use-visitor-chat'
import { uploadVisitorConversationFile } from '@/service/use-conversation-files'
import type { SatisfactionSurveyRecord } from '@/models/satisfaction-survey'
import type { Socket } from 'socket.io-client'

// ─── Config context ──────────────────────────────────────────────

export type VisitorChatConfigValue = {
  channel: ChannelPublicConfig
  config: ChannelConfig
  locale: string
  isMobile: boolean
  ended: boolean
  conversationPublicId: string | null
  visitorSessionToken: string
  hasMore: boolean
  loadingMore: boolean
  historyAvailable: boolean
  historyConversations: VisitorConversationHistoryItem[]
  historyHasMore: boolean
  historyLoading: boolean
  historyLoaded: boolean
  historyError: boolean
  historyLimitReached: boolean
  initializing: boolean
  satisfactionCanInitiate: boolean
  satisfactionLoading: boolean
  onLoadMore: () => void
  onLoadHistory: (beforeId?: string) => Promise<void>
  onTyping: (content: string) => void
  onRestartConversation: () => Promise<void>
  onSatisfactionInitiate: () => Promise<SatisfactionSurveyRecord | null>
  onSatisfactionSubmitted: () => void
  onFileSend: (file: File) => Promise<void>
}

const VisitorChatConfigCtx = createContext<VisitorChatConfigValue | null>(null)

export function useVisitorChatConfig() {
  const ctx = useContext(VisitorChatConfigCtx)
  if (!ctx) throw new Error('useVisitorChatConfig must be used within VisitorChatRuntimeProvider')
  return ctx
}

// ─── Message metadata carried through assistant-ui ───────────────

export type VisitorMessageMeta = {
  senderName: string | null
  senderAvatar: string | null
  senderType: string
  senderId: number | null
  contentType: string
  conversationPublicId: string
  messageStatus?: string
  showTimestamp: boolean
  showName: boolean
  showAvatar: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────

function mapRole(senderType: string): 'user' | 'assistant' | 'system' {
  if (senderType === 'visitor') return 'user'
  if (senderType === 'agent') return 'assistant'
  return 'system'
}

function shouldShowTimestamp(cur: Message, prev: Message | null): boolean {
  if (!prev) return true
  return new Date(cur.created_at).getTime() - new Date(prev.created_at).getTime() > 5 * 60 * 1000
}

function shouldShowName(cur: Message, prev: Message | null): boolean {
  if (!prev) return true
  return prev.sender_type !== cur.sender_type || prev.sender_id !== cur.sender_id
}

function shouldShowAvatar(cur: Message, next: Message | null): boolean {
  if (!next) return true
  return next.sender_type !== cur.sender_type
}

// ─── Provider ────────────────────────────────────────────────────

type ProviderProps = Omit<VisitorChatConfigValue, 'onFileSend'> & {
  socket: Socket | null
  children: ReactNode
}

export function VisitorChatRuntimeProvider({
  children,
  socket,
  ...chatConfig
}: ProviderProps) {
  const messages = useVisitorChatStore((s) => s.messages)
  const { conversationPublicId, visitorSessionToken } = chatConfig

  const convertMessage = useCallback(
    (msg: Message, idx: number): ThreadMessageLike => {
      const prev = idx > 0 ? messages[idx - 1] : null
      const next = idx < messages.length - 1 ? messages[idx + 1] : null
      const useAgentAvatar = chatConfig.config.use_agent_avatar === true
      const showAvatar = msg.sender_type === 'agent'
        ? useAgentAvatar
        : shouldShowAvatar(msg, next)

      const meta: VisitorMessageMeta = {
        senderName: msg.sender_name,
        senderAvatar: msg.sender_avatar,
        senderType: msg.sender_type,
        senderId: msg.sender_id,
        contentType: msg.content_type,
        conversationPublicId: msg.conversation_public_id || conversationPublicId || '',
        messageStatus: msg.status,
        showTimestamp: shouldShowTimestamp(msg, prev),
        showName: shouldShowName(msg, prev),
        showAvatar,
      }

      return {
        role: mapRole(msg.sender_type),
        content: [{ type: 'text', text: msg.content }],
        id: String(msg.id),
        createdAt: new Date(msg.created_at),
        metadata: { custom: meta },
      }
    },
    [messages, chatConfig.config.use_agent_avatar],
  )

  const addOptimistic = useVisitorChatStore((s) => s.addOptimisticMessage)
  const confirmOptimistic = useVisitorChatStore((s) => s.confirmOptimisticMessage)
  const visitorExternalId = useVisitorChatStore((s) => s.visitorId)

  const onFileSend = useCallback(
    async (file: File) => {
      if (!socket || !conversationPublicId || !visitorExternalId) return

      const uploaded = await uploadVisitorConversationFile({
        conversationPublicId,
        visitorSessionToken,
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
      const tempId = addOptimistic(conversationPublicId, content, contentType)

      socket.emit('send_message', {
        conversation_public_id: conversationPublicId,
        content,
        content_type: contentType,
      }, (res: { ok?: boolean; message?: Message }) => {
        if (res?.ok && res.message) {
          confirmOptimistic(tempId, res.message)
        }
      })
    },
    [socket, conversationPublicId, visitorExternalId, visitorSessionToken, addOptimistic, confirmOptimistic],
  )

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const textPart = message.content.find((p) => p.type === 'text')
      if (!textPart || textPart.type !== 'text') return
      if (!socket || !conversationPublicId) return

      const tempId = addOptimistic(conversationPublicId, textPart.text, 'text')

      socket.emit('send_message', {
        conversation_public_id: conversationPublicId,
        content: textPart.text,
        content_type: 'text',
      }, (res: { ok?: boolean; message?: Message }) => {
        if (res?.ok && res.message) {
          confirmOptimistic(tempId, res.message)
        }
      })
    },
    [socket, conversationPublicId, addOptimistic, confirmOptimistic],
  )

  const runtime = useExternalStoreRuntime({
    isRunning: false,
    messages,
    convertMessage,
    onNew,
  })

  return (
    <VisitorChatConfigCtx.Provider value={{ ...chatConfig, onFileSend }}>
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </VisitorChatConfigCtx.Provider>
  )
}
