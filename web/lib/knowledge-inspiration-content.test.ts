import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getConversationFileUrl } from '@/service/use-conversation-files'
import { postForm } from '@/service/base'
import type { Message } from '@/models/conversation'
import { buildKnowledgeInspirationPayloadFromMessage } from './knowledge-inspiration-content'

vi.mock('@/service/use-conversation-files', () => ({
  getConversationFileUrl: vi.fn(),
}))

vi.mock('@/service/base', () => ({
  postForm: vi.fn(),
}))

const mockedGetConversationFileUrl = vi.mocked(getConversationFileUrl)
const mockedPostForm = vi.mocked(postForm)

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 10,
    conversation_id: 20,
    sender_type: 'agent',
    sender_id: 1,
    sender_name: 'Agent',
    sender_avatar: null,
    content_type: 'text',
    content: 'hello',
    created_at: '2026-07-04T00:00:00Z',
    ...overrides,
  }
}

describe('buildKnowledgeInspirationPayloadFromMessage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('copies rich-text conversation images into persistent knowledge image URLs', async () => {
    mockedGetConversationFileUrl.mockResolvedValue({
      url: 'https://signed.example.com/source.png',
      expires_seconds: 300,
    })
    mockedPostForm.mockResolvedValue({
      url: 'https://cdn.example.com/custom-field-files/copied.png',
      name: 'source.png',
      size: 12,
      content_type: 'image/png',
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      new Blob(['image-bytes'], { type: 'image/png' }),
      { status: 200 },
    )))

    const payload = await buildKnowledgeInspirationPayloadFromMessage(makeMessage({
      content_type: 'rich_text',
      content: '<p>hello</p><img data-file-id="file_123" data-name="source.png" alt="source.png">',
    }))

    expect(mockedGetConversationFileUrl).toHaveBeenCalledWith({
      conversationId: 20,
      fileId: 'file_123',
      downloadName: 'source.png',
    })
    expect(mockedPostForm).toHaveBeenCalledTimes(1)
    expect(payload).toMatchObject({
      content_format: 'rich_text',
      source_conversation_id: 20,
      source_message_id: 10,
    })
    expect(payload.content).toContain('src="https://cdn.example.com/custom-field-files/copied.png"')
    expect(payload.content).not.toContain('data-file-id')
    expect(payload.content).not.toContain('data-name')
  })

  it('leaves plain text messages synchronous in shape', async () => {
    const payload = await buildKnowledgeInspirationPayloadFromMessage(makeMessage({ content: ' hello ' }))

    expect(payload.content).toBe('hello')
    expect(payload.content_format).toBe('text')
    expect(mockedGetConversationFileUrl).not.toHaveBeenCalled()
    expect(mockedPostForm).not.toHaveBeenCalled()
  })

  it('turns an image message into persistent rich text content', async () => {
    mockedGetConversationFileUrl.mockResolvedValue({
      url: 'https://signed.example.com/source.png',
      expires_seconds: 300,
    })
    mockedPostForm.mockResolvedValue({
      url: 'https://cdn.example.com/custom-field-files/source.png',
      name: 'source.png',
      size: 12,
      content_type: 'image/png',
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      new Blob(['image-bytes'], { type: 'image/png' }),
      { status: 200 },
    )))

    const payload = await buildKnowledgeInspirationPayloadFromMessage(makeMessage({
      content_type: 'image',
      content: JSON.stringify({
        schema_version: 1,
        file_id: 'file_123',
        name: 'source.png',
        size: 12,
        mime_type: 'image/png',
      }),
    }))

    expect(payload.content_format).toBe('rich_text')
    expect(payload.content).toContain('src="https://cdn.example.com/custom-field-files/source.png"')
    expect(payload.content).not.toContain('signed.example.com')
    expect(payload.content).not.toContain('file_123')
  })
})
