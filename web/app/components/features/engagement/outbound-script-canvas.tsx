'use client'

import { useEffect, useMemo } from 'react'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { IconCheck, IconGitBranch, IconMessage, IconRocket } from '@tabler/icons-react'

import { cn } from '@/lib/utils'
import type { OutboundScript, OutboundScriptNode, OutboundScriptNodeType } from '@/models/outbound-task'
import { outboundScriptChildren, outboundScriptNodeLabel } from './outbound-script-utils'

type ScriptCanvasNodeData = { scriptNode: OutboundScriptNode; invalid: boolean }
type ScriptCanvasNode = Node<ScriptCanvasNodeData, 'scriptNode'>

const iconByType = {
  start: IconRocket,
  script: IconMessage,
  branch: IconGitBranch,
  end: IconCheck,
} satisfies Record<OutboundScriptNodeType, typeof IconRocket>

export function OutboundScriptCanvas({
  script,
  selectedId,
  invalidNodeIds = new Set<string>(),
  readOnly = false,
  fitRequest = 0,
  onSelect,
  onPositionChange,
}: {
  script: OutboundScript
  selectedId: string | null
  invalidNodeIds?: Set<string>
  readOnly?: boolean
  fitRequest?: number
  onSelect: (nodeId: string) => void
  onPositionChange?: (nodeId: string, position: { x: number; y: number }) => void
}) {
  return (
    <ReactFlowProvider>
      <CanvasBody
        script={script}
        selectedId={selectedId}
        invalidNodeIds={invalidNodeIds}
        readOnly={readOnly}
        fitRequest={fitRequest}
        onSelect={onSelect}
        onPositionChange={onPositionChange}
      />
    </ReactFlowProvider>
  )
}

function CanvasBody({ script, selectedId, invalidNodeIds, readOnly, fitRequest, onSelect, onPositionChange }: {
  script: OutboundScript
  selectedId: string | null
  invalidNodeIds: Set<string>
  readOnly: boolean
  fitRequest: number
  onSelect: (nodeId: string) => void
  onPositionChange?: (nodeId: string, position: { x: number; y: number }) => void
}) {
  const flow = useReactFlow()
  const nodes = useMemo<ScriptCanvasNode[]>(() => script.nodes.map((scriptNode) => ({
    id: scriptNode.id,
    type: 'scriptNode',
    position: scriptNode.position,
    selected: scriptNode.id === selectedId,
    data: { scriptNode, invalid: invalidNodeIds.has(scriptNode.id) },
  })), [invalidNodeIds, script.nodes, selectedId])
  const edges = useMemo<Edge[]>(() => script.nodes.flatMap((node) => {
    if (node.type === 'branch') {
      return node.branches.filter((branch) => branch.next_node_id).map((branch) => ({
        id: `${node.id}-${branch.id}`,
        source: node.id,
        target: branch.next_node_id,
        label: branch.label,
        markerEnd: { type: MarkerType.ArrowClosed },
      }))
    }
    return outboundScriptChildren(node).map((target) => ({
      id: `${node.id}-${target}`,
      source: node.id,
      target,
      markerEnd: { type: MarkerType.ArrowClosed },
    }))
  }), [script.nodes])

  useEffect(() => {
    if (fitRequest > 0) void flow.fitView({ padding: 0.2, duration: 250 })
  }, [fitRequest, flow])

  return (
    <ReactFlow<ScriptCanvasNode, Edge>
      nodes={nodes}
      edges={edges}
      nodeTypes={{ scriptNode: ScriptNodeCard }}
      nodesDraggable={!readOnly}
      nodesConnectable={false}
      elementsSelectable
      fitView
      minZoom={0.35}
      maxZoom={1.5}
      onNodeClick={(_, node) => onSelect(node.id)}
      onNodeDragStop={(_, node) => onPositionChange?.(node.id, node.position)}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={20} size={1} />
      <Controls showInteractive={false} />
    </ReactFlow>
  )
}

function ScriptNodeCard({ data, selected }: NodeProps<ScriptCanvasNode>) {
  const { scriptNode, invalid } = data
  const Icon = iconByType[scriptNode.type]
  return (
    <div className={cn(
      'w-48 rounded-lg border bg-background px-3 py-3 shadow-sm',
      selected ? 'border-foreground ring-1 ring-foreground' : 'border-border',
      invalid && 'border-destructive ring-1 ring-destructive/30',
    )}>
      {scriptNode.type !== 'start' && <Handle type="target" position={Position.Left} isConnectable={false} />}
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          <Icon size={12} /> {outboundScriptNodeLabel(scriptNode.type)}
        </span>
        {scriptNode.type === 'branch' && <span className="text-[10px] text-muted-foreground">{scriptNode.branches.length} 个分支</span>}
      </div>
      <p className="mt-2 truncate text-sm font-semibold">{scriptNode.title || '未命名步骤'}</p>
      {scriptNode.type !== 'end' && <Handle type="source" position={Position.Right} isConnectable={false} />}
    </div>
  )
}
