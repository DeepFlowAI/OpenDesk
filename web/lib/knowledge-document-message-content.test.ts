import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getConversationFileUrl } from '@/service/use-conversation-files'
import { postForm } from '@/service/base'

import {
  buildKnowledgeDocumentContentFromMessage,
  knowledgeFilePayloadFromMessage,
} from './knowledge-document-message-content'

vi.mock('@/service/use-conversation-files', () => ({
  getConversationFileUrl: vi.fn(),
}))

vi.mock('@/service/base', () => ({
  postForm: vi.fn(),
}))

const mockedGetConversationFileUrl = vi.mocked(getConversationFileUrl)
const mockedPostForm = vi.mocked(postForm)

describe('buildKnowledgeDocumentContentFromMessage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('accepts a structured file message for attachment staging', () => {
    const payload = knowledgeFilePayloadFromMessage({
      content_type: 'file',
      content: JSON.stringify({
        schema_version: 1,
        file_id: 'file_123',
        name: 'guide.pdf',
        size: 12,
        mime_type: 'application/pdf',
      }),
    })

    expect(payload).toEqual(expect.objectContaining({
      file_id: 'file_123',
      name: 'guide.pdf',
    }))
  })

  it('rejects an invalid file message for attachment staging', () => {
    expect(knowledgeFilePayloadFromMessage({
      content_type: 'file',
      content: JSON.stringify({
        schema_version: 1,
        name: 'guide.pdf',
        size: 12,
        mime_type: 'application/pdf',
      }),
    })).toBeNull()
    expect(knowledgeFilePayloadFromMessage({
      content_type: 'text',
      content: 'guide.pdf',
    })).toBeNull()
  })

  it('converts plain-text paragraphs and line breaks into editable HTML', async () => {
    await expect(buildKnowledgeDocumentContentFromMessage({
      conversation_id: 20,
      content_type: 'text',
      content: 'First line\nSecond line\n\nNext paragraph',
    })).resolves.toBe('<p>First line<br>Second line</p><p>Next paragraph</p>')
  })

  it('escapes plain-text HTML instead of treating it as markup', async () => {
    await expect(buildKnowledgeDocumentContentFromMessage({
      conversation_id: 20,
      content_type: 'text',
      content: '<strong>not HTML</strong>',
    })).resolves.toBe('<p>&lt;strong&gt;not HTML&lt;/strong&gt;</p>')
  })

  it('keeps safe rich-text structure and removes executable markup', async () => {
    await expect(buildKnowledgeDocumentContentFromMessage({
      conversation_id: 20,
      content_type: 'rich_text',
      content: '<p onclick="alert(1)"><strong>Answer</strong></p><script>alert(2)</script>',
    })).resolves.toBe('<p><strong>Answer</strong></p>')
  })

  it('prefills an image with a persistent URL', async () => {
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

    const content = await buildKnowledgeDocumentContentFromMessage({
      conversation_id: 20,
      content_type: 'image',
      content: JSON.stringify({
        schema_version: 1,
        file_id: 'file_123',
        name: 'source.png',
        size: 12,
        mime_type: 'image/png',
      }),
    })

    expect(content).toContain('src="https://cdn.example.com/custom-field-files/source.png"')
    expect(content).not.toContain('signed.example.com')
    expect(content).not.toContain('file_123')
  })
})
