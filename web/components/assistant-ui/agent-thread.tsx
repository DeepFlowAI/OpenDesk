'use client'

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ThreadPrimitive, type MessageState } from '@assistant-ui/react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAgentChatConfig,
  type AgentMessageMeta,
} from './agent-chat-runtime'
import { AgentComposer, type ComposerContentType, type ComposerInsertRequest } from './agent-composer'
import {
  IconArrowsExchange2,
  IconLock,
  IconLockOpen,
  IconTicket,
  IconX,
  IconLoader2,
  IconMessagePlus,
  IconPinned,
  IconUserPlus,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import {
  copyImageUrlToClipboard,
  copyPlainTextToClipboard,
  htmlToPlainText,
} from '@/lib/clipboard'
import { useAuthStore } from '@/context/auth-store'
import { useChatStore } from '@/context/chat-store'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import { TransferConversationModal } from '@/app/components/features/chat/transfer-conversation-modal'
import { InviteCollaboratorModal } from '@/app/components/features/chat/invite-collaborator-modal'
import { KnowledgeDocumentCreateDialog } from '@/app/components/features/knowledge/knowledge-document-create-dialog'
import { RobotQaCreateDialog } from '@/app/components/features/chat/robot-qa-create-dialog'
import { stripKnowledgeHtml } from '@/app/components/features/knowledge/knowledge-utils'
import {
  WorkspaceMessageBubble,
} from '@/app/components/features/chat/workspace-message-bubble'
import { conversationKeys, setVisitorWebStatusQueryData, useVisitorWebStatus } from '@/service/use-conversations'
import { getConversationFileUrl } from '@/service/use-conversation-files'
import {
  stageKnowledgeAttachmentFromConversationMessage,
  useCreateKnowledgeInspiration,
} from '@/service/use-knowledge'
import { buildKnowledgeInspirationPayloadFromMessage } from '@/lib/knowledge-inspiration-content'
import { canCreateRobotQaFromMessage } from '@/lib/robot-qa-message-content'
import {
  buildKnowledgeDocumentContentFromMessage,
  knowledgeFilePayloadFromMessage,
} from '@/lib/knowledge-document-message-content'
import {
  knowledgeImageSourceFromMessage,
  KnowledgeImageTransferError,
} from '@/lib/knowledge-message-image'
import { get } from '@/service/base'
import { isConversationHistoryContentMessage } from '@/lib/conversation-history-message'
import {
  canQuoteMessage,
  messageQuoteFromMetadata,
} from '@/lib/message-quote'
import type {
  Conversation,
  Message,
  MessageListResponse,
  VisitorWebStatus,
  VisitorWebStatusResponse,
  WorkspaceConversationHistoryItem,
} from '@/models/conversation'
import type { ConversationFilePayload } from '@/models/conversation-file'
import type { KnowledgeDocumentAttachment } from '@/models/knowledge'
import type { RobotQaRuntime } from '@/models/robot-qa'
import { useRobotQaRuntime } from '@/service/use-robot-qa'
import type { Socket } from 'socket.io-client'

// ─── Timestamp formatting ────────────────────────────────────────

function formatHistoryTime(dateStr: string | null, locale: string): string {
  if (!dateStr) return locale === 'zh' ? '历史会话' : 'History'
  const d = new Date(dateStr)
  const date = d.toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
  })
  const time = d.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  return `${date} ${time}`
}

const MESSAGE_RECALL_WINDOW_MS = 2 * 60 * 1000

function isRecallableContentType(contentType: string | undefined): boolean {
  return contentType === 'text'
    || contentType === 'rich_text'
    || contentType === 'image'
    || contentType === 'file'
}

function isMessageWithinRecallWindow(createdAt: Date | undefined): boolean {
  if (!createdAt) return false
  return Date.now() - createdAt.getTime() <= MESSAGE_RECALL_WINDOW_MS
}

const EMPTY_MESSAGES: Message[] = []

type KnowledgeDocumentDraft = {
  contentHtml: string
  attachments: KnowledgeDocumentAttachment[]
}

function scrollToWorkspaceMessage(messageId: number, locale: Locale): void {
  const node = document.querySelector<HTMLElement>(`[data-workspace-message-id="${messageId}"]`)
  if (!node) {
    window.alert(t('ws.chat.quote.locateFailed', locale))
    return
  }
  node.scrollIntoView({ block: 'center', behavior: 'smooth' })
  node.classList.add('bg-warning/15')
  window.setTimeout(() => node.classList.remove('bg-warning/15'), 2000)
}

function isCollaborativeConversation(conversation: Conversation): boolean {
  return (
    conversation.viewer_relation === 'collaborator'
    || conversation.collaborated_by_current_user === true
    || Boolean(conversation.collaborators?.length)
  )
}

function knowledgeImageErrorText(error: unknown, locale: Locale): string {
  const isZh = locale === 'zh'
  if (!(error instanceof KnowledgeImageTransferError)) {
    return isZh ? '图片处理失败，请重试' : 'Failed to process the image. Try again.'
  }
  if (error.code === 'source_too_large') {
    return isZh
      ? '图片过大，暂不支持添加到知识库'
      : 'The image is too large to add to the knowledge base'
  }
  if (error.code === 'output_too_large') {
    return isZh
      ? '图片压缩后仍超过 10MB，无法添加到知识库'
      : 'The compressed image still exceeds 10MB'
  }
  if (error.code === 'processing_unavailable') {
    return isZh
      ? '图片超过 10MB，当前来源无法压缩后添加到知识库'
      : 'This image source cannot be compressed for the knowledge base'
  }
  if (error.code === 'invalid_source' || error.code === 'not_image') {
    return isZh
      ? '图片内容不可用，无法添加到知识库'
      : 'The image content is unavailable'
  }
  return isZh ? '图片处理失败，请重试' : 'Failed to process the image. Try again.'
}

