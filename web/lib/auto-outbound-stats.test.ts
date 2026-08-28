import { describe, expect, it } from 'vitest'
import { mapResultDistributionItems } from '@/lib/auto-outbound-stats'

describe('mapResultDistributionItems', () => {
  it('maps ivr exits to label/count items', () => {
    const items = mapResultDistributionItems(
      'ivr',
      { exits: { unknown: 2, simulated: 1 }, collected: {} },
      'zh',
    )
    expect(items).toEqual([
      { label: 'unknown', count: 2 },
      { label: 'simulated', count: 1 },
    ])
  })

  it('maps bot intents and appends handoff count', () => {
    const items = mapResultDistributionItems(
      'bot',
      { intents: { 咨询价格: 3 }, handoff_count: 1, handoff_rate: 0.25 },
      'zh',
    )
    expect(items).toEqual([
      { label: '咨询价格', count: 3 },
      { label: '转人工', count: 1 },
    ])
  })

  it('maps agent breakdown with localized label', () => {
    const items = mapResultDistributionItems(
      'agent',
      { agents: [{ agent_id: 7, answered: 2, avg_duration_ms: 1500 }] },
      'en',
    )
    expect(items).toEqual([{ label: 'Agent 7', count: 2 }])
  })

  it('returns empty list for missing or malformed payloads', () => {
    expect(mapResultDistributionItems('ivr', undefined, 'zh')).toEqual([])
    expect(
      mapResultDistributionItems('agent', { exits: {}, collected: {} } as never, 'zh'),
    ).toEqual([])
  })
})
