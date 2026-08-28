// Regression: the stats tab used to crash with
// "TypeError: (… ?? []).map is not a function" because the API returns
// result_distribution as a mode-specific object while the UI expected an array.
import { renderToString } from 'react-dom/server'
import { createElement } from 'react'
import { describe, expect, it } from 'vitest'
import {
  DailyTrendBars,
  SimpleBarChart,
} from '@/app/components/features/engagement/auto-outbound-task-ui'
import { mapResultDistributionItems } from '@/lib/auto-outbound-stats'

// Shape captured verbatim from GET /api/v1/engagement/auto-outbound-tasks/3/stats.
const apiStats = {
  daily_trend: [{ date: '2026-08-07', call_count: 3, answered_count: 1, answer_rate: 0.33 }],
  terminal_state_distribution: [
    { terminal_state: 'answered', count: 1 },
    { terminal_state: 'no_answer', count: 1 },
    { terminal_state: 'power_off', count: 1 },
  ],
  result_distribution: { exits: { unknown: 2, simulated: 1 }, collected: {} },
  abandon_stats: { answered: 1, abandoned: 0, abandon_rate: 0, abandon_rate_limit: null },
  abandon_over_limit: false,
}

describe('stats tab with real API payload', () => {
  it('renders the result-distribution chart without throwing', () => {
    const items = mapResultDistributionItems('ivr', apiStats.result_distribution, 'zh').map(
      (item) => ({ label: item.label, value: item.count }),
    )
    expect(items).toHaveLength(2)
    expect(() =>
      renderToString(createElement(SimpleBarChart, { emptyLabel: 'empty', items })),
    ).not.toThrow()
  })

  it('renders the daily trend chart from daily_trend', () => {
    expect(() =>
      renderToString(
        createElement(DailyTrendBars, { emptyLabel: 'empty', items: apiStats.daily_trend }),
      ),
    ).not.toThrow()
  })
})
