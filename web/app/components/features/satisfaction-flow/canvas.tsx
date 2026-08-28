'use client'

import { useCallback, useMemo } from 'react'
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react'
import { toast } from 'sonner'
import type { SatisfactionFlowGraph, SatisfactionNode } from '@/models/satisfaction-flow'
import { SATISFACTION_NODE_MIME } from '@/app/components/features/satisfaction-flow/toolbar'
import { SATISFACTION_NODE_COLOR, SATISFACTION_NODE_TYPES } from '@/app/components/features/satisfaction-flow/nodes'
import { COLLECT_OUTLET_COLOR } from '@/models/voice-flow-graph'

export function satisfactionEdgeStyle(sourceType: string | undefined, handle: string | null | undefined) {
  const outlet = handle ?? 'next'
  const stroke = sourceType === 'question'
    ? COLLECT_OUTLET_COLOR[outlet] ?? SATISFACTION_NODE_COLOR.question
    : sourceType === 'condition' && outlet === 'default'
      ? '#9CA3AF'
      : SATISFACTION_NODE_COLOR[sourceType as SatisfactionNode['type']] ?? '#9CA3AF'
  return { stroke, strokeWidth: 2 }
}

export function satisfactionFromBackend(graph: SatisfactionFlowGraph): { nodes: Node[]; edges: Edge[] } {
  return {
    nodes: graph.nodes.map((node) => ({ ...node, data: node.data, draggable: node.type !== 'start' })),
    edges: graph.edges.map((edge) => {
      const source = graph.nodes.find((node) => node.id === edge.source)
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.source_handle,
        type: 'smoothstep',
        style: satisfactionEdgeStyle(source?.type, edge.source_handle),
      }
    }),
  }
}

export function satisfactionToBackend(nodes: Node[], edges: Edge[]): SatisfactionFlowGraph {
  return {
    version: 1,
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type as SatisfactionNode['type'],
      position: node.position,
      data: node.data,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_handle: edge.sourceHandle ?? 'next',
    })),
  }
}

export function SatisfactionCanvas({
  nodes,
  edges,
  setNodes,
  setEdges,
  selectedId,
  onSelect,
  onDropNode,
}: {
  nodes: Node[]
  edges: Edge[]
  setNodes: (value: Node[] | ((nodes: Node[]) => Node[])) => void
  setEdges: (value: Edge[] | ((edges: Edge[]) => Edge[])) => void
  selectedId: string | null
  onSelect: (id: string | null) => void
  onDropNode: (type: SatisfactionNode['type'], position: { x: number; y: number }) => void
}) {
  const { screenToFlowPosition } = useReactFlow()
  const decorated = useMemo(() => nodes.map((node) => {
    const selected = node.id === selectedId
    return node.selected === selected ? node : { ...node, selected }
  }), [nodes, selectedId])
  const onConnect = useCallback((connection: Connection) => {
    const source = nodes.find((node) => node.id === connection.source)
    const target = nodes.find((node) => node.id === connection.target)
    if (source?.type === 'end' || target?.type === 'start') {
      toast.error('开始节点不能有入口，结束节点不能有出口')
      return
    }
    setEdges((current) => {
      const filtered = current.filter((edge) => !(edge.source === connection.source && (edge.sourceHandle ?? 'next') === (connection.sourceHandle ?? 'next')))
      return addEdge({
        ...connection,
        id: `edge_${crypto.randomUUID()}`,
        type: 'smoothstep',
        style: satisfactionEdgeStyle(source?.type, connection.sourceHandle),
      }, filtered)
    })
  }, [nodes, setEdges])

  return (
    <ReactFlow
      nodes={decorated}
      edges={edges}
      nodeTypes={SATISFACTION_NODE_TYPES}
      onNodesChange={(changes: NodeChange[]) => setNodes((current) => applyNodeChanges(changes, current))}
      onEdgesChange={(changes: EdgeChange[]) => setEdges((current) => applyEdgeChanges(changes, current))}
      onConnect={onConnect}
      onNodeClick={(_event, node) => onSelect(node.id)}
      onPaneClick={() => onSelect(null)}
      onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy' }}
      onDrop={(event) => {
        event.preventDefault()
        const type = event.dataTransfer.getData(SATISFACTION_NODE_MIME) as SatisfactionNode['type']
        if (type) onDropNode(type, screenToFlowPosition({ x: event.clientX, y: event.clientY }))
      }}
      fitView
      deleteKeyCode={['Backspace', 'Delete']}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      <Controls position="bottom-left" />
    </ReactFlow>
  )
}
