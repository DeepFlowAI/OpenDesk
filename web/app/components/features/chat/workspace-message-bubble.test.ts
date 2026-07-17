import { describe, expect, it, vi } from 'vitest'
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'

import type { Message } from '@/models/conversation'
import type { SessionRecordMessage } from '@/models/session-record'

import { WorkspaceMessageBubble, sessionRecordMessageToMessage } from './workspace-message-bubble'

function makeRecord(overrides: Partial<SessionRecordMessage> = {}): SessionRecordMessage {
  return {
    id: 1,
    conversation_id: 100,
    sender_type: 'agent',
    sender_id: 7,
    sender_name: 'Alice',
    sender_avatar: 'https://example.com/a.png',
    content_type: 'text',
    content: 'hello',
    is_recalled: false,
    recalled_at: null,
    recalled_by_type: null,
    recalled_by_id: null,
    recalled_by_name: null,
    metadata: { foo: 'bar' },
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('sessionRecordMessageToMessage', () => {
  it('maps the shared fields verbatim', () => {
    const msg = sessionRecordMessageToMessage(makeRecord())

    expect(msg).toMatchObject({
      id: 1,
      conversation_id: 100,
      sender_type: 'agent',
      sender_id: 7,
      sender_name: 'Alice',
      sender_avatar: 'https://example.com/a.png',
      content_type: 'text',
      content: 'hello',
      created_at: '2026-01-01T00:00:00Z',
      metadata: { foo: 'bar' },
    })
  })

  // Regression guard: these fields were at risk of being dropped during the
  // shared-component refactor. The record and active-chat views must agree.
  it('preserves satisfaction and config-version fields', () => {
    const msg = sessionRecordMessageToMessage(
      makeRecord({
        content_type: 'satisfaction_event',
        satisfaction_record_id: 555,
        config_version: 3,
      }),
    )

    expect(msg.satisfaction_record_id).toBe(555)
    expect(msg.config_version).toBe(3)
  })

  it('preserves recall metadata', () => {
    const msg = sessionRecordMessageToMessage(
      makeRecord({
        is_recalled: true,
        recalled_at: '2026-01-02T00:00:00Z',
        recalled_by_type: 'agent',
        recalled_by_id: 9,
        recalled_by_name: 'Bob',
      }),
    )

    expect(msg.is_recalled).toBe(true)
    expect(msg.recalled_at).toBe('2026-01-02T00:00:00Z')
    expect(msg.recalled_by_type).toBe('agent')
    expect(msg.recalled_by_id).toBe(9)
    expect(msg.recalled_by_name).toBe('Bob')
  })

  it('passes through event_type and leaves optional fields undefined when absent', () => {
    const msg = sessionRecordMessageToMessage(makeRecord({ event_type: 'system_event' }))

    expect(msg.event_type).toBe('system_event')
    expect(msg.satisfaction_record_id).toBeUndefined()
    expect(msg.config_version).toBeUndefined()
  })
})

describe('WorkspaceMessageBubble visitor avatar', () => {
  const visitorMessage: Message = {
    id: 2,
    conversation_id: 100,
    sender_type: 'visitor',
    sender_id: 8,
    sender_name: 'Visitor',
    sender_avatar: null,
    content_type: 'text',
    content: 'hello',
    created_at: '2026-01-01T00:00:00Z',
  }

  const baseProps = {
    message: visitorMessage,
    locale: 'zh' as const,
    mode: 'active' as const,
    attachmentContext: { kind: 'conversation' as const, conversationId: 100 },
  }

  it('shows the visitor avatar by default for shared views', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, baseProps))
    expect(html).toContain('data-testid="visitor-message-avatar"')
  })

  it('removes the visitor avatar when the active workspace disables it', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, {
      ...baseProps,
      showVisitorAvatar: false,
    }))
    expect(html).not.toContain('data-testid="visitor-message-avatar"')
  })
})

