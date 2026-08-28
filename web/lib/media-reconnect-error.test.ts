import { HTTPError } from 'ky'
import { describe, expect, it } from 'vitest'

import { isCurrentCallGoneError } from '@/lib/media-reconnect-error'

function httpError(status: number, body: unknown): HTTPError {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
  return new HTTPError(
    response,
    new Request('https://example.test/api/v1/call-center/agents/me/current-call/media-reconnect'),
    { message: 'Request failed' } as never,
  )
}

describe('isCurrentCallGoneError', () => {
  it('treats 404 media-reconnect as the call already ended', async () => {
    expect(
      await isCurrentCallGoneError(
        httpError(404, { code: 'NOT_FOUND', message: '当前没有进行中的通话' }),
      ),
    ).toBe(true)
    expect(
      await isCurrentCallGoneError(
        new Error(
          'Request failed with status code 404 Not Found: POST https://x/media-reconnect',
        ),
      ),
    ).toBe(true)
  })

  it('does not swallow real reconnect failures', async () => {
    expect(
      await isCurrentCallGoneError(
        httpError(409, { code: 'CONFLICT', message: '客户正在满意度调查中，无法恢复坐席媒体' }),
      ),
    ).toBe(false)
    expect(await isCurrentCallGoneError(new Error('ICE 连接失败'))).toBe(false)
  })
})
