import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildOpenAgentChatRequestBody,
  streamOpenAgentConversation,
} from './use-open-agent-conversation'


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

describe('streamOpenAgentConversation visitor session recovery', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('retries a pre-flight 401 as a fresh attempt with the new token', async () => {
    const recoverVisitorSession = vi.fn().mockResolvedValue('tok_new')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(
        '{"detail":"Invalid or expired visitor session"}',
        { status: 401 },
      ))
      .mockResolvedValueOnce(new Response('event: done\ndata: {}\n\n', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const onRecoveredAuth = vi.fn()
    const onRetry = vi.fn()
    const onError = vi.fn()
    const onDone = vi.fn()
    const controller = streamOpenAgentConversation({
      conversationPublicId: 'cv_1',
      visitorSessionToken: 'tok_old',
      message: 'hi',
      recoverVisitorSession,
      retry: { maxRetries: 2, baseDelayMs: 10_000 },
      handlers: { onRecoveredAuth, onRetry, onError, onDone },
    })

    await controller.completion

    expect(recoverVisitorSession).toHaveBeenCalledOnce()
    expect(onRecoveredAuth).toHaveBeenCalledOnce()
    expect(onRetry).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
    expect(onDone).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const firstInit = fetchMock.mock.calls[0]?.[1] as RequestInit
    const secondInit = fetchMock.mock.calls[1]?.[1] as RequestInit
    expect(firstInit.headers).toMatchObject({ Authorization: 'Bearer tok_old' })
    expect(secondInit.headers).toMatchObject({ Authorization: 'Bearer tok_new' })
    const retryBody = JSON.parse(String(secondInit.body)) as {
      resume: boolean
      message?: string
    }
    expect(retryBody.resume).toBe(false)
    expect(retryBody.message).toBe('hi')
  })

  it('does not remint a non-recoverable HTTP failure', async () => {
    const recoverVisitorSession = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('bad request', { status: 400 })))

    const onRecoveredAuth = vi.fn()
    const onError = vi.fn()
    const controller = streamOpenAgentConversation({
      conversationPublicId: 'cv_1',
      visitorSessionToken: 'tok_old',
      message: 'hi',
      recoverVisitorSession,
      handlers: { onRecoveredAuth, onError },
    })

    await controller.completion

    expect(recoverVisitorSession).not.toHaveBeenCalled()
    expect(onRecoveredAuth).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledOnce()
  })

  it('does not remint a 5xx that mentions 401 in the body', async () => {
    const recoverVisitorSession = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('upstream returned 401', { status: 500 }),
    ))

    const onRecoveredAuth = vi.fn()
    const controller = streamOpenAgentConversation({
      conversationPublicId: 'cv_1',
      visitorSessionToken: 'tok_old',
      message: 'hi',
      recoverVisitorSession,
      retry: { maxRetries: 0, baseDelayMs: 1 },
      handlers: { onRecoveredAuth },
    })

    await controller.completion

    expect(recoverVisitorSession).not.toHaveBeenCalled()
    expect(onRecoveredAuth).not.toHaveBeenCalled()
  })

  it('bounds remint retries when HTTP 401 persists and remint always succeeds', async () => {
    const recoverVisitorSession = vi.fn().mockImplementation(
      async () => `tok_${recoverVisitorSession.mock.calls.length + 1}`,
    )
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response('{"detail":"Invalid or expired visitor session"}', { status: 401 }),
    ))
    vi.stubGlobal('fetch', fetchMock)

    const onRecoveredAuth = vi.fn()
    const onRetry = vi.fn()
    const onError = vi.fn()
    const controller = streamOpenAgentConversation({
      conversationPublicId: 'cv_1',
      visitorSessionToken: 'tok_old',
      message: 'hi',
      recoverVisitorSession,
      retry: { maxRetries: 2, baseDelayMs: 10_000 },
      handlers: { onRecoveredAuth, onRetry, onError },
    })

    await controller.completion

    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(3)
    expect(recoverVisitorSession.mock.calls.length).toBeLessThanOrEqual(2)
    expect(onRecoveredAuth).toHaveBeenCalledTimes(2)
    expect(onRetry).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledOnce()
    expect(onError).toHaveBeenCalledWith(
      expect.any(String),
      { authRecoverable: true },
    )
  })

  it('does not remint HTTP 422 that mentions visitor_session_token', async () => {
    const recoverVisitorSession = vi.fn()
    const onRecoveredAuth = vi.fn()
    const onError = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('{"detail":"visitor_session_token is required"}', { status: 422 }),
    ))

    const controller = streamOpenAgentConversation({
      conversationPublicId: 'cv_1',
      visitorSessionToken: 'tok_old',
      message: 'hi',
      recoverVisitorSession,
      handlers: { onRecoveredAuth, onError },
    })

    await controller.completion

    expect(recoverVisitorSession).not.toHaveBeenCalled()
    expect(onRecoveredAuth).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledOnce()
  })

  it('still marks a mid-stream 5xx retry as resume', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('upstream failed', { status: 500 }))
      .mockResolvedValueOnce(new Response('event: done\ndata: {}\n\n', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const controller = streamOpenAgentConversation({
      conversationPublicId: 'cv_1',
      visitorSessionToken: 'tok_old',
      message: 'hi',
      retry: { maxRetries: 1, baseDelayMs: 1 },
      handlers: {},
    })

    await controller.completion

    const retryBody = JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body)) as {
      resume: boolean
      message?: string
    }
    expect(retryBody.resume).toBe(true)
    expect(retryBody.message).toBe('hi')
  })
})
