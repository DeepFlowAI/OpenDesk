'use client'

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
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
import type { Locale } from '@/context/locale-store'
import { uploadAgentConversationFile } from '@/service/use-conversation-files'
import type { Message, Conversation, WorkspaceConversationHistoryItem } from '@/models/conversation'
import type { ConversationFileUploadResponse } from '@/models/conversation-file'
import type { EmojiTargetConfig } from '@/models/emoji-setting'
import type { SatisfactionConversationState } from '@/models/satisfaction-survey'
import type { Socket } from 'socket.io-client'

// ─── Config context ──────────────────────────────────────────────

export type ComposerMode = 'public' | 'internal'

export type AgentChatConfigValue = {
  conversation: Conversation
  locale: Locale
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
  canPinConversation: boolean
  pinningConversation: boolean
  onTogglePinConversation: () => void
  canLockConversationTimeout: boolean
  lockingConversationTimeout: boolean
  onToggleConversationTimeoutLock: () => void
  canTransfer: boolean
  canEndConversation: boolean
  canInviteCollaborator: boolean
  canSendPublicReply: boolean
  canCreateInternalNote: boolean
  composerReadOnlyReason: string | null
  canStartNewConversation: boolean
  startNewConversationDisabledReason: string | null
  startingNewConversation: boolean
  onStartNewConversation: () => void
  onTransferred: (toName: string) => void
  onCollaborationInvitationSent: (name: string) => void
  satisfactionState: SatisfactionConversationState | null
  satisfactionLoading: boolean
  satisfactionSending: boolean
  onSendSatisfaction: () => Promise<boolean>
  emojiConfig: EmojiTargetConfig | null
  readStatusEnabled: boolean
}

export type AgentImageMessage = {
  id: string
  content: string
}

type AgentChatContextValue = AgentChatConfigValue & {
  imageMessages: AgentImageMessage[]
  onFileSend: (file: File) => Promise<void>
  onRichTextImageUpload: (file: File) => Promise<ConversationFileUploadResponse>
  onRichTextSend: (html: string) => Promise<void>
  composerMode: ComposerMode
  setComposerMode: (mode: ComposerMode) => void
  quotedMessage: Message | null
  onQuoteMessage: (message: Message) => void
  onClearQuote: () => void
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
  messageStatus?: string
  isOwn: boolean
  isRecalled?: boolean
  recalledAt?: string | null
  recalledByType?: string | null
  recalledByName?: string | null
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
  const [composerMode, setComposerMode] = useState<ComposerMode>(
    chatConfig.canSendPublicReply ? 'public' : 'internal',
  )
  const [quotedMessage, setQuotedMessage] = useState<Message | null>(null)
  const messagesMap = useChatStore((s) => s.messages)
  const currentMessages = useMemo(() => messagesMap.get(convId) || [], [messagesMap, convId])
  const imageMessages = useMemo<AgentImageMessage[]>(
    () =>
      currentMessages
        .filter((msg) => msg.content_type === 'image' && !msg.is_recalled)
        .map((msg) => ({ id: String(msg.id), content: msg.content })),
    [currentMessages],
  )
  const userId = useAuthStore((s) => s.user?.id)

  useEffect(() => {
    setComposerMode(chatConfig.canSendPublicReply ? 'public' : 'internal')
  }, [chatConfig.canSendPublicReply, convId])

  useEffect(() => {
    setQuotedMessage(null)
  }, [convId])

  const onQuoteMessage = useCallback((message: Message) => {
    setComposerMode('public')
    setQuotedMessage(message)
  }, [])

  const onClearQuote = useCallback(() => {
    setQuotedMessage(null)
  }, [])

  const emitSendMessage = useCallback(
    (payload: {
      conversation_id: number
      content: string
      content_type: string
      quoted_message_id?: number
    }) =>
      new Promise<void>((resolve, reject) => {
        if (!socket) {
          resolve()
          return
        }
        socket.emit('send_message', payload, (response?: { ok?: boolean; message?: unknown; error?: string }) => {
          if (response?.ok === false || response?.error) {
            const message = typeof response.message === 'string' ? response.message : response.error
            window.alert(message || (chatConfig.locale === 'zh'
              ? '发送失败，请稍后重试'
              : 'Send failed. Try again later'))
            reject(new Error(message || 'send_message failed'))
            return
          }
          if (payload.quoted_message_id) setQuotedMessage(null)
          resolve()
        })
      }),
    [chatConfig.locale, socket],
  )

  const onFileSend = useCallback(
    async (file: File) => {
      if (composerMode === 'internal' || !chatConfig.canSendPublicReply) return
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

      await emitSendMessage({
        conversation_id: convId,
        content,
        content_type: contentType,
        ...(quotedMessage ? { quoted_message_id: quotedMessage.id } : {}),
      })
    },
    [convId, composerMode, chatConfig.canSendPublicReply, emitSendMessage, quotedMessage],
  )

  const onRichTextImageUpload = useCallback(
    async (file: File) => {
      if (composerMode === 'internal' || !chatConfig.canSendPublicReply) {
        throw new Error('Rich text image upload is not available')
      }
      if (!convId) throw new Error('Conversation is required')
      return uploadAgentConversationFile({
        conversationId: convId,
        file,
      })
    },
    [convId, composerMode, chatConfig.canSendPublicReply],
  )

  const onRichTextSend = useCallback(
    async (html: string) => {
      if (!socket || !convId) return
      if (composerMode === 'internal' || !chatConfig.canSendPublicReply) return
      await emitSendMessage({
        conversation_id: convId,
        content: html,
        content_type: 'rich_text',
        ...(quotedMessage ? { quoted_message_id: quotedMessage.id } : {}),
      })
    },
    [socket, convId, composerMode, chatConfig.canSendPublicReply, emitSendMessage, quotedMessage],
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
        messageStatus: msg.status,
        isOwn: msg.sender_type === 'agent' && msg.sender_id === userId,
        isRecalled: msg.is_recalled,
        recalledAt: msg.recalled_at,
        recalledByType: msg.recalled_by_type,
        recalledByName: msg.recalled_by_name,
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
      if (composerMode === 'internal' && !chatConfig.canCreateInternalNote) return
      if (composerMode === 'public' && !chatConfig.canSendPublicReply) return
      await emitSendMessage({
        conversation_id: convId,
        content: textPart.text,
        content_type: composerMode === 'internal' ? 'internal_note' : 'text',
        ...(composerMode === 'public' && quotedMessage ? { quoted_message_id: quotedMessage.id } : {}),
      })
    },
    [socket, convId, composerMode, chatConfig.canCreateInternalNote, chatConfig.canSendPublicReply, emitSendMessage, quotedMessage],
  )

  const runtime = useExternalStoreRuntime({
    isRunning: false,
    messages: currentMessages,
    convertMessage,
    onNew,
  })

  return (
    <AgentChatConfigCtx.Provider
      value={{
        ...chatConfig,
        imageMessages,
        onFileSend,
        onRichTextImageUpload,
        onRichTextSend,
        composerMode,
        setComposerMode,
        quotedMessage,
        onQuoteMessage,
        onClearQuote,
      }}
    >
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </AgentChatConfigCtx.Provider>
  )
}
