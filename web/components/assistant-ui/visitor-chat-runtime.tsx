'use client'

import {
  createContext,
  useContext,
  useCallback,
  useEffect,
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
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import type {
  Message,
  OpenAgentTextBlock,
  OpenAgentThinkingBlock,
  OpenAgentToolBlock,
  VisitorConversationHistoryItem,
} from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import type { ChannelPublicConfig } from '@/service/use-visitor-chat'
import { uploadVisitorConversationFile } from '@/service/use-conversation-files'
import type { SatisfactionSurveyRecord } from '@/models/satisfaction-survey'
import type { Socket } from 'socket.io-client'
import {
  streamOpenAgentConversation,
  isHumanHandoffEventPayload,
  type HumanHandoffEventPayload,
  type OpenAgentLlmStepPayload,
  type OpenAgentThinkingDeltaPayload,
  type OpenAgentToolCallPayload,
  type OpenAgentToolResultPayload,
  type OpenAgentStreamController,
} from '@/service/use-open-agent-conversation'

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
  botMode: boolean
  botRunning: boolean
  visitorMessageCount: number
  pendingHumanHandoff: {
    payload: HumanHandoffEventPayload
    brief: string
    messageId?: number
    toolCallId?: string
  } | null
  handoffRouting: boolean
  satisfactionCanInitiate: boolean
  satisfactionLoading: boolean
  onLoadMore: () => void
  onLoadHistory: (beforeId?: string) => Promise<void>
  onTyping: (content: string) => void
  onRestartConversation: () => Promise<void>
  onRequestHumanHandoff: (payload?: HumanHandoffEventPayload | null) => Promise<boolean>
  onDismissHumanHandoff: () => void
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
  metadata?: Record<string, unknown>
  eventType?: string
  handoffPayload?: unknown
  messageStatus?: string
  streaming?: boolean
  openAgentThinkingBlocks?: OpenAgentThinkingBlock[]
  openAgentToolBlocks?: OpenAgentToolBlock[]
  openAgentTextBlocks?: OpenAgentTextBlock[]
  showTimestamp: boolean
  showName: boolean
  showAvatar: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────

function mapRole(senderType: string): 'user' | 'assistant' | 'system' {
  if (senderType === 'visitor') return 'user'
  if (senderType === 'agent' || senderType === 'bot') return 'assistant'
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

function getStringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function getNumberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function getOpenAgentThinkingBlocks(metadata?: Record<string, unknown>): OpenAgentThinkingBlock[] {
  const value = metadata?.open_agent_thinking_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentThinkingBlock[] => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    const id = getStringValue(record.id)
    const content = getStringValue(record.content)
    if (!id) return []
    return [{
      id,
      content,
      llmStepId: getNumberValue(record.llmStepId) ?? getNumberValue(record.llm_step_id),
      isStreaming: record.isStreaming === true || record.is_streaming === true,
      timelineIndex: getNumberValue(record.timelineIndex) ?? getNumberValue(record.timeline_index) ?? 0,
    }]
  })
}

export function getOpenAgentToolBlocks(metadata?: Record<string, unknown>): OpenAgentToolBlock[] {
  const value = metadata?.open_agent_tool_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentToolBlock[] => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    const toolCallId = getStringValue(record.toolCallId) || getStringValue(record.tool_call_id)
    const toolName = getStringValue(record.toolName) || getStringValue(record.tool_name)
    const id = getStringValue(record.id) || (toolCallId ? `tool_${toolCallId}` : '')
    if (!id || !toolCallId) return []
    return [{
      id,
      toolName,
      brief: getStringValue(record.brief) || toolName || '工具调用',
      toolCallId,
      stepId: getNumberValue(record.stepId) ?? getNumberValue(record.step_id),
      isExecuting: record.isExecuting === true || record.is_executing === true,
      timelineIndex: getNumberValue(record.timelineIndex) ?? getNumberValue(record.timeline_index) ?? 0,
      arguments: record.arguments ?? record.args,
      result: record.result,
      usedForHandoff: record.usedForHandoff === true || record.used_for_handoff === true,
    }]
  })
}

export function getOpenAgentTextBlocks(metadata?: Record<string, unknown>): OpenAgentTextBlock[] {
  const value = metadata?.open_agent_text_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentTextBlock[] => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    const id = getStringValue(record.id)
    const content = getStringValue(record.content)
    if (!id || content.length === 0) return []
    return [{
      id,
      content,
      isStreaming: record.isStreaming === true || record.is_streaming === true,
      timelineIndex: getNumberValue(record.timelineIndex) ?? getNumberValue(record.timeline_index) ?? 0,
    }]
  })
}

function getToolCallId(data: OpenAgentToolCallPayload | OpenAgentToolResultPayload, fallback: string): string {
  return getStringValue(data.tool_call_id) || getStringValue(data.id) || fallback
}

function buildToolBrief(data: OpenAgentToolCallPayload, toolName: string): string {
  const brief = getStringValue(data.brief)
  if (brief) return brief
  if (toolName) return `调用 ${toolName}`
  return '调用工具'
}

function upsertToolCallBlock(
  blocks: OpenAgentToolBlock[],
  data: OpenAgentToolCallPayload,
  timelineIndex: number,
): OpenAgentToolBlock[] {
  const toolName = getStringValue(data.tool_name) || getStringValue(data.name)
  const stepId = getNumberValue(data.step_id)
  const toolCallId = getToolCallId(data, stepId !== null ? `step_${stepId}` : `tool_${timelineIndex}`)
  const nextBlock: OpenAgentToolBlock = {
    id: `tool_${toolCallId}`,
    toolName,
    brief: buildToolBrief(data, toolName),
    toolCallId,
    stepId,
    isExecuting: true,
    timelineIndex,
    arguments: data.arguments ?? data.args,
  }

  const index = blocks.findIndex((block) => block.toolCallId === toolCallId)
  if (index === -1) return [...blocks, nextBlock]
  const next = [...blocks]
  next[index] = { ...next[index], ...nextBlock, timelineIndex: next[index].timelineIndex || timelineIndex }
  return next
}

