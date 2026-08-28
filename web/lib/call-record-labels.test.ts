import { describe, expect, it } from 'vitest'

import { formatHangupReason } from './call-record-labels'

describe('formatHangupReason', () => {
  it('uses the shared call-record translations for classified provider reasons', () => {
    expect(formatHangupReason('provider_not_found')).toBe('供应商未找到号码或路由')
    expect(formatHangupReason('provider_not_found', false)).toBe(
      'Provider could not find the number or route',
    )
  })

  it('keeps legacy labels and unknown reason fallback behavior', () => {
    expect(formatHangupReason('remote_bye')).toBe('访客挂断')
    expect(formatHangupReason('future_provider_reason')).toBe('future_provider_reason')
  })
})
