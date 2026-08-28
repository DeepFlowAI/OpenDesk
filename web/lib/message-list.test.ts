import { describe, expect, it } from 'vitest'

import type { Message } from '@/models/conversation'

import { dedupeMessagesById } from './message-list'

function message(overrides: Partial<Message> & Pick<Message, 'id'>): Message {
  return {
    conversation_id: 1,
    conversation_public_id: 'cv_1',
    sender_type: 'visitor',
    sender_id: null,
    sender_name: null,
    sender_avatar: null,
    content_type: 'text',
    content: 'hi',
    created_at: '2026-08-18T00:00:00Z',
    ...overrides,
  }
}

describe('dedupeMessagesById', () => {
  it('returns the same array when ids are unique', () => {
    const messages = [message({ id: 1 }), message({ id: 2 })]
    expect(dedupeMessagesById(messages)).toBe(messages)
  })

  it('keeps the later copy so assistant-ui never sees a duplicate id', () => {
    const first = message({ id: 11, content: 'history' })
    const later = message({ id: 11, content: 'realtime' })
    const next = message({ id: 12, content: 'follow-up' })

    expect(dedupeMessagesById([first, later, next]).map((item) => [item.id, item.content])).toEqual([
      [11, 'realtime'],
      [12, 'follow-up'],
    ])
  })
})
