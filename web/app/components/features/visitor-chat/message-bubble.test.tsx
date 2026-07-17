import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { ChannelConfig } from '@/models/channel'
import type { Message } from '@/models/conversation'

const visitorChatConfig = vi.hoisted(() => ({
  channel: {
    open_agent_ai_disclaimer: { enabled: false, content: '' },
    read_status: { web_sdk_enabled: true },
  },
  ended: false,
  offlineMode: false,
  visitorSessionToken: 'visitor-session-token',
  onRecallMessage: vi.fn(),
  onQuoteMessage: vi.fn(),
  onSubmitOpenAgentFeedback: vi.fn(),
}))

vi.mock('@/components/assistant-ui/visitor-chat-runtime', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/assistant-ui/visitor-chat-runtime')>()
  return {
    ...actual,
    useVisitorChatConfig: () => visitorChatConfig,
  }
})

vi.mock('@/app/components/features/chat/message-attachment', async () => {
  const { createElement } = await import('react')
  return {
    MessageAttachment: ({ inlinePlayableVideo }: { inlinePlayableVideo?: boolean }) => createElement(
      'div',
      {
        'data-testid': 'message-attachment',
        'data-inline-playable-video': String(Boolean(inlinePlayableVideo)),
      },
    ),
  }
})

import { MessageBubble, resolveVisitorVisibleMessageStatus } from './message-bubble'

describe('visitor file messages', () => {
  it('enables inline video playback on the shared attachment renderer', () => {
    const message: Message = {
      id: 1,
      conversation_id: 2,
      conversation_public_id: 'conversation-public-id',
      sender_type: 'agent',
      sender_id: 3,
      sender_name: 'Agent',
      sender_avatar: null,
      content_type: 'file',
      content: JSON.stringify({
        schema_version: 1,
        file_id: 'video-file-id',
        name: 'clip.mp4',
        size: 1024,
        mime_type: 'video/mp4',
      }),
      created_at: '2026-07-15T12:00:00Z',
    }

    const html = renderToStaticMarkup(
      <MessageBubble
        message={message}
        config={{} as ChannelConfig}
        showAvatar={false}
        showName={false}
        showTime={false}
        locale="zh"
      />,
    )

    expect(html).toContain('data-inline-playable-video="true"')
  })
})

describe('visitor leave-message status', () => {
  it.each(['offline', 'delivered', 'unread', 'read'])(
    'hides persisted %s status for an offline message',
    (status) => {
      expect(resolveVisitorVisibleMessageStatus(status, {
        readStatusEnabled: true,
        offlineMessagePublicId: 'offline-public-id',
      })).toBeNull()
    },
  )

  it('keeps the temporary sending state visible', () => {
    expect(resolveVisitorVisibleMessageStatus('sending', {
      readStatusEnabled: false,
    })).toBe('sending')
  })

  it('keeps regular Web SDK conversation read states unchanged', () => {
    expect(resolveVisitorVisibleMessageStatus('delivered', {
      readStatusEnabled: true,
    })).toBe('unread')
    expect(resolveVisitorVisibleMessageStatus('offline', {
      readStatusEnabled: false,
    })).toBe('offline')
  })
})

describe('visitor bot message status', () => {
  it.each(['sending', 'delivered', 'unread', 'read'])('hides %s for OpenAgent messages', (status) => {
    expect(resolveVisitorVisibleMessageStatus(status, {
      readStatusEnabled: true,
      openAgent: true,
    })).toBeNull()
  })
})
