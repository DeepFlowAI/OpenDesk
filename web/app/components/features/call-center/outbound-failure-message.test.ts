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

  it('treats agent hangup after a connected call as a normal end', () => {
    const result = mapOutboundFailure({ reason: 'agent_hangup' })
    expect(result.message).toBeNull()
    expect(result.level).toBe('info')
    expect(result.isFallback).toBe(false)
  })

  it('treats the end of the post-call satisfaction survey as a normal end', () => {
    for (const reason of [
      'satisfaction_completed',
      'satisfaction_partial',
      'satisfaction_unanswered',
      'satisfaction_failed',
    ]) {
      expect(mapOutboundFailure({ reason }).message).toBeNull()
    }
  })

  it('keeps local_cancel as ring timeout even when SIP 487 is attached', () => {
    const result = mapOutboundFailure({ reason: 'local_cancel', sip_status: 487 })
    expect(result.message).toBe('振铃超时，对方未接听')
    expect(result.isFallback).toBe(false)
  })

  it.each([
    [486, '对方占线'],
    [480, '对方暂时无法接通'],
    [403, '该号码无权外呼'],
    [408, '振铃超时'],
    [410, '该号码已失效'],
    [478, '无法解析被叫号码'],
    [484, '号码不完整'],
    [487, '呼叫已取消'],
    [488, '媒体协商失败'],
    [491, '对方正在处理另一路呼叫'],
    [500, '运营商线路异常'],
    [503, '运营商线路繁忙'],
    [504, '运营商响应超时'],
    [600, '对方占线'],
    [603, '对方拒接'],
    [604, '该号码不存在'],
    [606, '对方无法接受此呼叫'],
    [608, '对方拒接'],
  ] as const)('maps SIP %s to a known hint regardless of reason bucket', (sip, message) => {
    const result = mapOutboundFailure({ reason: 'originate_failed', sip_status: sip })
    expect(result.message).toBe(message)
    expect(result.isFallback).toBe(false)
  })

  it('falls back to SIP family wording for unlisted final responses', () => {
    expect(mapOutboundFailure({ reason: 'rejected', sip_status: 418 }).message).toBe(
      '呼叫被拒绝',
    )
    expect(mapOutboundFailure({ reason: 'originate_failed', sip_status: 555 }).message).toBe(
      '运营商线路异常',
    )
    expect(mapOutboundFailure({ reason: null, sip_status: 699 }).message).toBe(
      '对方无法接通',
    )
  })

  it('does not treat provisional 1xx leftovers as a SIP failure', () => {
    const result = mapOutboundFailure({ reason: 'weird_reason', sip_status: 183 })
    expect(result.isFallback).toBe(true)
    expect(result.message).toContain('weird_reason')
  })
})
