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
  readOnly = false,
}: {
  nodes: Node[]
  edges: Edge[]
  setNodes: (n: Node[] | ((prev: Node[]) => Node[])) => void
  setEdges: (e: Edge[] | ((prev: Edge[]) => Edge[])) => void
  selectedNodeId: string | null
  onSelect: (id: string | null) => void
  onDropNode?: (type: NodeType, position: { x: number; y: number }) => void
  readOnly?: boolean
}) {
  const { screenToFlowPosition } = useReactFlow()
  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      if (readOnly) {
        // Keep select/dimensions so preview can focus nodes; block moves/removes.
        const filtered = changes.filter((c) => c.type === 'select' || c.type === 'dimensions')
        if (!filtered.length) return
        setNodes((nds) => applyNodeChanges(filtered, nds))
        return
      }
      setNodes((nds) => applyNodeChanges(changes, nds))
    },
    [readOnly, setNodes],
  )
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      if (readOnly) return
      setEdges((eds) => applyEdgeChanges(changes, eds))
    },
    [readOnly, setEdges],
  )
  const onConnect = useCallback(
    (conn: Connection) => {
      if (readOnly) return
      const src = nodes.find((n) => n.id === conn.source)
      const tgt = nodes.find((n) => n.id === conn.target)
      const handle = conn.sourceHandle ?? 'next'
      // VoiceSpeed handoff must go to human routing, not announcement nodes.
      if (
        src?.type === 'voicespeed' &&
        handle === 'handoff' &&
        (tgt?.type === 'play' || tgt?.type === 'collect' || tgt?.type === 'condition' || tgt?.type === 'start')
      ) {
        return
      }
      setEdges((eds) => {
        const next: Edge = {
          id: genEdgeId(),
          source: conn.source ?? '',
          target: conn.target ?? '',
          sourceHandle: handle,
          type: 'smoothstep',
          style: {
            stroke: edgeColor(src?.type ?? null, handle),
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
    [nodes, readOnly, setEdges],
  )

  const onDragOver = useCallback((event: React.DragEvent) => {
    if (readOnly) return
    if (!event.dataTransfer.types.includes(NODE_DRAG_MIME)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [readOnly])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      if (readOnly || !onDropNode) return
      const type = event.dataTransfer.getData(NODE_DRAG_MIME) as NodeType
      if (!type) return
      event.preventDefault()
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
      onDropNode(type, position)
    },
    [onDropNode, readOnly, screenToFlowPosition],
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
      nodesDraggable={!readOnly}
      nodesConnectable={!readOnly}
      elementsSelectable
      edgesReconnectable={!readOnly}
      deleteKeyCode={readOnly ? null : ['Backspace', 'Delete']}
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