function knowledgeFileErrorText(error: unknown, locale: Locale): string {
  const isZh = locale === 'zh'
  const status = (error as { response?: { status?: number } }).response?.status
  if (status === 403) {
    return isZh
      ? '无权限新建知识文档'
      : 'You do not have permission to create knowledge documents'
  }
  if (status === 400 || status === 404) {
    return isZh
      ? '文件消息不可用，无法新建知识文档'
      : 'The file message is unavailable and cannot be used to create a knowledge document'
  }
  return isZh ? '文件处理失败，请重试' : 'Failed to process the file. Try again.'
}

// ─── Agent-side message bubble ───────────────────────────────────

function AgentMessageBubble({
  message,
  socket,
  robotQaRuntime,
  onComposerInsertRequest,
}: {
  message: MessageState
  socket: Socket | null
  robotQaRuntime?: RobotQaRuntime
  onComposerInsertRequest?: (request: Omit<ComposerInsertRequest, 'id' | 'conversationId'>) => void
}) {
  const {
    conversation,
    imageMessages,
    locale: cfgLocale,
    readStatusEnabled,
    isClosed,
    canSendPublicReply,
    onQuoteMessage,
    onRetryMessage,
  } = useAgentChatConfig()
  const user = useAuthStore((state) => state.user)
  const currentUserId = user?.id
  const createKnowledgeInspiration = useCreateKnowledgeInspiration()
  const [knowledgeDocumentDraft, setKnowledgeDocumentDraft] = useState<KnowledgeDocumentDraft | null>(null)
  const [robotQaMessage, setRobotQaMessage] = useState<Message | null>(null)
  const knowledgeContentProcessingRef = useRef(false)
  const meta = message.metadata?.custom as AgentMessageMeta | undefined
  const conversationMessages = useChatStore((state) => state.messages.get(conversation.id) || EMPTY_MESSAGES)

  const webChannel = String(conversation.channel?.channel_type || '').toLowerCase() === 'web'

  // The full original message is the single source of truth. The rebuild is a
  // fallback for messages without runtime metadata (not expected in this runtime).
  const originalMessage = useMemo<Message>(() => {
    if (meta?.original) return meta.original
    const firstPart = message.content?.[0]
    const fallbackContent = firstPart && 'text' in firstPart ? (firstPart.text as string) : ''
    return {
      id: Number(message.id) || 0,
      conversation_id: conversation.id,
      sender_type: 'system',
      sender_id: null,
      sender_name: null,
      sender_avatar: null,
      content_type: 'text',
      content: fallbackContent,
      created_at: message.createdAt?.toISOString() || new Date().toISOString(),
    }
  }, [conversation.id, message.content, message.createdAt, message.id, meta])

  const isRichText = originalMessage.content_type === 'rich_text'
  const attachmentContentType =
    originalMessage.content_type === 'image'
      ? 'image'
      : originalMessage.content_type === 'file'
        ? 'file'
        : null
  const content = originalMessage.content
  const hasMessageText = content.trim().length > 0
  const hasKnowledgeImage =
    originalMessage.content_type === 'image'
    && knowledgeImageSourceFromMessage(originalMessage) != null
  const hasKnowledgeFile = knowledgeFilePayloadFromMessage(originalMessage) != null
  const hasKnowledgeContent =
    ((originalMessage.content_type === 'text' || originalMessage.content_type === 'rich_text') && hasMessageText)
    || hasKnowledgeImage
  const isRecalled = Boolean(originalMessage.is_recalled || originalMessage.metadata?.is_recalled)
  const isOwn = originalMessage.sender_type === 'agent' && originalMessage.sender_id === currentUserId

  const canRecallMessage =
    Boolean(socket)
    && !isRecalled
    && !isClosed
    && canSendPublicReply
    && isOwn
    && isRecallableContentType(originalMessage.content_type)
    && webChannel
    && isMessageWithinRecallWindow(message.createdAt)
  const canQuoteCurrentMessage =
    Boolean(socket)
    && canQuoteMessage(originalMessage, { canSend: canSendPublicReply, closed: isClosed, webChannel })
  const canCopyCurrentMessage =
    !isRecalled
    && (
      attachmentContentType === 'image'
      || ((originalMessage.content_type === 'text' || originalMessage.content_type === 'rich_text') && hasMessageText)
    )
  const canAddKnowledgeInspiration =
    hasPermission(user, 'knowledge.workspace.inspiration.create')
    && !isRecalled
    && originalMessage.sender_type === 'agent'
    && hasKnowledgeContent
  const canCreateKnowledgeDocument =
    hasPermission(user, 'knowledge.workspace.document.create')
    && !isRecalled
    && originalMessage.sender_type === 'agent'
    && (hasKnowledgeContent || hasKnowledgeFile)
  const canCreateRobotQa =
    robotQaRuntime?.enabled === true
    && robotQaRuntime.available
    && !isClosed
    && canCreateRobotQaFromMessage(originalMessage)
  const recallEditContent = typeof originalMessage.metadata?.recall_edit_content === 'string'
    ? originalMessage.metadata.recall_edit_content
    : ''
  const canEditRecalled =
    isRecalled
    && isOwn
    && canSendPublicReply
    && !isClosed
    && (originalMessage.content_type === 'text' || originalMessage.content_type === 'rich_text')
    && recallEditContent.length > 0

  const quote = messageQuoteFromMetadata(originalMessage.metadata)
  const quotedOriginal = quote
    ? conversationMessages.find((item) => item.id === quote.message_id) ?? null
    : null
  const reeditQuotedMessage =
    quotedOriginal && canQuoteMessage(quotedOriginal, { canSend: canSendPublicReply, closed: isClosed, webChannel })
      ? quotedOriginal
      : null

  const handleCopy = useCallback(async (selectedText?: string) => {
    let ok = false
    if (selectedText && selectedText.trim()) {
      ok = await copyPlainTextToClipboard(selectedText)
    } else if (attachmentContentType === 'image') {
      let imageUrl = content
      try {
        const payload = JSON.parse(content) as ConversationFilePayload
        if (payload?.file_id) {
          const res = await getConversationFileUrl({
            conversationId: originalMessage.conversation_id,
            fileId: payload.file_id,
            downloadName: payload.name,
          })
          imageUrl = res.url
        }
      } catch {
        // content is a direct image URL rather than a file payload
      }
      ok = await copyImageUrlToClipboard(imageUrl)
    } else if (isRichText) {
      ok = await copyPlainTextToClipboard(htmlToPlainText(content))
    } else {
      ok = await copyPlainTextToClipboard(content)
    }
    if (ok) toast.success(t('ws.chat.copy.success', cfgLocale))
    else toast.error(t('ws.chat.copy.failed', cfgLocale))
  }, [attachmentContentType, cfgLocale, content, isRichText, originalMessage.conversation_id])

  const handleAddKnowledgeInspiration = useCallback(async (bubbleMessage?: Message) => {
    const source =
      conversationMessages.find((item) => item.id === originalMessage.id)
      ?? bubbleMessage
      ?? originalMessage
    const isImage = source.content_type === 'image'
    if (isImage && knowledgeContentProcessingRef.current) return
    const processingToastId = isImage
      ? toast.loading(cfgLocale === 'zh' ? '图片处理中…' : 'Processing image…')
      : undefined
    if (isImage) knowledgeContentProcessingRef.current = true
    let contentPrepared = false
    try {
      const payload = await buildKnowledgeInspirationPayloadFromMessage(source)
      contentPrepared = true
      await createKnowledgeInspiration.mutateAsync(payload)
      toast.success(
        cfgLocale === 'zh' ? '已添加至知识灵感' : 'Added to knowledge inspirations',
        processingToastId != null ? { id: processingToastId } : undefined,
      )
    } catch (error) {
      if (isImage && !contentPrepared) {
        toast.error(
          knowledgeImageErrorText(error, cfgLocale),
          processingToastId != null ? { id: processingToastId } : undefined,
        )
        return
      }
      const fallback = cfgLocale === 'zh' ? '添加知识灵感失败' : 'Failed to add knowledge inspiration'
      const showError = (message: string) => toast.error(
        message,
        processingToastId != null ? { id: processingToastId } : undefined,
      )
      const maybeResponse = error as { response?: { json?: () => Promise<unknown> } }
      if (maybeResponse.response?.json) {
        try {
          const body = await maybeResponse.response.json()
          if (body && typeof body === 'object' && typeof (body as Record<string, unknown>).message === 'string') {
            showError((body as Record<string, string>).message)
            return
          }
        } catch {
          showError(fallback)
          return
        }
      }
      showError(fallback)
    } finally {
      if (isImage) knowledgeContentProcessingRef.current = false
    }
  }, [cfgLocale, conversationMessages, createKnowledgeInspiration, originalMessage])

  const handleCreateKnowledgeDocument = useCallback(async (bubbleMessage?: Message) => {
    const source =
      conversationMessages.find((item) => item.id === originalMessage.id)
      ?? bubbleMessage
      ?? originalMessage
    const isImage = source.content_type === 'image'
    const isFile = source.content_type === 'file'
    if ((isImage || isFile) && knowledgeContentProcessingRef.current) return
    const processingToastId = isImage
      ? toast.loading(cfgLocale === 'zh' ? '图片处理中…' : 'Processing image…')
      : isFile
        ? toast.loading(cfgLocale === 'zh' ? '文件处理中…' : 'Processing file…')
        : undefined
    if (isImage || isFile) knowledgeContentProcessingRef.current = true
    try {
      if (isFile) {
        const attachment = await stageKnowledgeAttachmentFromConversationMessage(source.id)
        if (processingToastId != null) toast.dismiss(processingToastId)
        setKnowledgeDocumentDraft({
          contentHtml: '<p></p>',
          attachments: [attachment],
        })
        return
      }
      const contentHtml = await buildKnowledgeDocumentContentFromMessage(source)
      if (!stripKnowledgeHtml(contentHtml)) {
        toast.error(
          cfgLocale === 'zh'
            ? '消息内容不可用，无法新建知识文档'
            : 'Message content is unavailable and cannot be used to create a knowledge document',
          processingToastId != null ? { id: processingToastId } : undefined,
        )
        return
      }
      if (processingToastId != null) toast.dismiss(processingToastId)
      setKnowledgeDocumentDraft({ contentHtml, attachments: [] })
    } catch (error) {
      const errorText = isImage
        ? knowledgeImageErrorText(error, cfgLocale)
        : isFile
          ? knowledgeFileErrorText(error, cfgLocale)
          : cfgLocale === 'zh'
            ? '消息内容不可用，无法新建知识文档'
            : 'Message content is unavailable and cannot be used to create a knowledge document'
      toast.error(
        errorText,
        processingToastId != null ? { id: processingToastId } : undefined,
      )
    } finally {
      if (isImage || isFile) knowledgeContentProcessingRef.current = false
    }
  }, [cfgLocale, conversationMessages, originalMessage])

  const handleRecall = useCallback(() => {
    if (!socket) return
    socket.emit(
      'recall_message',
      { conversation_id: conversation.id, message_id: Number(message.id) },
      (response?: { ok?: boolean; message?: string }) => {
        if (response?.ok === false) {
          window.alert(response.message || t('ws.chat.recall.failed', cfgLocale))
        }
      },
    )
  }, [cfgLocale, conversation.id, message.id, socket])

  const handleEditRecalled = useCallback(() => {
    if (!onComposerInsertRequest) return
    onComposerInsertRequest({
      text: recallEditContent,
      contentType: originalMessage.content_type === 'rich_text' ? 'rich_text' : 'text',
      quotedMessage: reeditQuotedMessage,
    })
  }, [originalMessage.content_type, onComposerInsertRequest, recallEditContent, reeditQuotedMessage])

  return (
    <>
      <WorkspaceMessageBubble
        message={originalMessage}
        locale={cfgLocale}
        mode="active"
        attachmentContext={{ kind: 'conversation', conversationId: originalMessage.conversation_id }}
        visitorName={conversation.visitor?.name ?? null}
        visitorAvatarColor={conversation.visitor?.avatar_color ?? null}
        imageGallery={imageMessages}
        allMessages={conversationMessages}
        currentUserId={currentUserId}
        readStatusEnabled={readStatusEnabled}
        inlinePlayableVideo
        showAgentName={isCollaborativeConversation(conversation)}
        showVisitorName={false}
        showVisitorAvatar={false}
        showAssistantAvatar={false}
        onLocateQuotedMessage={(id) => scrollToWorkspaceMessage(id, cfgLocale)}
        onCopyMessage={canCopyCurrentMessage ? (_message, selectedText) => void handleCopy(selectedText) : undefined}
        onAddKnowledgeInspiration={canAddKnowledgeInspiration ? (msg) => void handleAddKnowledgeInspiration(msg) : undefined}
        onCreateKnowledgeDocument={canCreateKnowledgeDocument ? (msg) => void handleCreateKnowledgeDocument(msg) : undefined}
        onCreateRobotQa={canCreateRobotQa ? (msg) => setRobotQaMessage(
          conversationMessages.find((item) => item.id === msg.id) ?? msg,
        ) : undefined}
        onQuoteMessage={canQuoteCurrentMessage ? onQuoteMessage : undefined}
        onRecallMessage={canRecallMessage ? handleRecall : undefined}
        onEditRecalledMessage={canEditRecalled ? handleEditRecalled : undefined}
        onRetryMessage={isOwn && originalMessage.status === 'failed' ? onRetryMessage : undefined}
      />
      {knowledgeDocumentDraft != null && (
        <KnowledgeDocumentCreateDialog
          open
          initialContentHtml={knowledgeDocumentDraft.contentHtml}
          initialAttachments={knowledgeDocumentDraft.attachments}
          isZh={cfgLocale === 'zh'}
          onClose={() => setKnowledgeDocumentDraft(null)}
        />
      )}
      {robotQaMessage != null && robotQaRuntime && (
        <RobotQaCreateDialog
          open
          message={robotQaMessage}
          runtime={robotQaRuntime}
          isZh={cfgLocale === 'zh'}
          onClose={() => setRobotQaMessage(null)}
        />
      )}
    </>
  )
}

