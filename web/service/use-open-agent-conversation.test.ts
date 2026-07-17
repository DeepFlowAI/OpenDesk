import { describe, expect, it } from 'vitest'

import { buildOpenAgentChatRequestBody } from './use-open-agent-conversation'


describe('buildOpenAgentChatRequestBody', () => {
  it('builds an attachment-only request with stable retry identifiers', () => {
    const attachment = {
      file_id: 'file_1',
      type: 'file' as const,
      name: 'demo.pdf',
      mime_type: 'application/pdf',
      size: 12,
    }

    const body = buildOpenAgentChatRequestBody({
      attachments: [attachment],
      requestId: 'req_1',
      clientMessageId: 'cm_1',
      resume: true,
      lastEventId: 'r1-e2',
    })

    expect(body).toEqual({
      attachments: [attachment],
      request_id: 'req_1',
      client_message_id: 'cm_1',
      resume: true,
      last_event_id: 'r1-e2',
    })
    expect(body).not.toHaveProperty('message')
  })
})
