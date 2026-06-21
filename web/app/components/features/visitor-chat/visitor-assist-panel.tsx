'use client'

import { useEffect, useMemo, useRef } from 'react'
import { useComposerRuntime } from '@assistant-ui/react'
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import { useVisitorChatConfig } from '@/components/assistant-ui/visitor-chat-runtime'
import {
  AssistPanelRuntime,
  createAssistPanelError,
  createAssistPanelOk,
  type AssistPanelApi,
  type AssistPanelEventName,
  type AssistPanelStatus,
} from './assist-panel-runtime'

const SUPPORTED_EVENTS: AssistPanelEventName[] = [
  'status_changed',
  'agent_changed',
  'conversation_changed',
  'message_created',
  'context_changed',
  'panel_visibility_changed',
]

function resolveStage(status: {
  initializing: boolean
  ended: boolean
  conversationPublicId: string | null
  conversationStatus: string | null
  botMode: boolean
  handoffRouting: boolean
}): AssistPanelStatus['stage'] {
  if (status.initializing) return 'initializing'
  if (status.ended) return 'ended'
  if (!status.conversationPublicId) return 'offline'
  if (status.handoffRouting || status.conversationStatus === 'handoff_pending') return 'handoff_pending'
  if (status.botMode || status.conversationStatus === 'bot') return 'bot'
  return 'human'
}

function isAllowedUrl(url: string): boolean {
  if (!url) return false
  if (url.startsWith('/')) return true
  try {
    return new URL(url).protocol === 'https:'
  } catch {
    return false
  }
}

function toPublicMessage(message: {
  id: number
  sender_type: string
  content_type: string
  content: string
  created_at: string
}) {
  return {
    id: message.id,
    sender_type: message.sender_type,
    content_type: message.content_type,
    content: message.content,
    created_at: message.created_at,
  }
}

function isSupportedEvent(value: string): value is AssistPanelEventName {
  return SUPPORTED_EVENTS.includes(value as AssistPanelEventName)
}

