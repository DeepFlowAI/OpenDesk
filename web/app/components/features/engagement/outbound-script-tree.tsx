'use client'

import { IconAlertTriangle, IconChevronRight, IconGitBranch, IconMessage, IconRocket, IconSquareCheck } from '@tabler/icons-react'

import { cn } from '@/lib/utils'
import type { OutboundScript, OutboundScriptNodeType } from '@/models/outbound-task'
import { outboundScriptNodeMap } from './outbound-script-utils'

const iconByType = {
  start: IconRocket,
  script: IconMessage,
  branch: IconGitBranch,
  end: IconSquareCheck,
} satisfies Record<OutboundScriptNodeType, typeof IconRocket>

export function OutboundScriptTree({ script, selectedId, invalidNodeIds, onSelect }: {
  script: OutboundScript
  selectedId: string | null
  invalidNodeIds: Set<string>
  onSelect: (nodeId: string) => void
}) {
  const map = outboundScriptNodeMap(script)
  const start = script.nodes.find((node) => node.type === 'start')
  const renderNode = (nodeId: string, visited: Set<string>): React.ReactNode => {
    if (visited.has(nodeId)) return null
    const node = map.get(nodeId)
    if (!node) return null
    const Icon = iconByType[node.type]
    const nextVisited = new Set(visited).add(nodeId)
    return (
      <div key={node.id}>
        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className={cn('flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-muted', selectedId === node.id && 'bg-muted font-medium')}
        >
          <Icon size={15} className="shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate">{node.title || '未命名步骤'}</span>
          {invalidNodeIds.has(node.id) && <IconAlertTriangle size={14} className="shrink-0 text-destructive" />}
        </button>
        {node.type === 'branch' ? node.branches.map((branch) => (
          <div key={branch.id}>
            <div className="ml-4 flex items-center gap-1 py-1 text-xs text-muted-foreground">
              <IconChevronRight size={12} /> {branch.label || '未命名选项'}
            </div>
            {branch.next_node_id && <div className="ml-4">{renderNode(branch.next_node_id, nextVisited)}</div>}
          </div>
        )) : node.next_node_id ? <div className="ml-4">{renderNode(node.next_node_id, nextVisited)}</div> : null}
      </div>
    )
  }

  return <div className="p-2">{start ? renderNode(start.id, new Set()) : null}</div>
}