function applyToolResultBlock(
  blocks: OpenAgentToolBlock[],
  data: OpenAgentToolResultPayload,
  timelineIndex: number,
): OpenAgentToolBlock[] {
  const toolCallId = getToolCallId(data, `tool_${timelineIndex}`)
  const index = blocks.findIndex((block) => block.toolCallId === toolCallId)
  if (index === -1) {
    const toolName = getStringValue(data.tool_name)
    return [
      ...blocks,
      {
        id: `tool_${toolCallId}`,
        toolName,
        brief: toolName ? `调用 ${toolName}` : '工具调用',
        toolCallId,
        stepId: null,
        isExecuting: false,
        timelineIndex,
        result: data.result,
      },
    ]
  }

  const next = [...blocks]
  next[index] = { ...next[index], isExecuting: false, result: data.result }
  return next
}

function finishToolBlocks(blocks: OpenAgentToolBlock[]): OpenAgentToolBlock[] {
  return blocks.map((block) => ({ ...block, isExecuting: false }))
}

function appendTextBlock(
  blocks: OpenAgentTextBlock[],
  content: string,
  timelineIndex: number,
): OpenAgentTextBlock[] {
  if (!content) return blocks

  const last = blocks[blocks.length - 1]
  if (last?.isStreaming) {
    const next = [...blocks]
    next[next.length - 1] = {
      ...last,
      content: `${last.content}${content}`,
    }
    return next
  }

  return [
    ...blocks,
    {
      id: `text_${timelineIndex}`,
      content,
      isStreaming: true,
      timelineIndex,
    },
  ]
}

function finishTextBlocks(blocks: OpenAgentTextBlock[]): OpenAgentTextBlock[] {
  return blocks.map((block) => ({ ...block, isStreaming: false }))
}

function textBlocksContent(blocks: OpenAgentTextBlock[]): string {
  return blocks.map((block) => block.content).join('')
}

function isTextAlreadyRepresented(
  existingText: string,
  finalText: string,
): boolean {
  return Boolean(existingText) && existingText.trim() === finalText.trim()
}

function getThinkingDeltaText(data: OpenAgentThinkingDeltaPayload): string {
  return getStringValue(data.content) || getStringValue(data.delta) || getStringValue(data.text)
}

function getLlmStepId(data: OpenAgentLlmStepPayload): number | null {
  return getNumberValue(data.step_id)
}

function appendThinkingBlock(
  blocks: OpenAgentThinkingBlock[],
  data: OpenAgentThinkingDeltaPayload,
  timelineIndex: number,
  llmStepId: number | null,
): OpenAgentThinkingBlock[] {
  const content = getThinkingDeltaText(data)
  if (!content) return blocks

  const last = blocks[blocks.length - 1]
  if (last?.isStreaming) {
    const next = [...blocks]
    next[next.length - 1] = {
      ...last,
      content: `${last.content}${content}`,
      llmStepId: last.llmStepId ?? llmStepId,
    }
    return next
  }

  return [
    ...blocks,
    {
      id: `think_${timelineIndex}`,
      content,
      llmStepId,
      isStreaming: true,
      timelineIndex,
    },
  ]
}

function finishThinkingBlocks(
  blocks: OpenAgentThinkingBlock[],
  llmStepId?: number | null,
): OpenAgentThinkingBlock[] {
  return blocks.map((block) => ({
    ...block,
    llmStepId: block.llmStepId ?? llmStepId ?? null,
    isStreaming: false,
  }))
}

function applyThinkingStepId(
  blocks: OpenAgentThinkingBlock[],
  llmStepId: number | null,
): OpenAgentThinkingBlock[] {
  if (llmStepId === null) return blocks
  return blocks.map((block) => (
    block.isStreaming ? { ...block, llmStepId } : block
  ))
}

// ─── OpenAgent in-flight turn persistence ───────────────────────

const OPEN_AGENT_PENDING_TURN_VERSION = 1
const OPEN_AGENT_PENDING_TURN_TTL_MS = 10 * 60 * 1000

type PendingOpenAgentTurn = {
  schemaVersion: typeof OPEN_AGENT_PENDING_TURN_VERSION
  conversationPublicId: string
  message: string
  requestId: string
  clientMessageId: string
  lastEventId: string | null
  createdAt: number
  updatedAt: number
}

function pendingOpenAgentTurnKey(conversationPublicId: string): string {
  return `opendesk_open_agent_pending_turn_${conversationPublicId}`
}

