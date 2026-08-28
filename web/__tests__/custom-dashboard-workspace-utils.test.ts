import { describe, expect, it } from 'vitest'
import type { DashboardFilter } from '@/models/custom-dashboard'
import type { UnifiedField } from '@/models/field-definition'
import {
  buildDashboardDrilldownConditions,
  buildDashboardDrilldownUrl,
  parseDashboardFilterValues,
  sanitizeDashboardFilterValues,
} from '@/utils/custom-dashboard'

const filters: DashboardFilter[] = [
  { id: 'date', type: 'date_range', name: 'Date', field_keys: ['system:created_at'] },
  { id: 'level', type: 'field_option', name: 'Level', field_key: 'custom:customer_level' },
]

describe('workspace dashboard filters', () => {
  it('ignores unknown and malformed URL values', () => {
    const parsed = parseDashboardFilterValues(JSON.stringify({ unknown: 1, date: { start: 'bad', end: 'bad' }, level: 'vip' }), filters)
    expect(parsed).toEqual({ values: { level: 'vip' }, invalid: true })
  })

  it('builds ticket conditions from page filters and component drilldown', () => {
    const fields = [{ id: 9, key: 'customer_level', source: 'custom' }] as UnifiedField[]
    const conditions = buildDashboardDrilldownConditions(
      { drilldown: { where: { 'system:status': { in: ['pending'] } } } },
      filters,
      { date: { start: '2026-08-01', end: '2026-08-26' }, level: 'vip' },
      fields,
    )
    expect(conditions).toEqual(expect.arrayContaining([
      { field_id: null, field_key: 'created_at', operator: 'gte', value: '2026-08-01' },
      { field_id: 9, field_key: null, operator: 'in', value: ['vip'] },
      { field_id: null, field_key: 'status', operator: 'in', value: ['pending'] },
    ]))
  })

  it('drops disabled option values restored from a URL', () => {
    const fields = [{
      id: 9,
      key: 'customer_level',
      source: 'custom',
      field_type: 'single_select',
      type_config: {},
      options: [{ value: 'vip', is_active: false }],
      tree_nodes: [],
    }] as UnifiedField[]
    expect(sanitizeDashboardFilterValues({ level: 'vip' }, filters, fields)).toEqual({ values: {}, invalid: true })
  })

  it('keeps source dashboard filters in the return URL', () => {
    const url = buildDashboardDrilldownUrl(3, [], { level: 'vip' })
    const params = new URL(url, 'https://example.test').searchParams
    expect(params.get('from')).toBe('dashboard')
    expect(params.get('dashboardFilterValues')).toBe('{"level":"vip"}')
  })
})
