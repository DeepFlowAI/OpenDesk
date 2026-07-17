import { describe, expect, it } from 'vitest'

import {
  buildH5TicketDetailUrl,
  buildH5TicketListUrl,
  buildH5TicketNewUrl,
  readH5TicketListContext,
} from '@/lib/h5-ticket-navigation'

describe('H5 ticket navigation', () => {
  it('normalizes list context from URL params', () => {
    const params = new URLSearchParams('view=12&page=3&q=login&group=open')

    expect(readH5TicketListContext(params)).toEqual({
      view: '12',
      page: 3,
      q: 'login',
      group: 'open',
    })
  })

  it('omits default list values', () => {
    expect(buildH5TicketListUrl({ view: 'all', page: 1 })).toBe('/h5/tickets')
  })

  it('preserves list context through new and detail routes', () => {
    const context = { view: '5', page: 2, q: 'refund', group: 'pending' }

    expect(buildH5TicketNewUrl(context)).toBe(
      '/h5/tickets/new?view=5&page=2&q=refund&group=pending',
    )
    expect(buildH5TicketDetailUrl(42, context)).toBe(
      '/h5/tickets/42?view=5&page=2&q=refund&group=pending&from=list',
    )
  })
})