function generateRequestId(): string {
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

function generateClientMessageId(): string {
  const c = (typeof crypto !== 'undefined' ? crypto : null) as Crypto | null
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `cm_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`
}

function isPendingTurn(value: unknown): value is PendingOpenAgentTurn {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return record.schemaVersion === OPEN_AGENT_PENDING_TURN_VERSION
    && typeof record.conversationPublicId === 'string'
    && typeof record.message === 'string'
    && typeof record.requestId === 'string'
    && typeof record.clientMessageId === 'string'
    && (typeof record.lastEventId === 'string' || record.lastEventId === null)
    && typeof record.createdAt === 'number'
    && typeof record.updatedAt === 'number'
}

function readPendingOpenAgentTurn(conversationPublicId: string): PendingOpenAgentTurn | null {
  if (typeof window === 'undefined') return null
  const key = pendingOpenAgentTurnKey(conversationPublicId)
  const removeStoredTurn = () => {
    try {
      window.localStorage.removeItem(key)
    } catch {
      // localStorage can be unavailable in privacy-restricted contexts.
    }
  }
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    if (!isPendingTurn(parsed) || parsed.conversationPublicId !== conversationPublicId) {
      removeStoredTurn()
      return null
    }
    if (Date.now() - parsed.updatedAt > OPEN_AGENT_PENDING_TURN_TTL_MS) {
      removeStoredTurn()
      return null
    }
    return parsed
  } catch {
    removeStoredTurn()
    return null
  }
}

function storePendingOpenAgentTurn(turn: PendingOpenAgentTurn): PendingOpenAgentTurn {
  const next = { ...turn, updatedAt: Date.now() }
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(pendingOpenAgentTurnKey(turn.conversationPublicId), JSON.stringify(next))
    } catch {
      // A disabled or full localStorage should not break message sending.
    }
  }
  return next
}

function clearPendingOpenAgentTurn(conversationPublicId: string) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(pendingOpenAgentTurnKey(conversationPublicId))
  } catch {
    // localStorage can be unavailable in privacy-restricted contexts.
  }
}

function getMetadataString(message: Message, key: string): string | null {
  const value = message.metadata?.[key]
  return typeof value === 'string' ? value : null
}

function isHumanHandoffToolName(toolName: string): boolean {
  return toolName.trim().toLowerCase() === 'human_handoff'
}

function isHumanHandoffToolBlock(block: OpenAgentToolBlock): boolean {
  return isHumanHandoffToolName(block.toolName) || block.usedForHandoff === true
}

function resolveToolEventName(
  data: OpenAgentToolCallPayload | OpenAgentToolResultPayload,
): string {
  return getStringValue(data.tool_name) || getStringValue(data.name)
}

function stripHumanHandoffToolBlocks(blocks: OpenAgentToolBlock[]): OpenAgentToolBlock[] {
  return blocks.filter((block) => !isHumanHandoffToolBlock(block))
}

function isOpenAgentHandoffMessage(message: Message): boolean {
  return (
    message.metadata?.event_type === 'open_agent_handoff_event'
    || message.event_type === 'open_agent_handoff_event'
  )
}

function resolveHandoffPayloadFromMessage(message: Message): HumanHandoffEventPayload | null {
  const payload = message.metadata?.handoff_payload
  if (isHumanHandoffEventPayload(payload)) return payload
  return null
}

function resolveHandoffEventType(message: Message): string | null {
  const value = message.metadata?.handoff_event_type
  return typeof value === 'string' ? value : null
}

function resolveHandoffBrief(
  payload: HumanHandoffEventPayload,
  fallbackContent: string,
  locale: string,
): string {
  const brief = payload.handoff?.brief?.trim()
  if (brief) return brief
  if (fallbackContent.trim()) return fallbackContent.trim()
  return locale === 'zh'
    ? '这个问题需要人工客服进一步处理。'
    : 'This issue needs a human support agent to take a closer look.'
}

function isFinalBotMessage(message: Message): boolean {
  return message.sender_type === 'bot' && message.metadata?.streaming !== true
}

function isPendingTurnAlreadyTerminal(messages: Message[], turn: PendingOpenAgentTurn): boolean {
  const visitorIndex = messages.findIndex((message) =>
    message.sender_type === 'visitor'
    && getMetadataString(message, 'client_message_id') === turn.clientMessageId,
  )

  const hasSavedBotMessage = messages.some((message) =>
    isFinalBotMessage(message)
    && (
      getMetadataString(message, 'client_message_id') === turn.clientMessageId
      || getMetadataString(message, 'open_agent_request_id') === turn.requestId
    ),
  )
  if (hasSavedBotMessage) return true

  const followingMessages = visitorIndex >= 0
    ? messages.slice(visitorIndex + 1)
    : messages.filter((message) => {
      const createdAt = Date.parse(message.created_at)
      return Number.isNaN(createdAt) || createdAt >= turn.createdAt - 5000
    })

  return followingMessages.some((message) =>
    isFinalBotMessage(message),
  )
}

// ─── Provider ────────────────────────────────────────────────────

type ProviderProps = Omit<
  VisitorChatConfigValue,
  | 'onFileSend'
  | 'botRunning'
  | 'handoffRouting'
  | 'onRequestHumanHandoff'
  | 'onDismissHumanHandoff'
> & {
  socket: Socket | null
  onConversationStatusChange: (status: string | null) => void
  children: ReactNode
}

type RunOpenAgentTurnOptions = {
  text: string
  requestId?: string
  clientMessageId?: string
  lastEventId?: string | null
  resume?: boolean
  addVisitorOptimistic?: boolean
}

type ThreadMessageContentPart = Exclude<ThreadMessageLike['content'], string>[number]

const OPEN_AGENT_THINKING_PART_TEXT = 'thinking'

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toToolArgs(value: unknown): Record<string, unknown> {
  return isPlainRecord(value) ? value : {}
}

function stringifyToolArgs(value: Record<string, unknown>): string {
  try {
    return JSON.stringify(value)
  } catch {
    return '{}'
  }
}

