'use client'

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
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
import {
  prepareKnowledgeAttachmentForConversation,
  uploadAgentConversationFile,
} from '@/service/use-conversation-files'
import {
  buildKnowledgeSendPlan,
  type KnowledgeSendPlanItem,
} from '@/app/components/features/knowledge/knowledge-utils'
import type { Message, Conversation, WorkspaceConversationHistoryItem } from '@/models/conversation'
import type { ConversationFileUploadResponse } from '@/models/conversation-file'
import type { EmojiTargetConfig } from '@/models/emoji-setting'
import type { KnowledgeDocumentAttachment } from '@/models/knowledge'
import type { SatisfactionConversationState } from '@/models/satisfaction-survey'
import type { Socket } from 'socket.io-client'

// ─── Config context ──────────────────────────────────────────────

export type ComposerMode = 'public' | 'internal'

export type ResolvedConversationForSend = {
  conversation: Conversation
  alreadyActive?: boolean
}

export type DeferredConversationSendResult = {
  messageSent: boolean
}

export type KnowledgeDraftSendInput = {
  bodyContent: string
  bodyText: string
  bodyContentType: 'text' | 'rich_text'
  attachments: KnowledgeDocumentAttachment[]
  requestId: string
  onItemSent: (item: KnowledgeSendPlanItem) => void
  onAttachmentPreparing: (attachmentId: number | null) => void
}

export type KnowledgeDraftSendResult = {
  sent: number
  total: number
  errorMessage: string | null
}

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
  resolveConversationForSend?: () => Promise<ResolvedConversationForSend>
  uploadDeferredRichTextImage?: (file: File) => Promise<ConversationFileUploadResponse>
  onDeferredConversationResolved?: (
    conversation: Conversation,
    result: DeferredConversationSendResult,
  ) => void | Promise<void>
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
  onKnowledgeDraftSend: (input: KnowledgeDraftSendInput) => Promise<KnowledgeDraftSendResult>
  composerMode: ComposerMode
  setComposerMode: (mode: ComposerMode) => void
  quotedMessage: Message | null
  onQuoteMessage: (message: Message) => void
  onClearQuote: () => void
  onRetryMessage: (message: Message) => void
}

const AgentChatConfigCtx = createContext<AgentChatContextValue | null>(null)

export function useAgentChatConfig() {
  const ctx = useContext(AgentChatConfigCtx)
  if (!ctx) throw new Error('useAgentChatConfig must be used within AgentChatRuntimeProvider')
  return ctx
}

// ─── Message metadata ────────────────────────────────────────────

export type AgentMessageMeta = {
  // The full original message is the single source of truth. Both rendering and
  // interaction logic derive everything they need from it, so no field is lost.
  original: Message
}

// ─── Helpers ─────────────────────────────────────────────────────

function mapRole(senderType: string): 'user' | 'assistant' | 'system' {
  if (senderType === 'visitor') return 'user'
  if (senderType === 'agent' || senderType === 'bot') return 'assistant'
  return 'system'
}

let optimisticMessageId = -1