describe('WorkspaceMessageBubble message status', () => {
  const ownAgentMessage: Message = {
    id: 3,
    conversation_id: 100,
    sender_type: 'agent',
    sender_id: 7,
    sender_name: 'Alice',
    sender_avatar: null,
    content_type: 'text',
    content: 'hello',
    created_at: '2026-01-01T00:00:00Z',
    status: 'unread',
  }

  const baseProps = {
    message: ownAgentMessage,
    locale: 'zh' as const,
    mode: 'active' as const,
    attachmentContext: { kind: 'conversation' as const, conversationId: 100 },
    currentUserId: 7,
    readStatusEnabled: true,
  }

  it('places the own-message status trigger before the bubble content', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, baseProps))

    expect(html).toContain('aria-label="未读"')
    expect(html).toContain('data-workspace-message-id="3"')
    expect(html).toContain('data-sender-type="agent"')
    expect(html).toContain('data-message-status="unread"')
    expect(html.indexOf('aria-label="未读"')).toBeLessThan(html.indexOf('hello'))
    expect(html).toContain('flex min-w-0 max-w-full items-end gap-1')
    expect(html).toContain('rounded-[12px]')
  })

  it('places the timestamp before the agent name above the message', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, baseProps))
    const metaStart = html.indexOf('mb-1 flex max-w-full items-center gap-1')
    const contentStart = html.indexOf('hello')
    const metaHtml = html.slice(metaStart, contentStart)

    expect(metaStart).toBeGreaterThan(-1)
    expect(metaStart).toBeLessThan(contentStart)
    expect(metaHtml).toMatch(/<span[^>]*>[^<]+<\/span><span[^>]*>Alice<\/span>/)
  })

  it('removes the agent avatar when the active workspace disables it', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, {
      ...baseProps,
      message: { ...ownAgentMessage, sender_avatar: '/agent-avatar.png' },
      showAssistantAvatar: false,
    }))

    expect(html).not.toContain('/agent-avatar.png')
    expect(html).not.toContain('data-testid="visitor-message-avatar"')
  })

  it('hides read status without leaving a trigger when the setting is disabled', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, {
      ...baseProps,
      readStatusEnabled: false,
    }))

    expect(html).not.toContain('aria-label="未读"')
    expect(html).not.toContain('data-message-status=')
  })

  it('keeps the sending icon visible when the setting is disabled', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, {
      ...baseProps,
      message: { ...ownAgentMessage, status: 'sending' },
      readStatusEnabled: false,
    }))

    expect(html).toContain('aria-label="发送中"')
  })
})

describe('WorkspaceMessageBubble welcome message', () => {
  it('places the welcome timestamp above the bubble', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, {
      message: {
        id: 4,
        conversation_id: 100,
        sender_type: 'system',
        sender_id: null,
        sender_name: 'System',
        sender_avatar: null,
        content_type: 'welcome',
        content: 'Welcome to OpenDesk',
        created_at: '2026-01-01T00:00:00Z',
      },
      locale: 'zh',
      mode: 'active',
      attachmentContext: { kind: 'conversation', conversationId: 100 },
    }))

    const timestampIndex = html.indexOf('mb-1 text-right text-[11px]')
    const contentIndex = html.indexOf('Welcome to OpenDesk')
    expect(timestampIndex).toBeGreaterThan(-1)
    expect(timestampIndex).toBeLessThan(contentIndex)
    expect(html).not.toContain('mt-1 text-right text-[11px]')
  })

  it('removes the bot welcome avatar when the active workspace disables it', () => {
    const html = renderToStaticMarkup(createElement(WorkspaceMessageBubble, {
      message: {
        id: 5,
        conversation_id: 100,
        sender_type: 'bot',
        sender_id: 9,
        sender_name: 'Bot',
        sender_avatar: '/bot-avatar.png',
        content_type: 'bot_welcome',
        content: 'Welcome from bot',
        created_at: '2026-01-01T00:00:00Z',
      },
      locale: 'zh',
      mode: 'active',
      attachmentContext: { kind: 'conversation', conversationId: 100 },
      showAssistantAvatar: false,
    }))

    expect(html).not.toContain('/bot-avatar.png')
  })
})

