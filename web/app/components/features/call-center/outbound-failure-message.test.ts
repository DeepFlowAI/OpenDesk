import { describe, expect, it } from 'vitest'

import { mapOutboundFailure } from './outbound-failure-message'

describe('mapOutboundFailure', () => {
  it('maps rejected + SIP 404 to a clear Chinese message', () => {
    const result = mapOutboundFailure({ reason: 'rejected', sip_status: 404 })
    expect(result.message).toBe('该号码无法路由')
    expect(result.level).toBe('error')
  })

  it('accepts sip_status as a string from socket payloads', () => {
    const result = mapOutboundFailure({
      reason: 'rejected',
      sip_status: '404' as unknown as number,
    })
    expect(result.message).toBe('该号码无法路由')
  })

  it('maps bare SIP 404 when reason is missing', () => {
    const result = mapOutboundFailure({ reason: null, sip_status: 404 })
    expect(result.message).toBe('该号码无法路由')
  })
})
