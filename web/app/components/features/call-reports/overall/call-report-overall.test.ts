import { describe, expect, it } from 'vitest'
import {
  isCallTrendEmpty,
  type CallTrendChartBucket,
  type CallTrendChartMetric,
} from './build-call-trend-chart-option'
import {
  callDistributionSliceLabel,
  callGroupLabel,
  callMetricLabel,
  formatCallMetric,
} from './metric-format'

const metric: CallTrendChartMetric = {
  key: 'call_count',
  name: 'Total calls',
  format: 'integer',
  level: 'primary',
}

function bucket(value: number | null): CallTrendChartBucket {
  return {
    label: '2026-08-31',
    metrics: [{ key: 'call_count', value, format: 'integer' }],
  }
}

describe('overall call report presentation', () => {
  it('keeps unavailable values distinct from real zero counts', () => {
    expect(formatCallMetric(null, 'integer', 'en')).toBe('—')
    expect(formatCallMetric(0, 'integer', 'en')).toBe('0')
    expect(formatCallMetric(null, 'percent', 'en')).toBe('—')
    expect(formatCallMetric(0.125, 'percent', 'en')).toBe('12.5%')
  })

  it('localizes stable group and enum keys without translating tenant labels', () => {
    expect(callGroupLabel('inbound_service', 'zh')).toBe('呼入服务')
    expect(callDistributionSliceLabel(
      'satisfaction_trigger_source',
      { key: 'agent_invite', label: 'agent_invite', value: 2 },
      'en',
    )).toBe('Agent invitation')
    expect(callDistributionSliceLabel(
      'satisfaction_primary_option',
      { key: 'option-1', label: 'Very satisfied', value: 2 },
      'zh',
    )).toBe('Very satisfied')
  })

  it('localizes queue groups, metrics, and fixed distribution buckets', () => {
    expect(callGroupLabel('queue_waiting', 'zh')).toBe('等待与服务水平')
    expect(callMetricLabel('queue_service_level_20s', 'en')).toBe('20s service level')
    expect(callDistributionSliceLabel(
      'queue_wait_duration',
      { key: '20_60s', label: '20_60s', value: 3 },
      'zh',
    )).toBe('>20–60 秒')
    expect(callDistributionSliceLabel(
      'offer_result',
      { key: 'bridge_failed', label: 'bridge_failed', value: 1 },
      'en',
    )).toBe('Bridge failed')
  })

  it('treats null and zero-only trend buckets as empty', () => {
    expect(isCallTrendEmpty([metric], [bucket(null), bucket(0)])).toBe(true)
    expect(isCallTrendEmpty([metric], [bucket(1)])).toBe(false)
  })
})
