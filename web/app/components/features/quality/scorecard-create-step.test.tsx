import { describe, expect, it } from 'vitest'

import { buildQualityScorecardCreatePayload } from '@/app/components/features/quality/scorecard-create-step'

describe('buildQualityScorecardCreatePayload', () => {
  it('creates a name-only payload for the initial step', () => {
    expect(buildQualityScorecardCreatePayload('  Support quality  ')).toEqual({
      name: 'Support quality',
    })
  })
})