function ConversationDivider({ label }: { label: string }) {
  return (
    <div className="mb-4 flex justify-center text-[12px] text-[#999999]">
      <span className="shrink-0 rounded-full border border-[#E5E5E5] bg-white px-3 py-1">
        {label}
      </span>
    </div>
  )
}

function HistoryActionButton({
  label,
  loading,
  disabled,
  onClick,
}: {
  label: string
  loading?: boolean
  disabled?: boolean
  onClick?: () => void
}) {
  return (
    <button
      className="mx-auto mb-4 flex items-center gap-1 rounded-full px-4 py-1.5 text-[12px] font-medium text-[#1a1a1a] transition-colors hover:bg-black/[0.04] disabled:cursor-not-allowed disabled:text-[#999999]"
      onClick={onClick}
      disabled={disabled || loading}
      type="button"
    >
      {loading && <IconLoader2 size={14} className="animate-spin" />}
      {label}
    </button>
  )
}

function AgentHistoryMessageBubble({
  message,
  locale,
  visitorAvatarBg,
  imageMessages,
  allMessages,
  readStatusEnabled,
  currentUserId,
}: {
  message: Message
  locale: string
  visitorAvatarBg: string
  imageMessages: { id: string; content: string }[]
  allMessages: Message[]
  readStatusEnabled: boolean
  currentUserId?: number | null
}) {
  return (
    <WorkspaceMessageBubble
      message={message}
      locale={locale as Locale}
      mode="record"
      attachmentContext={{ kind: 'conversation', conversationId: message.conversation_id }}
      visitorAvatarColor={visitorAvatarBg}
      imageGallery={imageMessages}
      allMessages={allMessages}
      currentUserId={currentUserId}
      readStatusEnabled={readStatusEnabled}
      inlinePlayableVideo
      showAgentName={false}
      showVisitorName={false}
      showAssistantAvatar={false}
      onLocateQuotedMessage={(id) => scrollToWorkspaceMessage(id, locale as Locale)}
    />
  )
}

