import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  useQuery: vi.fn(),
}))

vi.mock('@tanstack/react-query', () => ({
  useMutation: vi.fn(),
  useQuery: mocks.useQuery,
  useQueryClient: vi.fn(),
}))

import { usePersonalAutoOutboundConfig } from './use-personal-auto-outbound'

describe('usePersonalAutoOutboundConfig', () => {
  beforeEach(() => {
    mocks.useQuery.mockReset()
  })

  it('refetches the configuration whenever the personal auto outbound view is entered', () => {
    usePersonalAutoOutboundConfig()

    expect(mocks.useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: ['personal-auto-outbound', 'config'],
        refetchOnMount: 'always',
      }),
    )
  })
})
