import { describe, expect, it } from 'vitest'
import { HTTPError } from 'ky'
import { readEmployeeErrorMessage } from './read-error-message'

function httpError(body: unknown, status = 400): HTTPError {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
  return new HTTPError(response, new Request('https://example.com/api/v1/employees'), {
    message: 'Request failed',
  } as never)
}

describe('readEmployeeErrorMessage', () => {
  it('prefers business-error message', async () => {
    const message = await readEmployeeErrorMessage(
      httpError({ code: 'VALIDATION_ERROR', message: 'Role not found or inactive' }),
      'fallback',
    )
    expect(message).toBe('Role not found or inactive')
  })

  it('reads FastAPI validation detail messages', async () => {
    const message = await readEmployeeErrorMessage(
      httpError({
        detail: [{ type: 'value_error', loc: ['body', 'roles'], msg: 'Value error, Each role must be one of: agent, admin' }],
      }, 422),
      'fallback',
    )
    expect(message).toContain('Each role must be one of')
  })

  it('falls back for unknown errors', async () => {
    await expect(readEmployeeErrorMessage(new Error('boom'), 'fallback')).resolves.toBe('fallback')
  })
})