function HistoryConversationBlock({
  conversation,
  locale,
  visitorAvatarBg,
  highlightedMessageId,
  readStatusEnabled,
  currentUserId,
}: {
  conversation: WorkspaceConversationHistoryItem
  locale: string
  visitorAvatarBg: string
  highlightedMessageId: number | null
  readStatusEnabled: boolean
  currentUserId?: number | null
}) {
  const visibleMessages = useMemo(
    () => conversation.messages.filter(isConversationHistoryContentMessage),
    [conversation.messages],
  )
  const imageMessages = useMemo(
    () =>
      visibleMessages
        .filter((msg) => msg.content_type === 'image' && !msg.is_recalled)
        .map((msg) => ({ id: String(msg.id), content: msg.content })),
    [visibleMessages],
  )
  const time = formatHistoryTime(
    conversation.started_at || conversation.created_at || conversation.last_message_at,
    locale,
  )
  const channel = conversation.channel?.name || conversation.channel?.channel_type || '-'
  const label = locale === 'zh'
    ? `${time} 历史会话 · ${channel}`
    : `${time} History · ${channel}`

  return (
    <div>
      <ConversationDivider label={label} />
      <p className="mb-3 text-center text-[11px] text-[#999999]">
        {locale === 'zh' ? '历史会话仅供查看' : 'History is read-only'}
      </p>
      {conversation.messages_truncated && (
        <div className="mb-3 text-center text-[12px] text-[#999999]">
          {locale === 'zh' ? '仅显示最近 200 条消息' : 'Showing latest 200 messages'}
        </div>
      )}
      {visibleMessages.map((message) => (
        <div
          key={message.id}
          data-workspace-message-id={message.id}
          className={cn(
            'rounded-2xl transition-colors duration-300',
            highlightedMessageId === message.id && 'bg-warning/15',
          )}
        >
          <AgentHistoryMessageBubble
            message={message}
            locale={locale}
            visitorAvatarBg={visitorAvatarBg}
            imageMessages={imageMessages}
            allMessages={visibleMessages}
            readStatusEnabled={readStatusEnabled}
            currentUserId={currentUserId}
          />
        </div>
      ))}
    </div>
  )
}

