import { describe, expect, it } from 'vitest'

import {
  createPendingAttachmentContent,
  parsePendingAttachmentContent,
} from './pending-attachment'

describe('pending attachment content', () => {
  it('keeps the local attachment details required for a failed-message bubble', () => {
    const file = new File(['hello'], 'report.txt', { type: 'text/plain' })
    const content = createPendingAttachmentContent(file, 'blob:https://example.test/local-file')

    expect(parsePendingAttachmentContent(content)).toEqual({
      schema_version: 1,
      pending_attachment: true,
      local_url: 'blob:https://example.test/local-file',
      name: 'report.txt',
      size: 5,
      mime_type: 'text/plain',
    })
  })

  it('does not treat persisted attachment content as a pending local attachment', () => {
    expect(parsePendingAttachmentContent(JSON.stringify({
      schema_version: 1,
      file_id: 'file-id',
      name: 'report.txt',
      size: 5,
      mime_type: 'text/plain',
    }))).toBeNull()
  })
})