describe('WorkspaceMessageBubble knowledge actions', () => {
  it('places robot QA after create document and invokes its callback', async () => {
    const message = sessionRecordMessageToMessage(makeRecord())
    const onAddKnowledgeInspiration = vi.fn()
    const onCreateKnowledgeDocument = vi.fn()
    const onCreateRobotQa = vi.fn()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(WorkspaceMessageBubble, {
        message,
        locale: 'zh',
        mode: 'active',
        attachmentContext: { kind: 'conversation', conversationId: 100 },
        onAddKnowledgeInspiration,
        onCreateKnowledgeDocument,
        onCreateRobotQa,
      }))
    })

    await act(async () => {
      container.firstElementChild?.dispatchEvent(new MouseEvent('contextmenu', {
        bubbles: true,
        clientX: 20,
        clientY: 20,
      }))
    })

    const actionLabels = Array.from(container.querySelectorAll('button')).map((button) => button.textContent?.trim())
    expect(actionLabels).toEqual(['添加知识灵感', '新建知识文档', '新建机器人 QA'])

    await act(async () => {
      container.querySelectorAll('button')[2]?.click()
    })
    expect(onCreateRobotQa).toHaveBeenCalledWith(expect.objectContaining({ id: message.id }))
    expect(onAddKnowledgeInspiration).not.toHaveBeenCalled()
    expect(onCreateKnowledgeDocument).not.toHaveBeenCalled()

    await act(async () => root.unmount())
    container.remove()
  })

  it('opens the same knowledge menu from an image message', async () => {
    const message = sessionRecordMessageToMessage(makeRecord({
      content_type: 'image',
      content: JSON.stringify({
        schema_version: 1,
        file_id: 'file_123',
        name: 'source.png',
        size: 12,
        mime_type: 'image/png',
      }),
    }))
    const onAddKnowledgeInspiration = vi.fn()
    const onCreateKnowledgeDocument = vi.fn()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(WorkspaceMessageBubble, {
        message,
        locale: 'zh',
        mode: 'active',
        attachmentContext: { kind: 'conversation', conversationId: 100 },
        onAddKnowledgeInspiration,
        onCreateKnowledgeDocument,
      }))
    })

    await act(async () => {
      container.firstElementChild?.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }))
    })

    expect(Array.from(container.querySelectorAll('button')).map((button) => button.textContent?.trim()))
      .toEqual(['添加知识灵感', '新建知识文档'])

    await act(async () => root.unmount())
    container.remove()
  })

  it('shows create document without inspiration for a file message', async () => {
    const message = sessionRecordMessageToMessage(makeRecord({
      content_type: 'file',
      content: JSON.stringify({
        schema_version: 1,
        file_id: 'file_123',
        name: 'guide.pdf',
        size: 12,
        mime_type: 'application/pdf',
      }),
    }))
    const onCreateKnowledgeDocument = vi.fn()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(WorkspaceMessageBubble, {
        message,
        locale: 'zh',
        mode: 'active',
        attachmentContext: { kind: 'conversation', conversationId: 100 },
        onCreateKnowledgeDocument,
      }))
    })

    await act(async () => {
      container.firstElementChild?.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true }))
    })

    const menuButtons = Array.from(container.querySelectorAll('button'))
      .filter((button) => button.textContent?.trim())
    expect(menuButtons.map((button) => button.textContent?.trim())).toEqual(['新建知识文档'])

    await act(async () => {
      menuButtons[0]?.click()
    })
    expect(onCreateKnowledgeDocument).toHaveBeenCalledWith(expect.objectContaining({ id: message.id }))

    await act(async () => root.unmount())
    container.remove()
  })
})
