import { describe, expect, it } from 'vitest'

import {
  autoOutboundIncomingForCallRecord,
  autoOutboundBusinessTabForIncoming,
  autoOutboundTaskId,
  callTypeLabel,
  isAutoOutboundIncoming,
  resolveAutoOutboundRecordId,
  restoredAutoOutboundContext,
  shouldAutoAcceptAutoOutbound,
  shouldKeepAutoAnswerChime,
  shouldShowAutoOutboundBusinessTab,
} from '@/lib/auto-outbound-incoming'

describe('isAutoOutboundIncoming', () => {
  it('requires source auto_outbound', () => {
    expect(isAutoOutboundIncoming(null)).toBe(false)
    expect(isAutoOutboundIncoming({})).toBe(false)
    expect(isAutoOutboundIncoming({ source: 'inbound' })).toBe(false)
    expect(isAutoOutboundIncoming({ source: 'auto_outbound' })).toBe(true)
    expect(isAutoOutboundIncoming({ source: 'personal_auto_outbound' })).toBe(true)
  })
})

describe('restoredAutoOutboundContext', () => {
  it('keeps valid server-owned business context', () => {
    expect(
      restoredAutoOutboundContext({
        source: 'auto_outbound',
        task_id: 12,
        record_id: 34,
      }),
    ).toEqual({ source: 'auto_outbound', task_id: 12, record_id: 34 })
  })

  it('drops invalid ids from a restore response', () => {
    expect(
      restoredAutoOutboundContext({
        source: 'auto_outbound',
        task_id: 0,
        record_id: -1,
      }),
    ).toEqual({ source: 'auto_outbound', task_id: undefined, record_id: undefined })
  })
})

describe('autoOutboundIncomingForCallRecord', () => {
  it('builds business context for a server-enriched recent call', () => {
    expect(
      autoOutboundIncomingForCallRecord({
        call_id: 'call-1',
        call_source: 'auto_outbound',
        direction: 'outbound',
        customer_number: '95002',
        service_number: '9000000',
        started_at: '2026-08-25T13:11:19Z',
        source: 'auto_outbound',
        task_id: 12,
        record_id: 34,
      }),
    ).toEqual({
      offer_id: '',
      call_id: 'call-1',
      from: '9000000',
      to: '95002',
      queue_id: null,
      startedAt: Date.parse('2026-08-25T13:11:19Z'),
      direction: 'outbound',
      source: 'auto_outbound',
      task_id: 12,
      record_id: 34,
    })
  })

  it('does not expose the business tab for a regular recent call', () => {
    expect(
      autoOutboundIncomingForCallRecord({
        call_id: 'call-2',
        call_source: 'inbound',
        direction: 'inbound',
        source: null,
        task_id: null,
        record_id: null,
      }),
    ).toBeNull()
  })
})

describe('shouldKeepAutoAnswerChime', () => {
  it('keeps playing while the offer is ringing or connected', () => {
    expect(shouldKeepAutoAnswerChime('incoming')).toBe(true)
    expect(shouldKeepAutoAnswerChime('on_call')).toBe(true)
  })

  it('stops once the offer is gone', () => {
    expect(shouldKeepAutoAnswerChime('idle')).toBe(false)
    expect(shouldKeepAutoAnswerChime('wrap_up')).toBe(false)
    expect(shouldKeepAutoAnswerChime('outbound_ringing')).toBe(false)
    expect(shouldKeepAutoAnswerChime('mic_denied')).toBe(false)
  })
})

describe('shouldAutoAcceptAutoOutbound', () => {
  it('auto-accepts web phone auto-outbound offers', () => {
    expect(
      shouldAutoAcceptAutoOutbound({
        source: 'auto_outbound',
        deviceType: 'webrtc',
      }),
    ).toBe(true)
    expect(
      shouldAutoAcceptAutoOutbound({
        source: 'personal_auto_outbound',
        deviceType: 'webrtc',
      }),
    ).toBe(true)
    expect(
      shouldAutoAcceptAutoOutbound({
        source: 'auto_outbound',
        deviceType: undefined,
      }),
    ).toBe(true)
  })

  it('does not auto-accept ordinary inbound or SIP desk phones', () => {
    expect(
      shouldAutoAcceptAutoOutbound({
        source: undefined,
        deviceType: 'webrtc',
      }),
    ).toBe(false)
    expect(
      shouldAutoAcceptAutoOutbound({
        source: 'auto_outbound',
        deviceType: 'sip_phone',
      }),
    ).toBe(false)
  })

  it('skips restore / already-answered offers', () => {
    expect(
      shouldAutoAcceptAutoOutbound({
        source: 'auto_outbound',
        deviceType: 'webrtc',
        restore: true,
      }),
    ).toBe(false)
    expect(
      shouldAutoAcceptAutoOutbound({
        source: 'auto_outbound',
        deviceType: 'webrtc',
        alreadyAnswered: true,
      }),
    ).toBe(false)
  })
})

