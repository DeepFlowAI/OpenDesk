'use client'
/**
 * Main ReactFlow canvas wrapper for the voice flow editor.
 *
 * Maintains React state for nodes + edges and a `selectedNodeId`. Provides
 * helpers (updateNode, addNode) that the property panel + toolbar drive.
 *
 * Maps to / from the backend `graph_json` protocol via `fromBackend`/`toBackend`.
 */
import { useCallback, useMemo } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  addEdge,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from '@xyflow/react'

import { NODE_DRAG_MIME } from './node-toolbar'
import { NODE_TYPES } from './nodes'
import {
  COLLECT_OUTLET_COLOR,
  NODE_COLOR,
  defaultDataFor,
  genEdgeId,
  genNodeId,
  type FlowEdge,
  type FlowNode,
  type NodeType,
  type VoiceFlowGraph,
} from '@/models/voice-flow-graph'

// ──────────────── Conversion helpers (backend ↔ ReactFlow) ────────────────

export function fromBackend(graph: VoiceFlowGraph): { nodes: Node[]; edges: Edge[] } {
  const nodes = graph.nodes.map<Node>((n) => ({
    id: n.id,
    type: n.type,
    position: n.position,
    data: n.data as Record<string, unknown>,
    draggable: n.type !== 'start',
  }))
  const edges = graph.edges.map<Edge>((e) => {
    const src = graph.nodes.find((n) => n.id === e.source)
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_handle,
      type: 'smoothstep',
      style: { stroke: edgeColor(src?.type ?? null, e.source_handle), strokeWidth: 2 },
    }
  })
  return { nodes, edges }
}

export function toBackend(nodes: Node[], edges: Edge[]): VoiceFlowGraph {
  return {
    version: 1,
    nodes: nodes.map<FlowNode>((n) => ({
      id: n.id,
      type: n.type as NodeType,
      position: n.position,
      // ReactFlow's Node `data` is `Record<string, unknown>`; we kept the
      // discriminated-union-shaped object intact, so cast back to FlowNode['data'].
      data: n.data as unknown as FlowNode['data'],
    } as FlowNode)),
    edges: edges.map<FlowEdge>((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      source_handle: e.sourceHandle ?? 'next',
    })),
    variables: collectVariables(nodes),
  }
}

function collectVariables(nodes: Node[]): VoiceFlowGraph['variables'] {
  return nodes
    .filter((n) => n.type === 'collect')
    .map((n) => ({
      name: (n.data as { output_variable?: string }).output_variable ?? '',
      source_node_id: n.id,
    }))
    .filter((v) => v.name)
}

function edgeColor(srcType: string | null, handle: string): string {
  if (srcType === 'collect') return COLLECT_OUTLET_COLOR[handle] ?? '#9CA3AF'
  if (srcType === 'condition') {
    return handle === 'default' ? '#9CA3AF' : NODE_COLOR.condition
  }
  if (!srcType) return '#9CA3AF'
  return NODE_COLOR[srcType as NodeType] ?? '#9CA3AF'
}

// ──────────────── Canvas component ────────────────

export function VoiceFlowCanvas({
  nodes,
  edges,
  setNodes,
  setEdges,
  selectedNodeId,
  onSelect,
  onDropNode,
}: {
  nodes: Node[]
  edges: Edge[]
  setNodes: (n: Node[] | ((prev: Node[]) => Node[])) => void
  setEdges: (e: Edge[] | ((prev: Edge[]) => Edge[])) => void
  selectedNodeId: string | null
  onSelect: (id: string | null) => void
  onDropNode?: (type: NodeType, position: { x: number; y: number }) => void
}) {
  const { screenToFlowPosition } = useReactFlow()
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [setNodes],
  )
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [setEdges],
  )
  const onConnect = useCallback(
    (conn: Connection) => {
      setEdges((eds) => {
        const src = nodes.find((n) => n.id === conn.source)
        const next: Edge = {
          id: genEdgeId(),
          source: conn.source ?? '',
          target: conn.target ?? '',
          sourceHandle: conn.sourceHandle ?? 'next',
          type: 'smoothstep',
          style: {
            stroke: edgeColor(src?.type ?? null, conn.sourceHandle ?? 'next'),
            strokeWidth: 2,
          },
        }
        // Replace any existing edge from same (source, sourceHandle) — only one
        // outgoing connection per outlet.
        const filtered = eds.filter(
          (e) => !(e.source === next.source && (e.sourceHandle ?? 'next') === next.sourceHandle),
        )
        return addEdge(next, filtered)
      })
    },
    [nodes, setEdges],
  )

  const onDragOver = useCallback((event: React.DragEvent) => {
    if (!event.dataTransfer.types.includes(NODE_DRAG_MIME)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      const type = event.dataTransfer.getData(NODE_DRAG_MIME) as NodeType
      if (!type || !onDropNode) return
      event.preventDefault()
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      onDropNode(type, position)
    },
    [onDropNode, screenToFlowPosition],
  )

  // Inject `selected` prop into node data so custom views can react.
  const decoratedNodes = useMemo(
    () => nodes.map((n) => ({ ...n, selected: n.id === selectedNodeId })),
    [nodes, selectedNodeId],
  )

  return (
    <ReactFlow
      nodes={decoratedNodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onNodeClick={(_e, node) => onSelect(node.id)}
      onPaneClick={() => onSelect(null)}
      onDragOver={onDragOver}
      onDrop={onDrop}
      nodeTypes={NODE_TYPES}
      fitView
      proOptions={{ hideAttribution: true }}
      defaultEdgeOptions={{ type: 'smoothstep' }}
    >
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
      <Controls position="bottom-left" />
    </ReactFlow>
  )
}

// ──────────────── New-node placement helper ────────────────

export function makeNewNode(type: NodeType, position?: { x: number; y: number }): Node {
  // Exact `position` when supplied (drag-drop). Otherwise jittered default
  // (click-add) so successive clicks don't stack on the same pixel.
  const pos = position ?? { x: 200 + Math.random() * 60, y: 200 + Math.random() * 60 }
  return {
    id: genNodeId(),
    type,
    position: pos,
    data: defaultDataFor(type) as Record<string, unknown>,
  }
}
