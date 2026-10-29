import { describe, expect, it } from 'vitest'
import { HTTPError } from 'ky'
import { describeFileSendError, isEmptyUploadFile, readBusinessErrorCode } from './file-send-error'

function httpError(body: unknown, status = 400): HTTPError {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
  return new HTTPError(response, new Request('https://example.com/api/v1/files'), {
    message: 'Request failed',
  } as never)
}

describe('isEmptyUploadFile', () => {
  it('treats zero-byte files as empty', () => {
    expect(isEmptyUploadFile({ size: 0 })).toBe(true)
    expect(isEmptyUploadFile({ size: 1 })).toBe(false)
  })
})

describe('describeFileSendError', () => {
  it('prefers the backend business message', async () => {
    await expect(
      describeFileSendError(httpError({ code: 'VALIDATION_ERROR', message: 'File is empty' })),
    ).resolves.toBe('File is empty')
  })

  it('falls back to http status when the body has no message', async () => {
    await expect(describeFileSendError(httpError({}, 413))).resolves.toBe('http_413')
  })

  it('uses Error.message for non-HTTP failures', async () => {
    await expect(describeFileSendError(new Error('network down'))).resolves.toBe('network down')
  })

  it('returns unknown for non-error values', async () => {
    await expect(describeFileSendError(null)).resolves.toBe('unknown')
  })
})

describe('readBusinessErrorCode', () => {
  it('returns the backend business code', async () => {
    const error = httpError({ code: 'LEAVE_MESSAGE_HOURS_OPEN', message: 'Leave message is only available outside service hours' })
    await expect(readBusinessErrorCode(error)).resolves.toBe('LEAVE_MESSAGE_HOURS_OPEN')
    // The body stays readable for describeFileSendError afterwards.
    await expect(describeFileSendError(error)).resolves.toBe('Leave message is only available outside service hours')
  })

  it('returns null without a code or for non-HTTP failures', async () => {
    await expect(readBusinessErrorCode(httpError({ message: 'x' }))).resolves.toBeNull()
    await expect(readBusinessErrorCode(new Error('network down'))).resolves.toBeNull()
  })
})
