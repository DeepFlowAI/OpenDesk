import { describe, expect, it } from 'vitest'

import type { OutboundScript } from '@/models/outbound-task'
import {
  addOutboundScriptChild,
  appendOutboundScriptHistory,
  createOutboundScript,
  deleteOutboundScriptSubtree,
  outboundScriptMaxDepth,
  validateOutboundScript,
} from './outbound-script-utils'

function completeScript(): OutboundScript {
  return {
    version: 1,
    nodes: [
      { id: 'start', type: 'start', title: '开始', next_node_id: 'branch', branches: [], position: { x: 0, y: 0 } },
      {
        id: 'branch',
        type: 'branch',
        title: '是否方便',
        content: '<p>现在方便吗？</p>',
        branches: [
          { id: 'yes', label: '方便', next_node_id: 'done' },
          { id: 'no', label: '不方便', next_node_id: 'callback' },
        ],
        position: { x: 200, y: 0 },
      },
      { id: 'done', type: 'end', title: '结束', branches: [], position: { x: 400, y: 0 } },
      { id: 'callback', type: 'end', title: '约定回拨', branches: [], position: { x: 400, y: 180 } },
    ],
  }
}

describe('outbound script utilities', () => {
  it('creates an unconfigured start node and reports its missing next step', () => {
    const script = createOutboundScript()

    expect(script.nodes).toHaveLength(1)
    expect(validateOutboundScript(script)[0]?.message).toContain('开始节点')
  })

  it('accepts a complete strict tree and calculates depth', () => {
    const script = completeScript()

    expect(validateOutboundScript(script)).toEqual([])
    expect(outboundScriptMaxDepth(script)).toBe(3)
  })

  it('adds a child to a branch option and deletes its subtree', () => {
    const script = completeScript()
    const withoutCallback = deleteOutboundScriptSubtree(script, 'callback')
    const result = addOutboundScriptChild(withoutCallback, 'branch', 'end', 'no')

    expect(result.script.nodes).toHaveLength(4)
    expect(result.script.nodes.find((node) => node.id === 'branch')?.branches[1].next_node_id).toBe(result.nodeId)
  })

  it('reports merged branches', () => {
    const script = completeScript()
    script.nodes[1].branches[1].next_node_id = 'done'

    expect(validateOutboundScript(script).some((issue) => issue.message.includes('汇聚'))).toBe(true)
  })

  it('appends branch node and target when jumping from the directory', () => {
    expect(appendOutboundScriptHistory(['first'], 'branch', 'done')).toEqual(['first', 'branch', 'done'])
  })

  it('does not duplicate the branch node when it is already the current step', () => {
    expect(appendOutboundScriptHistory(['first', 'branch'], 'branch', 'done')).toEqual(['first', 'branch', 'done'])
  })
})