function createClientMessageId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `agent-${Date.now()}-${Math.random().toString(16).slice(2)}`
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
  const currentUser = useAuthStore((state) => state.user)
  const convId = conversation.id
  const [composerMode, setComposerMode] = useState<ComposerMode>(
    chatConfig.canSendPublicReply ? 'public' : 'internal',
  )
  const [quotedMessage, setQuotedMessage] = useState<Message | null>(null)
  const resolvedConversationRef = useRef<Conversation | null>(null)
  const messagesMap = useChatStore((s) => s.messages)
  const currentMessages = useMemo(() => messagesMap.get(convId) || [], [messagesMap, convId])
  const imageMessages = useMemo<AgentImageMessage[]>(
    () =>
      currentMessages
        .filter((msg) => msg.content_type === 'image' && !msg.is_recalled)
        .map((msg) => ({ id: String(msg.id), content: msg.content })),
    [currentMessages],
  )

  useEffect(() => {
    setComposerMode(chatConfig.canSendPublicReply ? 'public' : 'internal')
  }, [chatConfig.canSendPublicReply, convId])

  useEffect(() => {
    setQuotedMessage(null)
    resolvedConversationRef.current = null
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
      client_message_id?: string
    }, retryMessage?: Message) => {
      const clientMessageId = payload.client_message_id
        || retryMessage?.metadata?.client_message_id
        || createClientMessageId()
      const tempId = retryMessage?.id && retryMessage.id < 0 ? retryMessage.id : optimisticMessageId--
      const optimisticMessage: Message = {
        id: tempId,
        conversation_id: payload.conversation_id,
        sender_type: 'agent',
        sender_id: currentUser?.id ?? null,
        sender_name: currentUser?.display_name || currentUser?.name || null,
        sender_avatar: currentUser?.avatar ?? null,
        content_type: payload.content_type as Message['content_type'],
        content: payload.content,
        created_at: retryMessage?.created_at || new Date().toISOString(),
        status: 'sending',
        metadata: {
          ...(retryMessage?.metadata || {}),
          client_message_id: clientMessageId,
          ...(payload.quoted_message_id ? { retry_quoted_message_id: payload.quoted_message_id } : {}),
        },
      }
      const store = useChatStore.getState()
      if (retryMessage) store.updateMessage(payload.conversation_id, optimisticMessage)
      else store.addMessage(payload.conversation_id, optimisticMessage)

      return new Promise<void>((resolve, reject) => {
        if (!socket?.connected) {
          useChatStore.getState().updateMessage(payload.conversation_id, {
            ...optimisticMessage,
            status: 'failed',
          })
          reject(new Error('socket disconnected'))
          return
        }
        socket.timeout(10_000).emit(
          'send_message',
          { ...payload, client_message_id: clientMessageId },
          (timeoutError: Error | null, response?: { ok?: boolean; message?: Message | string; error?: string }) => {
            if (timeoutError || response?.ok === false || response?.error) {
              const errorMessage = typeof response?.message === 'string' ? response.message : response?.error
              useChatStore.getState().updateMessage(payload.conversation_id, {
                ...optimisticMessage,
                status: 'failed',
              })
              reject(new Error(errorMessage || timeoutError?.message || 'send_message failed'))
              return
            }
            if (response?.message && typeof response.message !== 'string') {
              useChatStore.getState().addMessage(payload.conversation_id, response.message)
            }
            if (payload.quoted_message_id) setQuotedMessage(null)
            resolve()
          },
        )
      })
    },
    [currentUser, socket],
  )

  const onRetryMessage = useCallback((message: Message) => {
    if (message.status !== 'failed') return
    const quotedMessageId = typeof message.metadata?.retry_quoted_message_id === 'number'
      ? message.metadata.retry_quoted_message_id
      : undefined
    void emitSendMessage({
      conversation_id: message.conversation_id,
      content: message.content,
      content_type: message.content_type,
      ...(quotedMessageId ? { quoted_message_id: quotedMessageId } : {}),
    }, message).catch(() => {})
  }, [emitSendMessage])

  const ensureSendConversation = useCallback(async () => {
    if (!chatConfig.resolveConversationForSend) return conversation
    if (resolvedConversationRef.current) return resolvedConversationRef.current
    const resolved = await chatConfig.resolveConversationForSend()
    resolvedConversationRef.current = resolved.conversation
    return resolved.conversation
  }, [chatConfig, conversation])

  const notifyDeferredConversationResolved = useCallback(
    async (sendConversation: Conversation, messageSent: boolean) => {
      if (!chatConfig.resolveConversationForSend || !chatConfig.onDeferredConversationResolved) return
      await chatConfig.onDeferredConversationResolved(sendConversation, { messageSent })
    },
    [chatConfig],
  )

  const emitDeferredAwareMessage = useCallback(
    async (payload: {
      conversation: Conversation
      content: string
      content_type: string
      quoted_message_id?: number
    }) => {
      try {
        await emitSendMessage({
          conversation_id: payload.conversation.id,
          content: payload.content,
          content_type: payload.content_type,
          ...(payload.quoted_message_id ? { quoted_message_id: payload.quoted_message_id } : {}),
        })
      } catch (error) {
        await notifyDeferredConversationResolved(payload.conversation, false)
        throw error
      }
      await notifyDeferredConversationResolved(payload.conversation, true)
    },
    [emitSendMessage, notifyDeferredConversationResolved],
  )

  const onFileSend = useCallback(
    async (file: File) => {
      if (composerMode === 'internal' || !chatConfig.canSendPublicReply) return
      if (!socket || !convId) return

      const sendConversation = await ensureSendConversation()

      let uploaded: ConversationFileUploadResponse
      try {
        uploaded = await uploadAgentConversationFile({
          conversationId: sendConversation.id,
          file,
        })
      } catch (error) {
        await notifyDeferredConversationResolved(sendConversation, false)
        throw error
      }
      const contentType = uploaded.mime_type.startsWith('image/') ? 'image' : 'file'
      const content = JSON.stringify({
        schema_version: uploaded.schema_version,
        file_id: uploaded.file_id,
        name: uploaded.name,
        size: uploaded.size,
        mime_type: uploaded.mime_type,
      })

      await emitDeferredAwareMessage({
        conversation: sendConversation,
        content,
        content_type: contentType,
        ...(quotedMessage ? { quoted_message_id: quotedMessage.id } : {}),
      })
    },
    [
      convId,
      composerMode,
      chatConfig.canSendPublicReply,
      emitDeferredAwareMessage,
      ensureSendConversation,
      notifyDeferredConversationResolved,
      quotedMessage,
      socket,
    ],
  )

  const onRichTextImageUpload = useCallback(
    async (file: File) => {
      if (composerMode === 'internal' || !chatConfig.canSendPublicReply) {
        throw new Error('Rich text image upload is not available')
      }
      if (!convId) throw new Error('Conversation is required')
      if (chatConfig.resolveConversationForSend && chatConfig.uploadDeferredRichTextImage) {
        return chatConfig.uploadDeferredRichTextImage(file)
      }
      const sendConversation = await ensureSendConversation()
      return uploadAgentConversationFile({
        conversationId: sendConversation.id,
        file,
      })
    },
    [convId, composerMode, chatConfig, ensureSendConversation],
  )

  const onRichTextSend = useCallback(
    async (html: string) => {
      if (!socket || !convId) return
      if (composerMode === 'internal' || !chatConfig.canSendPublicReply) return
      const sendConversation = await ensureSendConversation()
      await emitDeferredAwareMessage({
        conversation: sendConversation,
        content: html,
        content_type: 'rich_text',
        ...(quotedMessage ? { quoted_message_id: quotedMessage.id } : {}),
      })
    },
    [
      socket,
      convId,
      composerMode,
      chatConfig.canSendPublicReply,
      emitDeferredAwareMessage,
      ensureSendConversation,
      quotedMessage,
    ],
  )

  const onKnowledgeDraftSend = useCallback(
    async (input: KnowledgeDraftSendInput): Promise<KnowledgeDraftSendResult> => {
      const plan = buildKnowledgeSendPlan({
        messageHtml: input.bodyContent,
        messageText: input.bodyText,
        attachments: input.attachments,
        requestId: input.requestId,
      })
      if (!socket || !convId || composerMode === 'internal' || !chatConfig.canSendPublicReply) {
        return { sent: 0, total: plan.length, errorMessage: 'Knowledge draft cannot be sent' }
      }

      let sent = 0
      let sendConversation: Conversation | null = null

      try {
        sendConversation = await ensureSendConversation()
        for (const item of plan) {
          let content: string
          let contentType: 'text' | 'rich_text' | 'file'
          if (item.kind === 'body') {
            content = item.content
            contentType = input.bodyContentType
          } else {
            input.onAttachmentPreparing(item.attachment.id)
            const prepared = await prepareKnowledgeAttachmentForConversation({
              conversationId: sendConversation.id,
              attachmentId: item.attachment.id,
            })
            content = JSON.stringify({
              schema_version: prepared.schema_version,
              file_id: prepared.file_id,
              name: prepared.name,
              size: prepared.size,
              mime_type: prepared.mime_type,
            })
            contentType = 'file'
          }

          await emitSendMessage({
            conversation_id: sendConversation.id,
            content,
            content_type: contentType,
            client_message_id: item.clientMessageId,
            ...(sent === 0 && quotedMessage ? { quoted_message_id: quotedMessage.id } : {}),
          })
          sent += 1
          input.onItemSent(item)
        }
        await notifyDeferredConversationResolved(sendConversation, plan.length > 0)
        return { sent, total: plan.length, errorMessage: null }
      } catch (error) {
        if (sendConversation) await notifyDeferredConversationResolved(sendConversation, sent > 0)
        return {
          sent,
          total: plan.length,
          errorMessage: error instanceof Error && error.message ? error.message : null,
        }
      } finally {
        input.onAttachmentPreparing(null)
      }
    },
    [
      chatConfig.canSendPublicReply,
      composerMode,
      convId,
      emitSendMessage,
      ensureSendConversation,
      notifyDeferredConversationResolved,
      quotedMessage,
      socket,
    ],
  )

  const convertMessage = useCallback(
    (msg: Message): ThreadMessageLike => {
      const meta: AgentMessageMeta = { original: msg }
      return {
        role: mapRole(msg.sender_type),
        content: [{ type: 'text', text: msg.content }],
        id: String(msg.id),
        createdAt: new Date(msg.created_at),
        metadata: { custom: meta },
      }
    },
    [],
  )

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const textPart = message.content.find((p) => p.type === 'text')
      if (!textPart || textPart.type !== 'text') return
      if (!socket || !convId) return
      if (composerMode === 'internal' && !chatConfig.canCreateInternalNote) return
      if (composerMode === 'public' && !chatConfig.canSendPublicReply) return
      const sendConversation = composerMode === 'public'
        ? await ensureSendConversation()
        : conversation
      await emitDeferredAwareMessage({
        conversation: sendConversation,
        content: textPart.text,
        content_type: composerMode === 'internal' ? 'internal_note' : 'text',
        ...(composerMode === 'public' && quotedMessage ? { quoted_message_id: quotedMessage.id } : {}),
      })
    },
    [
      socket,
      convId,
      composerMode,
      chatConfig.canCreateInternalNote,
      chatConfig.canSendPublicReply,
      conversation,
      emitDeferredAwareMessage,
      ensureSendConversation,
      quotedMessage,
    ],
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
        onKnowledgeDraftSend,
        composerMode,
        setComposerMode,
        quotedMessage,
        onQuoteMessage,
        onClearQuote,
        onRetryMessage,
      }}
    >
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </AgentChatConfigCtx.Provider>
  )
}
