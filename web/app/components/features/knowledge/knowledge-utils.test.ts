import { describe, expect, it } from 'vitest'
import type { KnowledgeDocument } from '@/models/knowledge'
import {
  buildKnowledgeSendPlan,
  knowledgeDocumentHasComposerBody,
  knowledgeDocumentHasComposerSendableContent,
  knowledgeDocumentHasMessageBody,
  knowledgeDocumentHasSendableContent,
  knowledgeHtmlToComposerText,
  knowledgeHtmlToMessageText,
  stripKnowledgeHtml,
} from './knowledge-utils'

function knowledgeDocument(
  contentHtml: string,
  attachmentCount = 0,
): KnowledgeDocument {
  return {
    id: 1,
    tenant_id: 1,
    directory_id: 1,
    directory_path: [],
    title: 'Document',
    content_html: contentHtml,
    attachments: Array.from({ length: attachmentCount }, (_, index) => ({
      id: index + 1,
      document_id: 1,
      name: `file-${index + 1}.pdf`,
      size: 10,
      mime_type: 'application/pdf',
      sort_order: index,
      created_at: '2026-07-15T00:00:00Z',
      updated_at: '2026-07-15T00:00:00Z',
    })),
    status: 'published',
    display_status: 'published',
    validity_type: 'permanent',
    valid_from: null,
    valid_to: null,
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
    created_by: null,
    updated_by: null,
  }
}

describe('knowledge HTML helpers', () => {
  it('treats image-only content with alt text as non-empty', () => {
    const html = '<p><img src="https://cdn.example.com/a.png" alt="退款截图"></p>'

    expect(stripKnowledgeHtml(html)).toBe('退款截图')
  })

  it('uses an image placeholder when image-only content has no label', () => {
    const html = '<p><img src="https://cdn.example.com/a.png"></p>'

    expect(knowledgeHtmlToMessageText(html)).toBe('[image]')
  })

  it('ignores img tags without src', () => {
    expect(stripKnowledgeHtml('<p><img alt="missing"></p>')).toBe('')
  })

  it('does not treat data-src as a persisted image source', () => {
    expect(stripKnowledgeHtml('<p><img data-src="https://cdn.example.com/a.png" alt="missing"></p>')).toBe('')
  })

  it('omits image labels and placeholders from plain composer text', () => {
    const html = [
      '<p>你好<img src="https://cdn.example.com/a.png" alt="20103df0.png">世界</p>',
      '<p><img src="https://cdn.example.com/b.png" title="receipt.png"></p>',
      '<p>结束</p>',
    ].join('')

    expect(knowledgeHtmlToComposerText(html)).toBe('你好 世界\n结束')
  })

  it('omits consecutive images without leaving empty lines', () => {
    const html = [
      '<p><img src="https://cdn.example.com/a.png" alt="a.png"></p>',
      '<p><img src="https://cdn.example.com/b.png"></p>',
      '<p>正文</p>',
    ].join('')

    expect(knowledgeHtmlToComposerText(html)).toBe('正文')
  })
})

describe('knowledge send plan', () => {
  const attachments = [
    {
      id: 11,
      document_id: 5,
      name: 'first.pdf',
      size: 10,
      mime_type: 'application/pdf',
      sort_order: 0,
      created_at: '2026-07-15T00:00:00Z',
      updated_at: '2026-07-15T00:00:00Z',
    },
    {
      id: 12,
      document_id: 5,
      name: 'second.pdf',
      size: 20,
      mime_type: 'application/pdf',
      sort_order: 1,
      created_at: '2026-07-15T00:00:00Z',
      updated_at: '2026-07-15T00:00:00Z',
    },
  ]

  it('puts body before one file message per attachment', () => {
    const plan = buildKnowledgeSendPlan({
      messageHtml: '<p>正文</p>',
      messageText: '正文',
      attachments,
      requestId: 'request-1',
    })

    expect(plan.map((item) => item.kind)).toEqual(['body', 'attachment', 'attachment'])
    expect(plan.map((item) => item.clientMessageId)).toEqual([
      'knowledge:request-1:body',
      'knowledge:request-1:attachment:11',
      'knowledge:request-1:attachment:12',
    ])
  })

  it('skips the body for an attachment-only document', () => {
    const plan = buildKnowledgeSendPlan({
      messageHtml: '<p></p>',
      messageText: '',
      attachments,
      requestId: 'request-2',
    })

    expect(plan.map((item) => item.kind)).toEqual(['attachment', 'attachment'])
  })
})

describe('knowledge document sendable content', () => {
  it('accepts a document with text content', () => {
    const document = knowledgeDocument('<p>正文</p>')

    expect(knowledgeDocumentHasMessageBody(document)).toBe(true)
    expect(knowledgeDocumentHasSendableContent(document)).toBe(true)
  })

  it('accepts a document with a persisted inline image', () => {
    const document = knowledgeDocument('<p><img src="https://cdn.example.com/a.png"></p>')

    expect(knowledgeDocumentHasMessageBody(document)).toBe(true)
    expect(knowledgeDocumentHasComposerBody(document, 'text')).toBe(false)
    expect(knowledgeDocumentHasComposerBody(document, 'rich_text')).toBe(true)
    expect(knowledgeDocumentHasComposerSendableContent(document, 'text')).toBe(false)
    expect(knowledgeDocumentHasComposerSendableContent(document, 'rich_text')).toBe(true)
  })

  it('accepts an attachment-only document without a message body', () => {
    const document = knowledgeDocument('<p></p>', 1)

    expect(knowledgeDocumentHasMessageBody(document)).toBe(false)
    expect(knowledgeDocumentHasSendableContent(document)).toBe(true)
    expect(knowledgeDocumentHasComposerSendableContent(document, 'text')).toBe(true)
  })

  it('rejects a document without body, image, or attachments', () => {
    const document = knowledgeDocument('<p><br></p>')

    expect(knowledgeDocumentHasSendableContent(document)).toBe(false)
  })
})