function buildOpenAgentAssistantContent(message: Message): ThreadMessageContentPart[] {
  const parts: ThreadMessageContentPart[] = []
  const textBlocks = getOpenAgentTextBlocks(message.metadata)
    .sort((a, b) => a.timelineIndex - b.timelineIndex)
  const thinkingBlocks = getOpenAgentThinkingBlocks(message.metadata)
    .sort((a, b) => a.timelineIndex - b.timelineIndex)
  const visibleToolBlocks = getOpenAgentToolBlocks(message.metadata)
    .filter((block) => !isHumanHandoffToolBlock(block))
    .sort((a, b) => a.timelineIndex - b.timelineIndex)
  const traceBlocks = [
    ...textBlocks.map((block) => ({ type: 'text' as const, block, timelineIndex: block.timelineIndex })),
    ...thinkingBlocks.map((block) => ({ type: 'thinking' as const, block, timelineIndex: block.timelineIndex })),
    ...visibleToolBlocks.map((block) => ({ type: 'tool' as const, block, timelineIndex: block.timelineIndex })),
  ].sort((a, b) => a.timelineIndex - b.timelineIndex)

  if (textBlocks.length === 0 && thinkingBlocks.length === 0 && visibleToolBlocks.length > 0) {
    parts.push({
      type: 'reasoning',
      text: OPEN_AGENT_THINKING_PART_TEXT,
      parentId: `open-agent-thinking-${message.id}`,
    })
  }

  for (const item of traceBlocks) {
    if (item.type === 'text') {
      parts.push({
        type: 'text',
        text: item.block.content,
        parentId: item.block.id,
      })
      continue
    }

    if (item.type === 'thinking') {
      parts.push({
        type: 'reasoning',
        text: item.block.content || OPEN_AGENT_THINKING_PART_TEXT,
        parentId: item.block.id,
      })
      continue
    }

    const block = item.block
    const args = toToolArgs(block.arguments)
    parts.push({
      type: 'tool-call',
      toolCallId: block.toolCallId,
      toolName: block.toolName.trim() || 'open_agent_tool',
      args,
      argsText: stringifyToolArgs(args),
      result: block.result,
      artifact: {
        brief: block.brief,
        isExecuting: block.isExecuting,
        timelineIndex: block.timelineIndex,
      },
    } as ThreadMessageContentPart)
  }

  if (textBlocks.length === 0 && message.content.trim().length > 0) {
    parts.push({ type: 'text', text: message.content })
  }

  return parts
}