describe('shouldShowAutoOutboundBusinessTab', () => {
  it('requires auto_outbound source and a positive task_id', () => {
    expect(shouldShowAutoOutboundBusinessTab(null)).toBe(false)
    expect(shouldShowAutoOutboundBusinessTab({ source: 'auto_outbound' })).toBe(false)
    expect(
      shouldShowAutoOutboundBusinessTab({ source: 'auto_outbound', task_id: 0 }),
    ).toBe(false)
    expect(
      shouldShowAutoOutboundBusinessTab({ source: 'auto_outbound', task_id: 12 }),
    ).toBe(true)
    expect(
      shouldShowAutoOutboundBusinessTab({ source: 'personal_auto_outbound', task_id: 12 }),
    ).toBe(false)
    expect(
      shouldShowAutoOutboundBusinessTab({ source: 'inbound', task_id: 12 }),
    ).toBe(false)
  })
})

describe('autoOutboundBusinessTabForIncoming', () => {
  it('selects the matching business tab for auto-outbound offers', () => {
    expect(
      autoOutboundBusinessTabForIncoming({ source: 'auto_outbound', task_id: 12 }),
    ).toBe('auto_outbound')
    expect(
      autoOutboundBusinessTabForIncoming({
        source: 'personal_auto_outbound',
        record_id: 34,
      }),
    ).toBe('personal_auto_outbound')
  })

  it('does not select a business tab without a valid business record', () => {
    expect(autoOutboundBusinessTabForIncoming(null)).toBeNull()
    expect(autoOutboundBusinessTabForIncoming({ source: 'auto_outbound' })).toBeNull()
    expect(
      autoOutboundBusinessTabForIncoming({ source: 'personal_auto_outbound', record_id: 0 }),
    ).toBeNull()
    expect(
      autoOutboundBusinessTabForIncoming({ source: 'inbound', task_id: 12, record_id: 34 }),
    ).toBeNull()
  })
})

describe('resolveAutoOutboundRecordId', () => {
  it('prefers push record_id', () => {
    expect(
      resolveAutoOutboundRecordId({
        pushRecordId: 99,
        callRecordId: 1,
        records: [{ id: 5, call_record_id: 1 }],
      }),
    ).toBe(99)
  })

  it('matches by call_record_id when push omits record_id', () => {
    expect(
      resolveAutoOutboundRecordId({
        callRecordId: 77,
        records: [
          { id: 1, call_record_id: 10 },
          { id: 2, call_record_id: 77 },
        ],
      }),
    ).toBe(2)
  })

  it('falls back to open agent record for the same phone', () => {
    expect(
      resolveAutoOutboundRecordId({
        phoneNumber: '13800138000',
        records: [
          {
            id: 3,
            phone_number: '13800138000',
            reception_type: 'agent',
            reception_result: { submitted_by: 1 },
          },
          {
            id: 4,
            phone_number: '13800138000',
            reception_type: 'agent',
            reception_result: null,
          },
        ],
      }),
    ).toBe(4)
  })
})

describe('autoOutboundTaskId / callTypeLabel', () => {
  it('parses task id', () => {
    expect(autoOutboundTaskId({ task_id: 8 })).toBe(8)
    expect(autoOutboundTaskId({ task_id: -1 })).toBeNull()
  })

  it('labels auto outbound distinctly from inbound', () => {
    expect(
      callTypeLabel({ isAutoOutbound: true, direction: 'inbound', locale: 'zh' }),
    ).toBe('自动外呼')
    expect(
      callTypeLabel({ isAutoOutbound: true, direction: 'inbound', locale: 'en' }),
    ).toBe('Auto outbound')
    expect(
      callTypeLabel({ isAutoOutbound: false, direction: 'inbound', locale: 'zh' }),
    ).toBe('呼入')
    expect(
      callTypeLabel({ isAutoOutbound: false, direction: 'outbound', locale: 'en' }),
    ).toBe('Outbound')
  })
})