export function VisitorAssistPanel() {
  const {
    channel,
    config,
    locale,
    ended,
    conversationStatus,
    conversationPublicId,
    initializing,
    botMode,
    botRunning,
    handoffRouting,
    onAssistSendMessage,
    onRequestHumanHandoff,
  } = useVisitorChatConfig()
  const composer = useComposerRuntime()
  const connected = useVisitorChatStore((s) => s.connected)
  const connecting = useVisitorChatStore((s) => s.connecting)
  const activeAgent = useVisitorChatStore((s) => s.activeAgent)
  const visitorId = useVisitorChatStore((s) => s.visitorId)
  const messages = useVisitorChatStore((s) => s.messages)
  const statusListenersRef = useRef(new Set<(next: AssistPanelStatus) => void>())
  const eventListenersRef = useRef(new Map<AssistPanelEventName, Set<(payload: unknown) => void>>())

  const status = useMemo<AssistPanelStatus>(() => {
    const stage = resolveStage({
      initializing,
      ended,
      conversationPublicId,
      conversationStatus,
      botMode,
      handoffRouting,
    })
    const connectionStatus = connecting ? 'connecting' : connected ? 'connected' : 'disconnected'
    return {
      stage,
      conversationStatus,
      connectionStatus,
      botRunning,
      handoffRouting,
      canSendMessage: Boolean(
        conversationPublicId
        && !ended
        && connected
        && !initializing
        && !botRunning
        && !handoffRouting,
      ),
      canRequestHumanHandoff: Boolean(
        botMode
        && config.open_agent_handoff_enabled
        && conversationPublicId
        && !ended
        && connected
        && !botRunning
        && !handoffRouting,
      ),
      currentAgent: activeAgent,
    }
  }, [
    activeAgent,
    botMode,
    botRunning,
    config.open_agent_handoff_enabled,
    connected,
    connecting,
    conversationPublicId,
    conversationStatus,
    ended,
    handoffRouting,
    initializing,
  ])

  const statusRef = useRef(status)
  const conversationRef = useRef({
    public_id: conversationPublicId,
    status: conversationStatus,
    ended,
    canSendMessage: status.canSendMessage,
  })
  const agentRef = useRef(activeAgent)
  const messagesRef = useRef(messages)

  statusRef.current = status
  conversationRef.current = {
    public_id: conversationPublicId,
    status: conversationStatus,
    ended,
    canSendMessage: status.canSendMessage,
  }
  agentRef.current = activeAgent
  messagesRef.current = messages

  const emitEvent = (eventName: AssistPanelEventName, payload: unknown) => {
    eventListenersRef.current.get(eventName)?.forEach((listener) => {
      try {
        listener(payload)
      } catch {
        // Tenant code errors stay inside the assist panel runtime.
      }
    })
  }

  useEffect(() => {
    statusListenersRef.current.forEach((listener) => {
      try {
        listener(status)
      } catch {
        // Tenant code errors stay inside the assist panel runtime.
      }
    })
    emitEvent('status_changed', status)
  }, [status])

  useEffect(() => {
    emitEvent('agent_changed', activeAgent)
  }, [activeAgent])

  useEffect(() => {
    emitEvent('conversation_changed', conversationRef.current)
  }, [conversationPublicId, conversationStatus, ended, status.canSendMessage])

  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage) emitEvent('message_created', toPublicMessage(lastMessage))
  }, [messages])

  const api = useMemo<AssistPanelApi>(() => ({
    getChannel: () => ({
      channel_key: channel.channel_key,
      name: channel.name,
      logo_url: channel.logo_url,
      config: {
        assist_panel_enabled: config.assist_panel_enabled,
        assist_panel_title: config.assist_panel_title,
      },
    }),
    getConversation: () => conversationRef.current,
    getCurrentStatus: () => statusRef.current,
    subscribeStatus: (listener: (next: AssistPanelStatus) => void) => {
      statusListenersRef.current.add(listener)
      listener(statusRef.current)
      return () => {
        statusListenersRef.current.delete(listener)
      }
    },
    subscribeEvent: (eventName: AssistPanelEventName, listener: (payload: unknown) => void) => {
      if (!isSupportedEvent(eventName)) {
        listener(createAssistPanelError('UNSUPPORTED_EVENT', 'Unsupported assist panel event'))
        return () => undefined
      }
      const listeners = eventListenersRef.current.get(eventName) ?? new Set<(payload: unknown) => void>()
      listeners.add(listener)
      eventListenersRef.current.set(eventName, listeners)
      if (eventName === 'status_changed') listener(statusRef.current)
      if (eventName === 'agent_changed') listener(agentRef.current)
      if (eventName === 'conversation_changed') listener(conversationRef.current)
      if (eventName === 'message_created') {
        const lastMessage = messagesRef.current[messagesRef.current.length - 1]
        listener(lastMessage ? toPublicMessage(lastMessage) : null)
      }
      if (eventName === 'context_changed') listener(null)
      if (eventName === 'panel_visibility_changed') listener({ visible: true, collapsed: false })
      return () => {
        listeners.delete(listener)
      }
    },
    getCurrentAgent: () => agentRef.current,
    getVisitor: () => ({ external_id: visitorId }),
    getMessages: () => messagesRef.current.slice(-50).map(toPublicMessage),
    sendMessage: async (text: string) => {
      const next = typeof text === 'string' ? text.trim() : ''
      if (!next || next.length > 2000) {
        return createAssistPanelError('INVALID_PAYLOAD', 'Message text is invalid')
      }
      const current = statusRef.current
      if (!conversationRef.current.public_id) {
        return createAssistPanelError('CONVERSATION_NOT_READY', 'Conversation is not ready')
      }
      if (ended) {
        return createAssistPanelError('CONVERSATION_ENDED', 'Conversation has ended')
      }
      if (!current.canSendMessage) {
        return createAssistPanelError('MESSAGE_SEND_DISABLED', 'Message sending is disabled')
      }
      const ok = await onAssistSendMessage(next)
      return ok ? createAssistPanelOk() : createAssistPanelError('MESSAGE_SEND_DISABLED', 'Message sending failed')
    },
    setComposerText: (text: string) => {
      const next = typeof text === 'string' ? text.slice(0, 2000) : ''
      if (!next) return createAssistPanelError('INVALID_PAYLOAD', 'Composer text is invalid')
      composer.setText(next)
      return createAssistPanelOk()
    },
    requestHumanHandoff: async () => {
      const current = statusRef.current
      if (!current.canRequestHumanHandoff) {
        return createAssistPanelError('HUMAN_HANDOFF_DISABLED', 'Human handoff is disabled')
      }
      const ok = await onRequestHumanHandoff(null)
      return ok ? createAssistPanelOk() : createAssistPanelError('HUMAN_HANDOFF_DISABLED', 'Human handoff failed')
    },
    openUrl: (url: string) => {
      if (!isAllowedUrl(url)) return createAssistPanelError('INVALID_PAYLOAD', 'URL is invalid')
      window.open(url, '_blank', 'noopener,noreferrer')
      return createAssistPanelOk()
    },
  }), [
    channel.channel_key,
    channel.logo_url,
    channel.name,
    composer,
    config.assist_panel_enabled,
    config.assist_panel_title,
    ended,
    onAssistSendMessage,
    onRequestHumanHandoff,
    visitorId,
  ])

  return (
    <aside className="flex h-full min-h-0 w-[360px] shrink-0 flex-col overflow-hidden border-l border-border bg-card">
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <AssistPanelRuntime
          code={config.assist_panel_react_code ?? ''}
          api={api}
          status={status}
          config={config.assist_panel_config ?? {}}
          locale={locale}
        />
      </div>
    </aside>
  )
}
