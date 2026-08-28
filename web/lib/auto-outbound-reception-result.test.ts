import { describe, expect, it } from 'vitest'

import { summarizeReceptionResult } from '@/lib/auto-outbound-reception-result'

describe('summarizeReceptionResult', () => {
  it('returns dash for empty / null / unparsed values', () => {
    expect(summarizeReceptionResult(null, 'ivr', 'zh')).toBe('—')
    expect(summarizeReceptionResult(undefined, 'bot', 'zh')).toBe('—')
    expect(summarizeReceptionResult('', 'agent', 'zh')).toBe('—')
    expect(summarizeReceptionResult('not-json', 'ivr', 'zh')).toBe('—')
    expect(summarizeReceptionResult({}, 'none', 'zh')).toBe('—')
  })

  it('summarizes abandoned calls', () => {
    expect(summarizeReceptionResult({ abandoned: true }, 'none', 'zh')).toBe('呼损')
    expect(summarizeReceptionResult({ abandoned: true, reason: 'no_agent' }, null, 'en')).toBe(
      'Abandoned',
    )
  })

  it('summarizes IVR exit and collected keys', () => {
    expect(
      summarizeReceptionResult(
        { exit: 'simulated', degraded: true, collected: {} },
        'ivr',
        'zh',
      ),
    ).toBe('流程出口：simulated')

    expect(
      summarizeReceptionResult(
        { exit: 'end', collected: { rating: '5', comment: 'ok' } },
        'ivr',
        'zh',
      ),
    ).toBe('流程出口：end · 按键：rating=5, comment=ok')

    expect(
      summarizeReceptionResult({ collected: { digit: '1' } }, 'ivr', 'en'),
    ).toBe('Keys: digit=1')

    expect(summarizeReceptionResult({ collected: {} }, 'ivr', 'zh')).toBe('—')
  })

  it('summarizes bot intent and transfer flags', () => {
    expect(summarizeReceptionResult({ intent: '有意向' }, 'bot', 'zh')).toBe('有意向')
    expect(
      summarizeReceptionResult({ intent: '有意向', handoff: true }, 'bot', 'zh'),
    ).toBe('有意向 · 已转人工')
    expect(
      summarizeReceptionResult({ intent: 'hot', transferred: true }, 'bot', 'en'),
    ).toBe('hot · Transferred to agent')
    expect(summarizeReceptionResult({ transfer: true }, 'bot', 'zh')).toBe('已转人工')
    expect(summarizeReceptionResult({ intent: null, handoff: false }, 'bot', 'zh')).toBe('—')
  })

  it('summarizes agent wrap-up business fields', () => {
    expect(
      summarizeReceptionResult(
        { field_values: { note: '跟进' }, submitted_by: 1, auto_submitted: false },
        'agent',
        'zh',
      ),
    ).toBe('note: 跟进')

    expect(
      summarizeReceptionResult(
        {
          field_values: { a: '1', b: '2', c: '3' },
          submitted_by: 1,
          auto_submitted: false,
        },
        'agent',
        'zh',
      ),
    ).toBe('已填 3 个字段')

    expect(
      summarizeReceptionResult(
        { field_values: { a: '1', b: '2' }, auto_submitted: true },
        'agent',
        'en',
      ),
    ).toBe('2 fields filled')

    // Assigned but wrap-up not submitted yet.
    expect(
      summarizeReceptionResult({ assigned: true, agent_id: 9, degraded: true }, 'agent', 'zh'),
    ).toBe('—')
  })

  it('does not dump raw JSON strings into the cell', () => {
    const raw = '{"exit":"simulated","degraded":true,"collected":{}}'
    expect(summarizeReceptionResult(raw, 'ivr', 'zh')).toBe('流程出口：simulated')
    expect(summarizeReceptionResult(raw, 'ivr', 'zh')).not.toContain('{')
  })
})
