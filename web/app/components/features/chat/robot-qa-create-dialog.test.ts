import { describe, expect, it } from 'vitest'

import type { RobotQaDirectory } from '@/models/robot-qa'

import {
  defaultRobotQaDirectoryId,
  filterRobotQaDirectories,
  robotQaDirectoryLabel,
} from './robot-qa-create-dialog'

const directories: RobotQaDirectory[] = [
  { id: 1, parent_id: null, name: '产品', sort_order: 0, depth: 1, path: ['产品'] },
  { id: 2, parent_id: 1, name: '登录', sort_order: 0, depth: 2, path: ['产品', '登录'] },
  { id: 3, parent_id: null, name: '未分类', sort_order: 1, depth: 1, path: ['未分类'] },
]

describe('robot QA directory picker', () => {
  it('defaults only to the top-level uncategorized directory', () => {
    expect(defaultRobotQaDirectoryId(directories)).toBe('3')
    expect(defaultRobotQaDirectoryId(directories.slice(0, 2))).toBe('')
    expect(defaultRobotQaDirectoryId([
      { ...directories[2], id: 4, parent_id: 1 },
    ])).toBe('')
  })

  it('filters by full directory path', () => {
    expect(filterRobotQaDirectories(directories, '产品 / 登录').map((item) => item.id)).toEqual([2])
  })

  it('uses the full directory path as the selected label', () => {
    expect(robotQaDirectoryLabel(directories[1])).toBe('产品 / 登录')
    expect(robotQaDirectoryLabel({ ...directories[0], path: [] })).toBe('产品')
  })
})