function visitorWebStatusLabel(status: VisitorWebStatus, locale: Locale): string {
  if (status === 'online') return t('ws.chat.visitorWebStatusOnline', locale)
  if (status === 'offline') return t('ws.chat.visitorWebStatusOffline', locale)
  return t('ws.chat.visitorWebStatusUnknown', locale)
}

function visitorWebStatusTooltip(status: VisitorWebStatus, locale: Locale): string {
  if (status === 'unknown') return t('ws.chat.visitorWebStatusUnavailable', locale)
  return t('ws.chat.visitorWebStatusTooltip', locale, {
    status: visitorWebStatusLabel(status, locale),
  })
}

function shouldShowVisitorWebStatus(conversation: Conversation): boolean {
  return (
    String(conversation.channel?.channel_type || '').toLowerCase() === 'web'
    && Boolean(conversation.visitor?.external_id)
  )
}

function VisitorWebStatusBadge({
  conversation,
  socket,
}: {
  conversation: Conversation
  socket: Socket | null
}) {
  const { locale } = useLocaleStore()
  const queryClient = useQueryClient()
  const visible = conversation.status !== 'closed' && shouldShowVisitorWebStatus(conversation)
  const statusQuery = useVisitorWebStatus(conversation.id, {
    enabled: visible,
    refetchInterval: 5_000,
  })

  useEffect(() => {
    if (!socket || !visible) return

    const handleStatusUpdated = (payload: VisitorWebStatusResponse) => {
      if (payload.conversation_id !== conversation.id) return
      setVisitorWebStatusQueryData(queryClient, payload)
    }

    const handleConnect = () => {
      queryClient.invalidateQueries({
        queryKey: conversationKeys.visitorWebStatus(conversation.id),
      })
    }

    socket.on('visitor_web_status_updated', handleStatusUpdated)
    socket.on('connect', handleConnect)
    return () => {
      socket.off('visitor_web_status_updated', handleStatusUpdated)
      socket.off('connect', handleConnect)
    }
  }, [conversation.id, queryClient, socket, visible])

  if (!visible) return null

  if (statusQuery.isLoading && !statusQuery.data) {
    const label = t('ws.chat.visitorWebStatusChecking', locale)
    return (
      <span
        aria-label={label}
        className="inline-flex h-[22px] w-14 shrink-0 items-center rounded-full bg-muted px-2"
        title={label}
      >
        <span className="h-2 w-full animate-pulse rounded-full bg-muted-foreground/20" />
      </span>
    )
  }

  if (statusQuery.data && !statusQuery.data.can_display) return null

  const status: VisitorWebStatus = statusQuery.isError
    ? 'unknown'
    : statusQuery.data?.status ?? 'unknown'
  const label = visitorWebStatusLabel(status, locale)
  const tooltip = visitorWebStatusTooltip(status, locale)
  const online = status === 'online'

  return (
    <span
      aria-label={tooltip}
      className={cn(
        'inline-flex h-[22px] max-w-24 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[12px] font-medium',
        online
          ? 'border-success/20 bg-success/10 text-success'
          : 'border-border bg-muted text-muted-foreground',
      )}
      title={tooltip}
    >
      <span
        className={cn(
          'h-1.5 w-1.5 shrink-0 rounded-full',
          online ? 'bg-success' : 'bg-muted-foreground/70',
        )}
      />
      <span className="min-w-0 truncate">{label}</span>
    </span>
  )
}

// ─── Main Thread ─────────────────────────────────────────────────

type AgentThreadProps = {
  socket: Socket | null
  composerInsertRequest?: ComposerInsertRequest | null
  onComposerInsertRequest?: (request: Omit<ComposerInsertRequest, 'id' | 'conversationId'>) => void
  composerInputHeight?: number
  onComposerInputHeightCommit?: (height: number) => void
  onComposerContentTypeChange?: (contentType: ComposerContentType) => void
  messageSearchOpen?: boolean
  onOpenMessageSearch?: () => void
  messageSearchTarget?: {
    conversationId: number
    messageId: number
    requestId: number
  } | null
}

