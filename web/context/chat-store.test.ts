import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  const values = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    },
  })
})

import { useChatStore } from '@/context/chat-store'
import type { Conversation, Message } from '@/models/conversation'

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: 1,
    conversation_id: 10,
    conversation_public_id: 'cv_10',
    sender_type: 'agent',
    sender_id: 2,
    sender_name: 'Agent',
    sender_avatar: null,
    content_type: 'text',
    content: 'hello',
    created_at: '2026-07-11T00:00:00Z',
    ...overrides,
  }
}

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 10,
    public_id: 'cv_10',
    share_code: 'share-10',
    tenant_id: 1,
    visitor: null,
    agent: null,
    channel: null,
    group: null,
    status: 'active',
    started_at: null,
    ended_at: null,
    ended_by: null,
    last_message_at: null,
    last_message_preview: null,
    visitor_system: null,
    visitor_browser: null,
    visitor_ip: null,
    unread_count: 0,
    created_at: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  useChatStore.setState({
    conversations: [],
    selectedConversationId: null,
    conversationScope: 'my',
    myConversationView: 'current',
    workspaceChatTab: 'messages',
    messages: new Map(),
    visitorTyping: new Map(),
    visitorTypingContent: new Map(),
    recentReadAt: new Map(),
  })
})

describe('workspace message delivery state', () => {
  it('advances only the selected agent messages to unread', () => {
    useChatStore.getState().setMessages(10, [
      message({ id: 1, status: 'sending' }),
      message({ id: 2, status: 'offline' }),
      message({ id: 3, sender_type: 'visitor', status: 'unread' }),
    ])

    useChatStore.getState().markAgentMessagesDeliveredToVisitor(10, [2, 3])

    expect(useChatStore.getState().messages.get(10)?.map((item) => item.status)).toEqual([
      'sending',
      'unread',
      'unread',
    ])
  })

  it('never regresses a read message when a delivery event arrives late', () => {
    useChatStore.getState().setMessages(10, [message({ id: 1, status: 'read' })])

    useChatStore.getState().markAgentMessagesDeliveredToVisitor(10, [1])
    useChatStore.getState().markAgentMessagesDeliveredToVisitor(10, [1])

    expect(useChatStore.getState().messages.get(10)?.[0].status).toBe('read')
  })

  it('makes duplicate and out-of-order read events idempotent', () => {
    useChatStore.getState().setMessages(10, [
      message({ id: 1, status: 'sending' }),
      message({ id: 2, status: 'offline' }),
    ])

    useChatStore.getState().markAgentMessagesReadByVisitor(10, [1])
    useChatStore.getState().markAgentMessagesDeliveredToVisitor(10, [1])
    useChatStore.getState().markAgentMessagesReadByVisitor(10, [1])

    expect(useChatStore.getState().messages.get(10)?.map((item) => item.status)).toEqual([
      'read',
      'offline',
    ])
  })

  it('keeps delivery and read updates isolated by conversation', () => {
    useChatStore.getState().setMessages(10, [message({ id: 1, status: 'sending' })])
    useChatStore.getState().setMessages(20, [
      message({ id: 1, conversation_id: 20, conversation_public_id: 'cv_20', status: 'offline' }),
    ])

    useChatStore.getState().markAgentMessagesDeliveredToVisitor(10, [1])
    useChatStore.getState().markAgentMessagesReadByVisitor(10, [1])

    expect(useChatStore.getState().messages.get(10)?.[0].status).toBe('read')
    expect(useChatStore.getState().messages.get(20)?.[0].status).toBe('offline')
  })

  it('ignores an empty delivery batch without replacing store state', () => {
    useChatStore.getState().setMessages(10, [message({ status: 'sending' })])
    const previousMessages = useChatStore.getState().messages

    useChatStore.getState().markAgentMessagesDeliveredToVisitor(10, [])

    expect(useChatStore.getState().messages).toBe(previousMessages)
  })
})

describe('workspace message reconciliation', () => {
  it('deduplicates realtime messages by server id', () => {
    useChatStore.getState().setMessages(10, [message({ id: 1 })])

    useChatStore.getState().addMessage(10, message({ id: 1, content: 'duplicate' }))

    expect(useChatStore.getState().messages.get(10)).toHaveLength(1)
    expect(useChatStore.getState().messages.get(10)?.[0].content).toBe('hello')
  })

  it('replaces an optimistic message by client message id', () => {
    useChatStore.getState().setMessages(10, [
      message({
        id: -1,
        status: 'sending',
        metadata: { client_message_id: 'client-1' },
      }),
    ])

    useChatStore.getState().addMessage(10, message({
      id: 101,
      status: 'sending',
      metadata: { client_message_id: 'client-1' },
    }))

    expect(useChatStore.getState().messages.get(10)?.map((item) => item.id)).toEqual([101])
  })

  it('applies a recall update without regressing read status', () => {
    useChatStore.getState().setMessages(10, [message({ id: 1, status: 'read' })])

    useChatStore.getState().updateMessage(10, message({
      id: 1,
      status: 'unread',
      is_recalled: true,
      content: '',
    }))

    expect(useChatStore.getState().messages.get(10)?.[0]).toMatchObject({
      is_recalled: true,
      content: '',
      status: 'read',
    })
  })

  it('adds a quoted reply without changing the original message status', () => {
    useChatStore.getState().setMessages(10, [message({ id: 1, status: 'read' })])

    useChatStore.getState().addMessage(10, message({
      id: 2,
      content: 'quoted reply',
      status: 'sending',
      metadata: {
        quote: {
          schema_version: 1,
          message_id: 1,
          sender_type: 'agent',
          sender_id: 2,
          sender_name: 'Agent',
          content_type: 'text',
          summary: 'hello',
        },
      },
    }))

    expect(useChatStore.getState().messages.get(10)?.[0].status).toBe('read')
    expect(useChatStore.getState().messages.get(10)?.[1].metadata?.quote?.message_id).toBe(1)
  })

  it('does not let a stale list response restore a recently cleared unread count', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_000)
    useChatStore.setState({ conversations: [conversation({ unread_count: 3 })] })

    useChatStore.getState().markConversationRead(10)
    useChatStore.getState().setConversations([conversation({ unread_count: 3 })])

    expect(useChatStore.getState().conversations[0].unread_count).toBe(0)
  })

  it('keeps unread counts isolated when one conversation is marked read', () => {
    useChatStore.setState({
      conversations: [
        conversation({ id: 10, unread_count: 2 }),
        conversation({ id: 20, public_id: 'cv_20', unread_count: 4 }),
      ],
    })

    useChatStore.getState().markConversationRead(10)

    expect(useChatStore.getState().conversations.map((item) => item.unread_count)).toEqual([0, 4])
  })
})
