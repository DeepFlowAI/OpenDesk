import { describe, expect, it } from 'vitest'

import {
  resolvePreferredOutboundNumber,
  workspaceCallOutboundNumberId,
} from '@/lib/call-outbound-number'

describe('workspaceCallOutboundNumberId', () => {
  it('reads a non-empty outbound number id', () => {
    expect(
      workspaceCallOutboundNumberId({
        workspace_call: { outbound_number_id: 'pn-2' },
      }),
    ).toBe('pn-2')
  })

  it('ignores missing or blank values', () => {
    expect(workspaceCallOutboundNumberId(undefined)).toBeUndefined()
    expect(workspaceCallOutboundNumberId({})).toBeUndefined()
    expect(
      workspaceCallOutboundNumberId({
        workspace_call: { outbound_number_id: '   ' },
      }),
    ).toBeUndefined()
  })
})

describe('resolvePreferredOutboundNumber', () => {
  const numbers = [{ id: 'pn-1' }, { id: 'pn-2' }, { id: 'pn-3' }]

  it('returns the preferred number when it is still in the list', () => {
    expect(resolvePreferredOutboundNumber(numbers, 'pn-2')?.id).toBe('pn-2')
  })

  it('falls back to the first number when the preferred id is missing or stale', () => {
    expect(resolvePreferredOutboundNumber(numbers)?.id).toBe('pn-1')
    expect(resolvePreferredOutboundNumber(numbers, 'gone')?.id).toBe('pn-1')
  })

  it('returns undefined when the list is empty', () => {
    expect(resolvePreferredOutboundNumber([], 'pn-2')).toBeUndefined()
  })
})