export function AgentThread({
  socket,
  composerInsertRequest,
  onComposerInsertRequest,
  composerInputHeight,
  onComposerInputHeightCommit,
  onComposerContentTypeChange,
  messageSearchOpen,
  onOpenMessageSearch,
  messageSearchTarget,
}: AgentThreadProps) {
  const {
    conversation,
    isClosed,
    isTyping,
    visitorTypingContent,
    hasMore,
    loadingMore,
    historyAvailable,
    historyConversations,
    historyHasMore,
    historyLoading,
    historyLoaded,
    historyError,
    historyLimitReached,
    onLoadMore,
    onLoadHistory,
    onEndConversation,
    onCreateTicket,
    canCreateTicket,
    canPinConversation,
    pinningConversation,
    onTogglePinConversation,
    canLockConversationTimeout,
    lockingConversationTimeout,
    onToggleConversationTimeoutLock,
    canTransfer,
    canEndConversation,
    canInviteCollaborator,
    canStartNewConversation,
    startNewConversationDisabledReason,
    startingNewConversation,
    onStartNewConversation,
    onTransferred,
    onCollaborationInvitationSent,
    readStatusEnabled,
  } = useAgentChatConfig()
  const { locale } = useLocaleStore()
  const currentUser = useAuthStore((state) => state.user)
  const currentUserId = currentUser?.id
  const canUseRobotQa = hasPermission(currentUser, 'chat.conversation.robot_qa.create')
  const robotQaRuntime = useRobotQaRuntime(canUseRobotQa)
  const currentMessages = useChatStore((state) => state.messages.get(conversation.id) || EMPTY_MESSAGES)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [highlightedMessageId, setHighlightedMessageId] = useState<number | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pendingScrollDeltaRef = useRef<number | null>(null)
  const isNearBottomRef = useRef(true)
  const loadedSearchTargetRef = useRef<string | null>(null)
  const lastTailMessageRef = useRef<{ conversationId: number; messageId: number | null }>({
    conversationId: conversation.id,
    messageId: null,
  })
  const visitorAvatarBg = conversation.visitor?.avatar_color || '#4A8C5C'
  const latestMessage = currentMessages[currentMessages.length - 1]
  const latestMessageId = latestMessage?.id ?? null
  const isPeerConversation = conversation.viewer_relation === 'peer'
  const isCollaboratorConversation = conversation.viewer_relation === 'collaborator'
  const ownerName = conversation.agent?.display_name || conversation.agent?.name
  const collaboratorNames = (conversation.collaborators ?? [])
    .map((agent) => agent.display_name || agent.name)
    .filter(Boolean)
  const visibleHistoryConversations = useMemo(
    () => historyConversations.filter((item) => item.messages.some(isConversationHistoryContentMessage)),
    [historyConversations],
  )
  const oldestHistoryId = historyConversations[0]?.id
  const showHistoryEntry = historyAvailable && !historyLoaded
  const showCurrentDivider = historyLoaded && visibleHistoryConversations.length > 0
  const showHistoryDone =
    historyLoaded && visibleHistoryConversations.length > 0 && (!historyHasMore || historyLimitReached)
  const historyEndTime = formatHistoryTime(
    conversation.ended_at || conversation.last_message_at || conversation.created_at,
    locale,
  )
  const pinLabel = conversation.is_pinned
    ? t('ws.chat.unpinConversation', locale)
    : t('ws.chat.pinConversation', locale)
  const timeoutLockLabel = conversation.is_timeout_locked
    ? t('ws.chat.unlockConversationTimeout', locale)
    : t('ws.chat.lockConversationTimeout', locale)

  const loadHistoryWithAnchor = useCallback(
    async (beforeId?: number) => {
      const viewport = viewportRef.current
      pendingScrollDeltaRef.current = viewport ? viewport.scrollHeight - viewport.scrollTop : null
      await onLoadHistory(beforeId)
    },
    [onLoadHistory],
  )

  useLayoutEffect(() => {
    if (pendingScrollDeltaRef.current == null) return
    const viewport = viewportRef.current
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight - pendingScrollDeltaRef.current
    }
    pendingScrollDeltaRef.current = null
  }, [historyConversations.length])

  const updateNearBottom = useCallback(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    isNearBottomRef.current = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 80
  }, [])

  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    const scroll = () => {
      const viewport = viewportRef.current
      if (!viewport) return
      viewport.scrollTo({ top: viewport.scrollHeight, behavior })
      isNearBottomRef.current = true
    }

    scroll()
    window.requestAnimationFrame(scroll)
  }, [])

  useLayoutEffect(() => {
    const previousTail = lastTailMessageRef.current
    const conversationChanged = previousTail.conversationId !== conversation.id
    const tailChanged = conversationChanged || previousTail.messageId !== latestMessageId

    lastTailMessageRef.current = {
      conversationId: conversation.id,
      messageId: latestMessageId,
    }

    if (!latestMessage || !tailChanged) return

    if (conversationChanged || previousTail.messageId == null) {
      scrollToBottom('auto')
      return
    }

    const isOwnAgentMessage =
      latestMessage.sender_type === 'agent' && latestMessage.sender_id === currentUserId
    if (isOwnAgentMessage || isNearBottomRef.current) {
      scrollToBottom('smooth')
    }
  }, [
    conversation.id,
    currentUserId,
    latestMessage,
    latestMessageId,
    scrollToBottom,
  ])

  useEffect(() => {
    if (!messageSearchTarget || messageSearchTarget.conversationId !== conversation.id) return
    const key = `${messageSearchTarget.requestId}:${messageSearchTarget.messageId}`
    const selector = `[data-workspace-message-id="${messageSearchTarget.messageId}"]`

    const scrollToTarget = () => {
      const node = viewportRef.current?.querySelector<HTMLElement>(selector)
      if (!node) return false
      node.scrollIntoView({ block: 'center', behavior: 'smooth' })
      setHighlightedMessageId(messageSearchTarget.messageId)
      window.setTimeout(() => {
        setHighlightedMessageId((current) => (
          current === messageSearchTarget.messageId ? null : current
        ))
      }, 2000)
      return true
    }

    window.requestAnimationFrame(() => {
      if (scrollToTarget()) return
      if (loadedSearchTargetRef.current === key) return
      loadedSearchTargetRef.current = key
      get<MessageListResponse>(`v1/conversations/${conversation.id}/messages`, {
        searchParams: { before_id: messageSearchTarget.messageId + 1, limit: 20 },
      })
        .then((data) => {
          const merged = [...data.items, ...currentMessages]
          const seen = new Set<number>()
          const nextMessages = merged
            .filter((message) => {
              if (seen.has(message.id)) return false
              seen.add(message.id)
              return true
            })
            .sort((a, b) => a.id - b.id)
          useChatStore.getState().setMessages(conversation.id, nextMessages)
          window.requestAnimationFrame(() => {
            if (!scrollToTarget()) {
              window.alert(t('ws.chat.messageSearch.locateFailed', locale))
            }
          })
        })
        .catch(() => {
          window.alert(t('ws.chat.messageSearch.locateFailed', locale))
        })
    })
  }, [conversation.id, currentMessages, locale, messageSearchTarget])

  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col bg-[#FAFAFA]">
      {/* 会话头部 — 2.1 pen: #FAFAFA, 56px, px 24 */}
      <div className="mt-px flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5E5] bg-[#FAFAFA] px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-base font-semibold text-[#1a1a1a]">
            {conversation.visitor?.name || `#${conversation.id}`}
          </span>
          {conversation.channel && (
            <span className="shrink-0 rounded border border-[#E5E5E5] bg-[#F5F5F5] px-2 py-0.5 text-[12px] font-medium capitalize text-[#737373]">
              {conversation.channel.channel_type}
            </span>
          )}
          {isClosed && (
            <span className="shrink-0 rounded border border-[#E5E5E5] bg-[#F0F0F0] px-2 py-0.5 text-[12px] font-medium text-[#737373]">
              {t('ws.chat.historyConversation', locale)}
            </span>
          )}
          {isClosed && (
            <span className="max-w-44 truncate text-[12px] text-[#737373]" title={historyEndTime}>
              {historyEndTime}
            </span>
          )}
          <VisitorWebStatusBadge conversation={conversation} socket={socket} />
          {conversation.is_timeout_locked && (
            <span className="shrink-0 rounded border border-[#D6D6D6] bg-[#F0F0F0] px-2 py-0.5 text-[12px] font-medium text-[#555555]">
              {t('ws.chat.timeoutLocked', locale)}
            </span>
          )}
          {isPeerConversation && (
            <span className="shrink-0 rounded border border-[#E5E5E5] bg-[#F5F5F5] px-2 py-0.5 text-[12px] font-medium text-[#737373]">
              {t('ws.chat.peerConversation', locale)}
            </span>
          )}
          {isCollaboratorConversation && (
            <span className="shrink-0 rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[12px] font-medium text-emerald-700">
              {t('ws.chat.collaboratingBadge', locale)}
            </span>
          )}
          {(isPeerConversation || isCollaboratorConversation) && ownerName && (
            <span className="max-w-40 truncate text-[12px] text-[#737373]" title={ownerName}>
              {t('ws.chat.ownerLabel', locale, { name: ownerName })}
            </span>
          )}
          {collaboratorNames.length > 0 && (
            <span
              className="max-w-48 truncate text-[12px] text-[#737373]"
              title={collaboratorNames.join(', ')}
            >
              {t('ws.chat.collaboratorsLabel', locale, {
                names: collaboratorNames.slice(0, 2).join(', '),
              })}
              {collaboratorNames.length > 2 ? ` +${collaboratorNames.length - 2}` : ''}
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {canPinConversation && (
            <button
              onClick={onTogglePinConversation}
              disabled={pinningConversation}
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                conversation.is_pinned
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'bg-[#E8E8E8] text-[#666666] hover:bg-[#DDDDDD]',
              )}
              title={pinLabel}
              aria-label={pinLabel}
              type="button"
            >
              {pinningConversation ? (
                <IconLoader2 size={16} stroke={1.5} className="animate-spin" />
              ) : (
                <IconPinned size={16} stroke={1.5} />
              )}
            </button>
          )}
          {canLockConversationTimeout && (
            <button
              onClick={onToggleConversationTimeoutLock}
              disabled={lockingConversationTimeout}
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                conversation.is_timeout_locked
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'bg-[#E8E8E8] text-[#666666] hover:bg-[#DDDDDD]',
              )}
              title={timeoutLockLabel}
              aria-label={timeoutLockLabel}
              type="button"
            >
              {lockingConversationTimeout ? (
                <IconLoader2 size={16} stroke={1.5} className="animate-spin" />
              ) : conversation.is_timeout_locked ? (
                <IconLockOpen size={16} stroke={1.5} />
              ) : (
                <IconLock size={16} stroke={1.5} />
              )}
            </button>
          )}
          {isClosed && (
            <button
              onClick={onStartNewConversation}
              disabled={!canStartNewConversation || startingNewConversation}
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD] disabled:cursor-not-allowed disabled:opacity-50"
              title={startNewConversationDisabledReason || t('ws.chat.startNewConversation', locale)}
              type="button"
            >
              {startingNewConversation ? (
                <IconLoader2 size={16} stroke={1.5} className="animate-spin" />
              ) : (
                <IconMessagePlus size={16} stroke={1.5} />
              )}
              {t('ws.chat.startNewConversation', locale)}
            </button>
          )}
          {canCreateTicket && (
            <button
              onClick={onCreateTicket}
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.createTicket', locale)}
              type="button"
            >
              <IconTicket size={16} stroke={1.5} />
              {t('ws.chat.createTicket', locale)}
            </button>
          )}
          {!isClosed && canInviteCollaborator && conversation.agent && (
            <button
              onClick={() => setShowInviteModal(true)}
              data-action="invite-collaborator"
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.collabInviteAction', locale)}
              type="button"
            >
              <IconUserPlus size={16} stroke={1.5} />
              {t('ws.chat.collabInviteAction', locale)}
            </button>
          )}
          {!isClosed && canTransfer && conversation.agent && (
            <button
              onClick={() => setShowTransferModal(true)}
              data-action="transfer-conversation"
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.transfer', locale)}
              type="button"
            >
              <IconArrowsExchange2 size={16} stroke={1.5} />
              {t('ws.chat.transfer', locale)}
            </button>
          )}
          {canEndConversation && (
            <button
              onClick={onEndConversation}
              data-action="end-conversation"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#E8E8E8] text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.endConversation', locale)}
              type="button"
            >
              <IconX size={18} stroke={1.5} />
            </button>
          )}
        </div>
      </div>

      <ThreadPrimitive.Viewport
        ref={viewportRef}
        onScroll={updateNearBottom}
        className="relative flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain bg-[#FAFAFA] px-6 py-5"
      >
        {showHistoryEntry && (
          <HistoryActionButton
            label={
              historyError
                ? t('ws.chat.historyLoadFailed', locale)
                : t('ws.chat.viewHistory', locale)
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor()}
          />
        )}

        {historyLoaded && historyHasMore && !historyLimitReached && (
          <HistoryActionButton
            label={
              historyError
                ? t('ws.chat.historyLoadFailed', locale)
                : t('ws.chat.loadMoreHistory', locale)
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor(oldestHistoryId)}
          />
        )}

        {showHistoryDone && (
          <HistoryActionButton
            label={
              historyLimitReached
                ? t('ws.chat.historyLimitReached', locale)
                : t('ws.chat.noMoreHistory', locale)
            }
            disabled
          />
        )}

        {visibleHistoryConversations.map((historyConversation) => (
          <HistoryConversationBlock
            key={historyConversation.id}
            conversation={historyConversation}
            locale={locale}
            visitorAvatarBg={visitorAvatarBg}
            highlightedMessageId={highlightedMessageId}
            readStatusEnabled={readStatusEnabled}
            currentUserId={currentUserId}
          />
        ))}

        {showCurrentDivider && (
          <ConversationDivider label={t('ws.chat.currentConversation', locale)} />
        )}

        {hasMore ? (
          <button
            className="mx-auto mb-4 flex items-center gap-1 rounded-full px-4 py-1.5 text-[12px] text-[#999999] transition-colors hover:bg-black/[0.04]"
            onClick={onLoadMore}
            disabled={loadingMore}
            type="button"
          >
            {loadingMore ? (
              <IconLoader2 size={14} className="animate-spin" />
            ) : (
              t('ws.chat.loadMore', locale)
            )}
          </button>
        ) : (
          <p className="mb-4 text-center text-[12px] text-[#999999]">{t('ws.chat.noMoreMessages', locale)}</p>
        )}

        {/* Messages */}
        <ThreadPrimitive.Messages>
          {({ message }: { message: MessageState }) => (
            <div
              data-workspace-message-id={message.id}
              className={cn(
                'rounded-2xl transition-colors duration-300',
                highlightedMessageId === Number(message.id) && 'bg-warning/15',
              )}
            >
              <AgentMessageBubble
                message={message}
                socket={socket}
                robotQaRuntime={canUseRobotQa ? robotQaRuntime.data : undefined}
                onComposerInsertRequest={onComposerInsertRequest}
              />
            </div>
          )}
        </ThreadPrimitive.Messages>

        {/* Visitor typing preview */}
        {isTyping && (
          <div className="mb-4 flex">
            <div className="flex min-w-0 max-w-[70%] flex-col items-start gap-1">
              {visitorTypingContent ? (
                <>
                  <div className="max-w-full rounded-[18px] border border-dashed border-[#D0D0D0] bg-white px-3.5 py-2.5 text-sm leading-normal break-words break-all whitespace-pre-wrap text-[#1a1a1a] shadow-sm">
                    {visitorTypingContent}
                  </div>
                  <span className="pl-1 text-[11px] italic text-[#999999]">{t('ws.chat.visitorTyping', locale)}</span>
                </>
              ) : (
                <div className="text-[12px] italic text-[#999999]">{t('ws.chat.visitorTyping', locale)}</div>
              )}
            </div>
          </div>
        )}
      </ThreadPrimitive.Viewport>

      {/* ── Composer ── */}
      <AgentComposer
        disabled={isClosed && !canStartNewConversation}
        disabledReason={startNewConversationDisabledReason}
        socket={socket}
        insertRequest={composerInsertRequest}
        inputHeight={composerInputHeight}
        onInputHeightCommit={onComposerInputHeightCommit}
        onContentTypeChange={onComposerContentTypeChange}
        messageSearchOpen={messageSearchOpen}
        onOpenMessageSearch={onOpenMessageSearch}
      />

      {/* ── Transfer conversation modal ── */}
      {canTransfer && (
        <TransferConversationModal
          conversation={conversation}
          open={showTransferModal}
          onClose={() => setShowTransferModal(false)}
          onTransferred={(toName) => {
            setShowTransferModal(false)
            onTransferred(toName)
          }}
        />
      )}

      {canInviteCollaborator && (
        <InviteCollaboratorModal
          conversation={conversation}
          open={showInviteModal}
          onClose={() => setShowInviteModal(false)}
          onInvited={(name) => {
            setShowInviteModal(false)
            onCollaborationInvitationSent(name)
          }}
        />
      )}
    </ThreadPrimitive.Root>
  )
}
