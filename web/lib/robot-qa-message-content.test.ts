import { describe, expect, it } from 'vitest'

import type { Message } from '@/models/conversation'

import {
  canCreateRobotQaFromMessage,
  normalizeRobotQaKeyword,
  robotQaAnswerMarkdownFromMessage,
} from './robot-qa-message-content'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 1,
    conversation_id: 10,
    sender_type: 'visitor',
    sender_id: 20,
    sender_name: 'Visitor',
    sender_avatar: null,
    content_type: 'text',
    content: 'How can I reset my password?',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('robot QA message content', () => {
  it('accepts visible text and rich-text messages from supported senders', () => {
    expect(canCreateRobotQaFromMessage(makeMessage())).toBe(true)
    expect(canCreateRobotQaFromMessage(makeMessage({
      sender_type: 'bot',
      content_type: 'rich_text',
      content: '<p><strong>Reset</strong> the password</p>',
    }))).toBe(true)
  })

  it('rejects recalled, empty, and unsupported messages', () => {
    expect(canCreateRobotQaFromMessage(makeMessage({ is_recalled: true }))).toBe(false)
    expect(canCreateRobotQaFromMessage(makeMessage({ content: '   ' }))).toBe(false)
    expect(canCreateRobotQaFromMessage(makeMessage({ sender_type: 'system' }))).toBe(false)
    expect(canCreateRobotQaFromMessage(makeMessage({ content_type: 'image' }))).toBe(false)
  })

  it('converts rich text to Markdown', () => {
    expect(robotQaAnswerMarkdownFromMessage(makeMessage({
      content_type: 'rich_text',
      content: '<h2>Reset</h2><ul><li>Open settings</li><li>Choose password</li></ul>',
    }))).toBe('## Reset\n\n-   Open settings\n-   Choose password')
  })

  it('normalizes valid permission keywords and rejects invalid characters', () => {
    expect(normalizeRobotQaKeyword(' VIP_User ')).toBe('vip_user')
    expect(normalizeRobotQaKeyword('中文')).toBeNull()
    expect(normalizeRobotQaKeyword('vip-user')).toBeNull()
  })
})
