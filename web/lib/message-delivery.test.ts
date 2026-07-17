import { describe, expect, it } from 'vitest'
import { buildMessageDeliveryBatches } from './message-delivery'
import type { Message } from '@/models/conversation'

function message(overrides: Partial<Message>): Message {
  return {
    id: 1,
    conversation_id: 10,
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

describe('buildMessageDeliveryBatches', () => {
  it('groups and deduplicates eligible agent messages by public conversation id', () => {
    expect(buildMessageDeliveryBatches([
      {
        conversationPublicId: 'cv_1',
        messages: [
          message({ id: 2 }),
          message({ id: 1 }),
          message({ id: 2 }),
          message({ id: 3, sender_type: 'visitor' }),
          message({ id: 4, content_type: 'system' }),
          message({ id: -1 }),
        ],
      },
      {
        conversationPublicId: 'cv_2',
        messages: [message({ id: 5, conversation_public_id: 'cv_2', content_type: 'file' })],
      },
    ])).toEqual([
      { conversationPublicId: 'cv_1', messageIds: [1, 2] },
      { conversationPublicId: 'cv_2', messageIds: [5] },
    ])
  })
})
