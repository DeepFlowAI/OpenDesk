import { describe, expect, it } from 'vitest'

import type { RobotQaKnowledgeBase } from '@/models/robot-qa'
import {
  filterRobotQaKnowledgeBases,
  isRobotQaTargetInvalid,
} from '@/app/components/features/conversation-settings/robot-qa-setting-section'


const items: RobotQaKnowledgeBase[] = [
  { id: 1, name: 'Support', description: 'Customer help', status: 'active' },
  { id: 2, name: '销售', description: null, status: 'active' },
]

describe('robot QA setting helpers', () => {
  it('filters candidates by name and description', () => {
    expect(filterRobotQaKnowledgeBases(items, 'help').map((item) => item.id)).toEqual([1])
    expect(filterRobotQaKnowledgeBases(items, '销售').map((item) => item.id)).toEqual([2])
  })

  it('marks only a missing saved target as invalid', () => {
    expect(isRobotQaTargetInvalid(null, items)).toBe(false)
    expect(isRobotQaTargetInvalid(1, items)).toBe(false)
    expect(isRobotQaTargetInvalid(9, items)).toBe(true)
  })
})
