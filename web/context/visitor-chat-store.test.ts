import { beforeEach, describe, expect, it } from 'vitest'
import type { Message } from '@/models/conversation'
import {
  findOptimisticVisitorIndex,
  useVisitorChatStore,
} from '@/context/visitor-chat-store'

function message(overrides: Partial<Message>): Message {
  return {
    id: 1,
    conversation_id: 10,
    conversation_public_id: 'cv_1',
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

beforeEach(() => {
  useVisitorChatStore.setState({
    conversationPublicId: null,
    messages: [],
    hasMore: false,
  })
})

describe('visitor chat message reconciliation', () => {
  it('preserves realtime and optimistic messages while replacing the previous timeline', () => {
    useVisitorChatStore.setState({
      messages: [
        message({ id: 7, conversation_public_id: 'om_1', content: 'offline copy' }),
        message({ id: 11, content: 'realtime reply', created_at: '2026-07-11T00:00:02Z' }),
        message({
          id: -1,
          sender_type: 'visitor',
          sender_id: null,
          sender_name: null,
          content: 'optimistic',
          status: 'sending',
          created_at: '2026-07-11T00:00:03Z',
        }),
      ],
    })

    useVisitorChatStore.getState().reconcileConversationMessages('cv_1', [
      message({ id: 10, content: 'history', created_at: '2026-07-11T00:00:01Z' }),
    ])

    expect(useVisitorChatStore.getState().messages.map((item) => item.id)).toEqual([10, 11, -1])
  })

  it('deduplicates a realtime message already present in restored history', () => {
    useVisitorChatStore.setState({
      messages: [message({ id: 11, content: 'realtime copy' })],
    })

    useVisitorChatStore.getState().reconcileConversationMessages('cv_1', [
      message({ id: 10, content: 'history' }),
      message({ id: 11, content: 'history copy' }),
    ])

    expect(useVisitorChatStore.getState().messages.map((item) => item.id)).toEqual([10, 11])
    expect(useVisitorChatStore.getState().messages[1].content).toBe('history copy')
  })

  it('keeps messages from another conversation out of the active timeline', () => {
    useVisitorChatStore.setState({
      messages: [
        message({ id: 20, conversation_public_id: 'cv_2' }),
        message({ id: 11, conversation_public_id: 'cv_1' }),
      ],
    })

    useVisitorChatStore.getState().reconcileConversationMessages('cv_1', [
      message({ id: 10, conversation_public_id: 'cv_1' }),
    ])

    expect(useVisitorChatStore.getState().messages.map((item) => item.id)).toEqual([10, 11])
  })

  it('preserves read when a stale server update arrives later', () => {
    useVisitorChatStore.setState({
      messages: [message({ id: 11, sender_type: 'visitor', status: 'read' })],
    })

    useVisitorChatStore.getState().reconcileConversationMessages('cv_1', [
      message({ id: 11, sender_type: 'visitor', status: 'unread' }),
    ])

    expect(useVisitorChatStore.getState().messages[0].status).toBe('read')
  })

  it('applies a recall update without regressing a read visitor message', () => {
    useVisitorChatStore.setState({
      messages: [message({
        id: 11,
        sender_type: 'visitor',
        status: 'read',
        content: 'typo',
      })],
    })

    useVisitorChatStore.getState().reconcileConversationMessages('cv_1', [
      message({
        id: 11,
        sender_type: 'visitor',
        status: 'unread',
        content: '',
        is_recalled: true,
      }),
    ])

    expect(useVisitorChatStore.getState().messages[0]).toMatchObject({
      is_recalled: true,
      content: '',
      status: 'read',
    })
  })

  it('marks only visitor messages in the selected conversation read', () => {
    useVisitorChatStore.setState({
      messages: [
        message({ id: 1, sender_type: 'visitor', status: 'unread' }),
        message({ id: 2, sender_type: 'agent', status: 'unread' }),
        message({ id: 3, conversation_public_id: 'cv_2', sender_type: 'visitor', status: 'unread' }),
      ],
    })

    useVisitorChatStore.getState().markVisitorMessagesRead('cv_1')

    expect(useVisitorChatStore.getState().messages.map((item) => item.status)).toEqual([
      'read',
      'unread',
      'unread',
    ])
  })

  it('replaces an optimistic message with exactly one confirmed server message', () => {
    const tempId = useVisitorChatStore.getState().addOptimisticMessage(
      'cv_1',
      'retry me',
      'text',
      { client_message_id: 'client-1' },
    )
    const confirmed = message({
      id: 101,
      sender_type: 'visitor',
      content: 'retry me',
      status: 'unread',
      metadata: { client_message_id: 'client-1' },
    })

    useVisitorChatStore.getState().confirmOptimisticMessage(tempId, confirmed)
    useVisitorChatStore.getState().confirmOptimisticMessage(tempId, confirmed)

    expect(useVisitorChatStore.getState().messages).toEqual([confirmed])
  })

  it('matches an optimistic image by file_id when the JSON string was normalized', () => {
    const optimistic = message({
      id: -3,
      sender_type: 'visitor',
      sender_id: null,
      content_type: 'image',
      content: '{"file_id":"file-1","name":"IMG_0001.jpg","size":1200,"mime_type":"image/jpeg"}',
    })
    const confirmed = message({
      id: 88,
      sender_type: 'visitor',
      sender_id: null,
      content_type: 'image',
      content: '{"schema_version":1,"file_id":"file-1","name":"IMG_0001.jpg","size":1200,"mime_type":"image/jpeg"}',
    })

    expect(findOptimisticVisitorIndex([optimistic], confirmed)).toBe(0)
  })

  it('drops the optimistic photo when the room echo already confirmed it', () => {
    const tempId = useVisitorChatStore.getState().addOptimisticMessage(
      'cv_1',
      '{"file_id":"file-1","name":"IMG_0001.jpg","size":1200,"mime_type":"image/jpeg"}',
      'image',
    )
    const confirmed = message({
      id: 88,
      sender_type: 'visitor',
      sender_id: null,
      content_type: 'image',
      content: '{"schema_version":1,"file_id":"file-1","name":"IMG_0001.jpg","size":1200,"mime_type":"image/jpeg"}',
    })

    useVisitorChatStore.setState({
      messages: [...useVisitorChatStore.getState().messages, confirmed],
    })
    useVisitorChatStore.getState().confirmOptimisticMessage(tempId, confirmed)

    expect(useVisitorChatStore.getState().messages).toEqual([confirmed])
  })
})

describe('visitor chat prependMessages', () => {
  it('does not keep overlapping history ids that crash assistant-ui', () => {
    useVisitorChatStore.setState({
      messages: [message({ id: 11, content: 'on screen' }), message({ id: 12 })],
    })

    useVisitorChatStore.getState().prependMessages([
      message({ id: 10, content: 'older' }),
      message({ id: 11, content: 'overlap' }),
    ])

    expect(useVisitorChatStore.getState().messages.map((item) => [item.id, item.content])).toEqual([
      [10, 'older'],
      [11, 'on screen'],
      [12, 'hello'],
    ])
  })
})