export function VisitorChatRuntimeProvider({
  children,
  socket,
  onConversationStatusChange,
  ...chatConfig
}: ProviderProps) {
  const messages = useVisitorChatStore((s) => s.messages)
  const { conversationPublicId, visitorSessionToken } = chatConfig
  const [botRunning, setBotRunning] = useState(false)
  const abortRef = useRef<OpenAgentStreamController | null>(null)
  const pendingTurnRef = useRef<PendingOpenAgentTurn | null>(null)
  const detachedRequestIdsRef = useRef<Set<string>>(new Set())
  const resumedClientMessageIdRef = useRef<string | null>(null)

  const convertMessage = useCallback(
    (msg: Message, idx: number): ThreadMessageLike => {
      const prev = idx > 0 ? messages[idx - 1] : null
      const next = idx < messages.length - 1 ? messages[idx + 1] : null
      const useAgentAvatar = chatConfig.config.use_agent_avatar === true
      const showAvatar = msg.sender_type === 'agent' || msg.sender_type === 'bot'
        ? useAgentAvatar
        : shouldShowAvatar(msg, next)

      const meta: VisitorMessageMeta = {
        senderName: msg.sender_name,
        senderAvatar: msg.sender_avatar,
        senderType: msg.sender_type,
        senderId: msg.sender_id,
        contentType: msg.content_type,
        conversationPublicId: msg.conversation_public_id || conversationPublicId || '',
        metadata: msg.metadata,
        eventType: getMetadataString(msg, 'event_type') || undefined,
        handoffPayload: msg.metadata?.handoff_payload,
        messageStatus: msg.status,
        streaming: msg.metadata?.streaming === true,
        openAgentThinkingBlocks: getOpenAgentThinkingBlocks(msg.metadata),
        openAgentToolBlocks: getOpenAgentToolBlocks(msg.metadata),
        openAgentTextBlocks: getOpenAgentTextBlocks(msg.metadata),
        showTimestamp: shouldShowTimestamp(msg, prev),
        showName: shouldShowName(msg, prev),
        showAvatar,
      }

      const role = mapRole(msg.sender_type)
      const content = msg.sender_type === 'bot'
        ? buildOpenAgentAssistantContent(msg)
        : [{ type: 'text' as const, text: msg.content }]

      const converted: ThreadMessageLike = {
        role,
        content,
        id: String(msg.id),
        createdAt: new Date(msg.created_at),
        metadata: { custom: meta },
      }

      if (role === 'assistant') {
        return {
          ...converted,
          role,
          status: msg.metadata?.streaming === true
            ? { type: 'running' }
            : { type: 'complete', reason: 'stop' },
        }
      }

      return converted
    },
    [messages, chatConfig.config.use_agent_avatar, conversationPublicId],
  )

  const addOptimistic = useVisitorChatStore((s) => s.addOptimisticMessage)
  const markOptimisticDelivered = useVisitorChatStore((s) => s.markOptimisticDelivered)
  const confirmOptimistic = useVisitorChatStore((s) => s.confirmOptimisticMessage)
  const addBotStreamingMessage = useVisitorChatStore((s) => s.addBotStreamingMessage)
  const appendMessageContent = useVisitorChatStore((s) => s.appendMessageContent)
  const setMessageContent = useVisitorChatStore((s) => s.setMessageContent)
  const updateMessageMetadata = useVisitorChatStore((s) => s.updateMessageMetadata)
  const removeMessage = useVisitorChatStore((s) => s.removeMessage)
  const replaceMessage = useVisitorChatStore((s) => s.replaceMessage)
  const addMessage = useVisitorChatStore((s) => s.addMessage)
  const addSystemNotice = useVisitorChatStore((s) => s.addSystemNotice)
  const setPendingHumanHandoff = useVisitorChatStore((s) => s.setPendingHumanHandoff)
  const markHandoffConfirming = useVisitorChatStore((s) => s.markHandoffConfirming)
  const setHandoffRouting = useVisitorChatStore((s) => s.setHandoffRouting)
  const resetHandoffUiState = useVisitorChatStore((s) => s.resetHandoffUiState)
  const clearHandoffConfirming = useVisitorChatStore((s) => s.clearHandoffConfirming)
  const handleHandoffRouteFailed = useVisitorChatStore((s) => s.handleHandoffRouteFailed)
  const handoffRouting = useVisitorChatStore((s) => s.handoffRouting)
  const visitorExternalId = useVisitorChatStore((s) => s.visitorId)

  const requestHumanHandoff = useCallback(
    async (payload?: HumanHandoffEventPayload | null) => {
      if (!socket || !conversationPublicId) return false
      const toolCallId = typeof payload?.tool_call_id === 'string' ? payload.tool_call_id : undefined
      if (payload && toolCallId) {
        markHandoffConfirming(toolCallId)
      } else if (payload) {
        setHandoffRouting(true)
      }
      return await new Promise<boolean>((resolve) => {
        socket.emit(
          'request_human_handoff',
          {
            conversation_public_id: conversationPublicId,
            ...(payload ? { handoff_payload: payload } : {}),
            handoff_trigger: payload ? 'bot_confirmed' : 'visitor',
            ...(toolCallId ? { tool_call_id: toolCallId } : {}),
          },
          (res: {
            ok?: boolean
            status?: string
            message?: Message
            reason?: string
          }) => {
            if (res?.message) addMessage(res.message)
            if (res?.status) {
              onConversationStatusChange(res.status)
              if (res.status === 'active') {
                resetHandoffUiState()
              }
            }
            if (res?.ok) {
              if (!payload) {
                resetHandoffUiState()
              }
              resolve(true)
              return
            }
            if (toolCallId) {
              clearHandoffConfirming(toolCallId)
            }
            if (payload) {
              handleHandoffRouteFailed(
                res?.reason,
                payload,
                payload.handoff?.brief?.trim() || '',
                useVisitorChatStore.getState().pendingHumanHandoff?.messageId,
              )
            } else {
              setHandoffRouting(false)
            }
            resolve(false)
          },
        )
      })
    },
    [
      addMessage,
      clearHandoffConfirming,
      conversationPublicId,
      handleHandoffRouteFailed,
      markHandoffConfirming,
      onConversationStatusChange,
      resetHandoffUiState,
      setHandoffRouting,
      setPendingHumanHandoff,
      socket,
    ],
  )

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

  const runOpenAgentTurn = useCallback(
    async ({
      text,
      requestId = generateRequestId(),
      clientMessageId = generateClientMessageId(),
      lastEventId = null,
      resume = false,
      addVisitorOptimistic = false,
    }: RunOpenAgentTurnOptions) => {
      if (!conversationPublicId || abortRef.current) return

      if (addVisitorOptimistic) {
        const tempId = addOptimistic(conversationPublicId, text, 'text')
        markOptimisticDelivered(tempId)
      }

      let pendingTurn = storePendingOpenAgentTurn({
        schemaVersion: OPEN_AGENT_PENDING_TURN_VERSION,
        conversationPublicId,
        message: text,
        requestId,
        clientMessageId,
        lastEventId,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      })
      pendingTurnRef.current = pendingTurn

      setBotRunning(true)
      let assistantTempId: number | null = addBotStreamingMessage(
        conversationPublicId,
        chatConfig.config.open_agent_agent_name || '智能助手',
      )
      let assistantHasContent = false
      let assistantHasTextContent = false
      let assistantAccumulatedText = ''
      let openAgentTimelineIndex = 0
      let lastLlmStepId: number | null = null
      let streamErrorShown = false
      let controller: OpenAgentStreamController | null = null
      const pendingToolCalls = new Map<string, OpenAgentToolCallPayload>()

      const clearPendingTurn = () => {
        if (pendingTurnRef.current?.clientMessageId !== clientMessageId) return
        clearPendingOpenAgentTurn(conversationPublicId)
        pendingTurnRef.current = null
      }

      const persistControllerSnapshot = () => {
        if (!controller || pendingTurnRef.current?.clientMessageId !== clientMessageId) return
        const snapshot = controller.getSnapshot()
        pendingTurn = storePendingOpenAgentTurn({
          ...pendingTurn,
          requestId: snapshot.requestId,
          clientMessageId: snapshot.clientMessageId,
          lastEventId: snapshot.lastEventId,
        })
        pendingTurnRef.current = pendingTurn
      }

      const clearAssistantPlaceholder = () => {
        if (assistantTempId === null || assistantHasContent) return
        removeMessage(assistantTempId)
        assistantTempId = null
      }

      const stripAssistantHandoffToolBlocks = () => {
        if (assistantTempId === null) return
        updateMessageMetadata(assistantTempId, (metadata) => ({
          ...metadata,
          open_agent_tool_blocks: stripHumanHandoffToolBlocks(getOpenAgentToolBlocks(metadata)),
        }))
      }

      const applyHumanHandoffFlow = (saved: Message, payload: HumanHandoffEventPayload, brief: string) => {
        stripAssistantHandoffToolBlocks()

        const handoffEventType = resolveHandoffEventType(saved)
        if (handoffEventType === 'auto_triggered' || handoffEventType === 'confirmed_by_visitor') {
          setPendingHumanHandoff(null)
          if (handoffEventType === 'auto_triggered') {
            useVisitorChatStore.getState().setHandoffRouting(true)
          }
          return
        }
        if (
          handoffEventType === 'confirm_requested'
          || (
            !handoffEventType
            && chatConfig.config.open_agent_handoff_behavior === 'confirm'
          )
        ) {
          setPendingHumanHandoff({
            payload,
            brief,
            messageId: saved.id,
            toolCallId: typeof saved.metadata?.tool_call_id === 'string'
              ? saved.metadata.tool_call_id
              : payload.tool_call_id,
          })
        }
      }

      const ensureAssistantMessage = () => {
        if (assistantTempId === null) {
          assistantTempId = addBotStreamingMessage(
            conversationPublicId,
            chatConfig.config.open_agent_agent_name || '智能助手',
          )
        }
        return assistantTempId
      }

      const updateAssistantToolBlocks = (
        updater: (blocks: OpenAgentToolBlock[]) => OpenAgentToolBlock[],
      ) => {
        const messageId = ensureAssistantMessage()
        assistantHasContent = true
        updateMessageMetadata(messageId, (metadata) => ({
          ...metadata,
          streaming: true,
          open_agent_text_blocks: finishTextBlocks(getOpenAgentTextBlocks(metadata)),
          open_agent_thinking_blocks: finishThinkingBlocks(
            getOpenAgentThinkingBlocks(metadata),
            lastLlmStepId,
          ),
          open_agent_tool_blocks: updater(getOpenAgentToolBlocks(metadata)),
        }))
      }

      const updateAssistantThinkingBlocks = (
        updater: (blocks: OpenAgentThinkingBlock[]) => OpenAgentThinkingBlock[],
      ) => {
        const messageId = ensureAssistantMessage()
        assistantHasContent = true
        updateMessageMetadata(messageId, (metadata) => ({
          ...metadata,
          streaming: true,
          open_agent_text_blocks: finishTextBlocks(getOpenAgentTextBlocks(metadata)),
          open_agent_thinking_blocks: updater(getOpenAgentThinkingBlocks(metadata)),
        }))
      }

      const updateAssistantTextBlocks = (
        updater: (blocks: OpenAgentTextBlock[]) => OpenAgentTextBlock[],
      ) => {
        const messageId = ensureAssistantMessage()
        assistantHasContent = true
        assistantHasTextContent = true
        updateMessageMetadata(messageId, (metadata) => ({
          ...metadata,
          streaming: true,
          open_agent_text_blocks: updater(getOpenAgentTextBlocks(metadata)),
          open_agent_thinking_blocks: finishThinkingBlocks(
            getOpenAgentThinkingBlocks(metadata),
            lastLlmStepId,
          ),
        }))
        return messageId
      }

      const finishAssistantThinkingBlocks = (messageId: number) => {
        updateMessageMetadata(messageId, (metadata) => ({
          ...metadata,
          open_agent_thinking_blocks: finishThinkingBlocks(
            getOpenAgentThinkingBlocks(metadata),
            lastLlmStepId,
          ),
        }))
      }

      const showBotError = (message?: string) => {
        if (streamErrorShown) return
        streamErrorShown = true
        clearPendingTurn()
        clearAssistantPlaceholder()
        addSystemNotice(
          conversationPublicId,
          message || (chatConfig.locale === 'zh'
            ? '智能助手暂时没有响应，请稍后重试或转人工'
            : 'The assistant is not responding. Please retry or contact support.'),
          { event_type: 'open_agent_stream_error' },
        )
      }

      controller = streamOpenAgentConversation({
        conversationPublicId,
        visitorSessionToken,
        message: text,
        requestId,
        clientMessageId,
        lastEventId,
        resume,
        handlers: {
          onLlmStepCreated: (data) => {
            persistControllerSnapshot()
            lastLlmStepId = getLlmStepId(data)
            if (assistantTempId !== null) {
              updateMessageMetadata(assistantTempId, (metadata) => ({
                ...metadata,
                open_agent_thinking_blocks: applyThinkingStepId(
                  getOpenAgentThinkingBlocks(metadata),
                  lastLlmStepId,
                ),
              }))
            }
          },
          onThinkingDelta: (data) => {
            persistControllerSnapshot()
            if (!getThinkingDeltaText(data)) return
            updateAssistantThinkingBlocks((blocks) => {
              const hasStreamingBlock = blocks[blocks.length - 1]?.isStreaming === true
              if (!hasStreamingBlock) openAgentTimelineIndex += 1
              return appendThinkingBlock(blocks, data, openAgentTimelineIndex, lastLlmStepId)
            })
          },
          onContentDelta: (delta) => {
            persistControllerSnapshot()
            if (!delta) return
            if (delta.trim().length > 0) {
              assistantHasContent = true
              assistantHasTextContent = true
            }
            assistantAccumulatedText += delta
            const messageId = updateAssistantTextBlocks((blocks) => {
              const hasStreamingBlock = blocks[blocks.length - 1]?.isStreaming === true
              if (!hasStreamingBlock) openAgentTimelineIndex += 1
              return appendTextBlock(blocks, delta, openAgentTimelineIndex)
            })
            finishAssistantThinkingBlocks(messageId)
            appendMessageContent(messageId, delta)
          },
          onToolCall: (data) => {
            persistControllerSnapshot()
            const toolCallId = getToolCallId(data, `tool_${openAgentTimelineIndex + 1}`)
            pendingToolCalls.set(toolCallId, data)
            if (isHumanHandoffToolName(resolveToolEventName(data))) return
            openAgentTimelineIndex += 1
            updateAssistantToolBlocks((blocks) => upsertToolCallBlock(blocks, data, openAgentTimelineIndex))
          },
          onToolResult: (data) => {
            persistControllerSnapshot()
            const toolCallId = getToolCallId(data, `tool_${openAgentTimelineIndex + 1}`)
            const pendingCall = pendingToolCalls.get(toolCallId)
            const toolName = resolveToolEventName(data)
              || (pendingCall ? resolveToolEventName(pendingCall) : '')
            if (isHumanHandoffToolName(toolName)) {
              stripAssistantHandoffToolBlocks()
              return
            }
            updateAssistantToolBlocks((blocks) => {
              const nextIndex = blocks.length > 0
                ? Math.max(...blocks.map((block) => block.timelineIndex)) + 1
                : openAgentTimelineIndex + 1
              openAgentTimelineIndex = Math.max(openAgentTimelineIndex, nextIndex)
              return applyToolResultBlock(blocks, data, nextIndex)
            })
          },
          onHumanHandoff: () => {
            // Handoff UI is driven by backend-persisted system messages via onMessageSaved.
            persistControllerSnapshot()
          },
          onHandoffUpdated: (data) => {
            persistControllerSnapshot()
            const payload = data.payload
            if (!isHumanHandoffEventPayload(payload)) return
            const brief = typeof data.brief === 'string' && data.brief.trim()
              ? data.brief.trim()
              : resolveHandoffBrief(payload, '', chatConfig.locale)
            const currentPending = useVisitorChatStore.getState().pendingHumanHandoff
            const messageId = currentPending?.messageId ?? getNumberValue(data.message_id)
            if (messageId != null) {
              setMessageContent(messageId, brief)
              updateMessageMetadata(messageId, (metadata) => ({
                ...metadata,
                handoff_payload: payload,
                ...(typeof payload.tool_call_id === 'string'
                  ? { tool_call_id: payload.tool_call_id }
                  : {}),
              }))
            }
            setPendingHumanHandoff({
              payload,
              brief,
              toolCallId: typeof payload.tool_call_id === 'string' ? payload.tool_call_id : undefined,
              messageId: messageId ?? undefined,
            })
          },
          onMessageSaved: (saved) => {
            persistControllerSnapshot()
            if (isOpenAgentHandoffMessage(saved)) {
              const payload = resolveHandoffPayloadFromMessage(saved)
              if (payload) {
                applyHumanHandoffFlow(
                  saved,
                  payload,
                  resolveHandoffBrief(payload, saved.content, chatConfig.locale),
                )
              } else {
                applyHumanHandoffFlow(
                  saved,
                  {
                    event_kind: 'human_handoff',
                    schema_version: 1,
                    handoff: { brief: saved.content },
                  },
                  saved.content,
                )
              }
              addMessage(saved)
              return
            }
            if (saved.sender_type === 'bot' && assistantTempId !== null) {
              replaceMessage(assistantTempId, saved)
              assistantTempId = null
              assistantHasContent = true
              assistantHasTextContent = saved.content.trim().length > 0
              assistantAccumulatedText = saved.content
              clearPendingTurn()
            } else {
              addMessage(saved)
            }
          },
          onConversationStatus: (data) => {
            const status = getStringValue(data.status)
            if (status) {
              onConversationStatusChange(status)
              if (status === 'active') resetHandoffUiState()
            }
          },
          onAssistantReset: () => {
            persistControllerSnapshot()
            pendingToolCalls.clear()
            if (assistantTempId !== null) {
              setMessageContent(assistantTempId, '')
              updateMessageMetadata(assistantTempId, (metadata) => ({
                ...metadata,
                streaming: true,
                open_agent_text_blocks: [],
                open_agent_thinking_blocks: [],
                open_agent_tool_blocks: [],
              }))
              assistantHasContent = false
              assistantHasTextContent = false
              assistantAccumulatedText = ''
              openAgentTimelineIndex = 0
              lastLlmStepId = null
            }
          },
          onDone: (data) => {
            persistControllerSnapshot()
            clearPendingTurn()
            const finalContent =
              getStringValue(data.final_content)
              || getStringValue(data.content)
              || getStringValue(data.text)
            if (finalContent) {
              let contentToAppend = ''
              if (!isTextAlreadyRepresented(assistantAccumulatedText, finalContent)) {
                contentToAppend = assistantAccumulatedText && finalContent.startsWith(assistantAccumulatedText)
                  ? finalContent.slice(assistantAccumulatedText.length)
                  : finalContent
              }
              if (contentToAppend) {
                const messageId = updateAssistantTextBlocks((blocks) => {
                  const existingText = textBlocksContent(blocks)
                  if (isTextAlreadyRepresented(existingText, finalContent)) return blocks
                  const nextContent = existingText && finalContent.startsWith(existingText)
                    ? finalContent.slice(existingText.length)
                    : finalContent
                  if (!nextContent) return blocks
                  const shouldStartNewBlock = Boolean(existingText) && !finalContent.startsWith(existingText)
                  const nextBlocks = shouldStartNewBlock ? finishTextBlocks(blocks) : blocks
                  const hasStreamingBlock = nextBlocks[nextBlocks.length - 1]?.isStreaming === true
                  if (!hasStreamingBlock) openAgentTimelineIndex += 1
                  return appendTextBlock(nextBlocks, nextContent, openAgentTimelineIndex)
                })
                appendMessageContent(
                  messageId,
                  assistantAccumulatedText && contentToAppend === finalContent
                    ? `\n\n${contentToAppend}`
                    : contentToAppend,
                )
                assistantAccumulatedText += contentToAppend
              }
              if (finalContent.trim().length > 0 || contentToAppend.trim().length > 0) {
                assistantHasContent = true
                assistantHasTextContent = true
              }
            }
            if (assistantTempId !== null && assistantHasContent) {
              updateMessageMetadata(assistantTempId, (metadata) => ({
                ...metadata,
                streaming: false,
                open_agent_text_blocks: finishTextBlocks(getOpenAgentTextBlocks(metadata)),
                open_agent_thinking_blocks: finishThinkingBlocks(
                  getOpenAgentThinkingBlocks(metadata),
                  lastLlmStepId,
                ),
                open_agent_tool_blocks: finishToolBlocks(
                  stripHumanHandoffToolBlocks(getOpenAgentToolBlocks(metadata)),
                ),
              }))
            }
            clearAssistantPlaceholder()
          },
          onRetry: () => {
            persistControllerSnapshot()
          },
          onError: () => {
            showBotError()
          },
        },
      })
      abortRef.current = controller
      persistControllerSnapshot()

      try {
        await controller.completion
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          showBotError()
        }
      } finally {
        const detachedForResume = detachedRequestIdsRef.current.has(controller.requestId)
        if (detachedForResume) {
          detachedRequestIdsRef.current.delete(controller.requestId)
        } else {
          clearPendingTurn()
        }
        clearAssistantPlaceholder()
        if (abortRef.current === controller) {
          abortRef.current = null
        }
        setBotRunning(false)
      }
    },
    [
      conversationPublicId,
      chatConfig.config.open_agent_agent_name,
      chatConfig.config.open_agent_handoff_behavior,
      chatConfig.locale,
      visitorSessionToken,
      addOptimistic,
      markOptimisticDelivered,
      addBotStreamingMessage,
      appendMessageContent,
      setMessageContent,
      updateMessageMetadata,
      removeMessage,
      replaceMessage,
      addMessage,
      addSystemNotice,
      requestHumanHandoff,
      resetHandoffUiState,
      setPendingHumanHandoff,
    ],
  )

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const textPart = message.content.find((p) => p.type === 'text')
      if (!textPart || textPart.type !== 'text') return
      if (!conversationPublicId) return

      if (chatConfig.botMode) {
        if (botRunning) return
        await runOpenAgentTurn({
          text: textPart.text,
          addVisitorOptimistic: true,
        })
        return
      }

      if (!socket) return

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
    [
      socket,
      conversationPublicId,
      chatConfig.botMode,
      botRunning,
      runOpenAgentTurn,
      addOptimistic,
      confirmOptimistic,
    ],
  )

  const persistCurrentTurnForResume = useCallback((detach = false) => {
    const controller = abortRef.current
    const pending = pendingTurnRef.current
    if (!controller || !pending) return

    const snapshot = controller.getSnapshot()
    pendingTurnRef.current = storePendingOpenAgentTurn({
      ...pending,
      requestId: snapshot.requestId,
      clientMessageId: snapshot.clientMessageId,
      lastEventId: snapshot.lastEventId,
    })

    if (detach) {
      detachedRequestIdsRef.current.add(controller.requestId)
      controller.detach()
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [])

  useEffect(() => {
    resumedClientMessageIdRef.current = null
    pendingTurnRef.current = null
  }, [conversationPublicId])

  useEffect(() => {
    if (typeof window === 'undefined') return

    const handleBeforeUnload = () => {
      persistCurrentTurnForResume(false)
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      persistCurrentTurnForResume(true)
    }
  }, [persistCurrentTurnForResume])

  useEffect(() => {
    if (
      !conversationPublicId
      || !chatConfig.botMode
      || chatConfig.initializing
      || botRunning
      || abortRef.current
    ) {
      return
    }

    const pending = readPendingOpenAgentTurn(conversationPublicId)
    if (!pending) return

    if (!pending.message.trim() || isPendingTurnAlreadyTerminal(messages, pending)) {
      clearPendingOpenAgentTurn(conversationPublicId)
      return
    }

    if (resumedClientMessageIdRef.current === pending.clientMessageId) return
    resumedClientMessageIdRef.current = pending.clientMessageId
    pendingTurnRef.current = pending

    void runOpenAgentTurn({
      text: pending.message,
      requestId: pending.requestId,
      clientMessageId: pending.clientMessageId,
      lastEventId: pending.lastEventId,
      resume: true,
      addVisitorOptimistic: false,
    })
  }, [
    conversationPublicId,
    chatConfig.botMode,
    chatConfig.initializing,
    botRunning,
    messages,
    runOpenAgentTurn,
  ])

  const runtime = useExternalStoreRuntime({
    isRunning: botRunning,
    messages,
    convertMessage,
    onNew,
    onCancel: async () => {
      if (conversationPublicId) clearPendingOpenAgentTurn(conversationPublicId)
      pendingTurnRef.current = null
      abortRef.current?.abort()
      setBotRunning(false)
    },
  })

  return (
    <VisitorChatConfigCtx.Provider
      value={{
        ...chatConfig,
        botRunning,
        handoffRouting,
        onFileSend,
        onRequestHumanHandoff: requestHumanHandoff,
        onDismissHumanHandoff: () => {
          useVisitorChatStore.getState().dismissPendingHumanHandoff()
          onConversationStatusChange('bot')
        },
      }}
    >
      <AssistantRuntimeProvider runtime={runtime}>
        {children}
      </AssistantRuntimeProvider>
    </VisitorChatConfigCtx.Provider>
  )
}
