'use client'

import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  BaseEdge,
  EdgeLabelRenderer,
  ReactFlow,
  getSmoothStepPath,
  useOnViewportChange,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
} from '@xyflow/react'
import { IconGitBranch, IconPlus, IconRefresh } from '@tabler/icons-react'
import { bottomMergeId, layoutWorkflowWithElk, topMergeId, type WorkflowElkLayoutResult } from './elk-graph'
import { TICKET_WORKFLOW_NODE_TYPES } from './nodes'
import type { TicketWorkflowGraph } from '@/models/ticket-workflow-graph'

const BRANCH_IN_HANDLE_PREFIX = 'in-'

const BRANCH_STUB_HEIGHT = 48

export function branchIncomingHandleId(branchId: string): string {
  return `${BRANCH_IN_HANDLE_PREFIX}${branchId}`
}

export const BRANCH_MERGE_HANDLE_ID = '__merge__'
export const BRANCH_MERGE_IN_HANDLE_ID = '__merge_in__'

export type InsertNodeType = 'update_record' | 'branch'
export type InsertTarget =
  | { kind: 'edge'; edgeId: string }
  | { kind: 'branch_merge'; branchId: string; targetId: string }

type EdgeInsertContextValue = {
  onInsert: (target: InsertTarget, type: InsertNodeType) => void
} | null

const EdgeInsertContext = createContext<EdgeInsertContextValue>(null)

export function fromWorkflowGraph(
  graph: TicketWorkflowGraph,
  layoutResult: WorkflowElkLayoutResult,
): { nodes: Node[]; edges: Edge[] } {
  const { positions: layout, virtualPositions, joins, scopes, slots } = layoutResult
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]))
  const edgeStyle = { strokeWidth: 2, stroke: '#d4d4d4' }
  const bottomTrunksAdded = new Set<string>()
  const edges: Edge[] = []

  const addBottomTrunk = (branchId: string, targetId: string) => {
    const groupKey = `${branchId}::${targetId}`
    if (bottomTrunksAdded.has(groupKey)) return
    bottomTrunksAdded.add(groupKey)
    edges.push({
      id: `merge-trunk__${branchId}__${targetId}`,
      source: branchId,
      target: targetId,
      sourceHandle: BRANCH_MERGE_HANDLE_ID,
      type: 'branchBottomTrunk',
      animated: false,
      style: edgeStyle,
      data: {
        insertTarget: { kind: 'branch_merge', branchId, targetId } satisfies InsertTarget,
        bottomMerge: virtualPositions.get(bottomMergeId(branchId)),
      },
    })
  }

  for (const edge of graph.edges) {
    const targetNode = nodeById.get(edge.target)
    const sourceNode = nodeById.get(edge.source)

    if (targetNode?.type === 'branch') {
      const topMerge = virtualPositions.get(topMergeId(edge.target))
      edges.push({
        id: `${edge.id}__top_trunk`,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.source_handle,
        targetHandle: BRANCH_MERGE_IN_HANDLE_ID,
        type: 'branchTopTrunk',
        animated: false,
        style: edgeStyle,
        data: { logicalEdgeId: edge.id, topMerge },
      })
      targetNode.data.branches.forEach((branch) => {
        edges.push({
          id: `${edge.id}__top_fork__${branch.id}`,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.source_handle,
          targetHandle: branchIncomingHandleId(branch.id),
          type: 'branchTopFork',
          animated: false,
          style: edgeStyle,
          data: { topMerge },
        })
      })
      continue
    }

    if (sourceNode?.type === 'branch') {
      const joinId = joins.get(edge.source)
      const isDirectToJoin = joinId === edge.target
      edges.push({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.source_handle,
        type: 'branchPath',
        animated: false,
        style: edgeStyle,
        data: isDirectToJoin
          ? { logicalEdgeId: edge.id, bottomMerge: virtualPositions.get(bottomMergeId(edge.source)) }
          : { logicalEdgeId: edge.id },
      })
      if (isDirectToJoin) {
        addBottomTrunk(edge.source, edge.target)
      }
      continue
    }

    const enclosingBranchId = findEnclosingBranchForJoinEdge(edge, joins, scopes)
    if (enclosingBranchId) {
      edges.push({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.source_handle,
        type: 'branchPath',
        animated: false,
        style: edgeStyle,
        data: { logicalEdgeId: edge.id, bottomMerge: virtualPositions.get(bottomMergeId(enclosingBranchId)) },
      })
      addBottomTrunk(enclosingBranchId, edge.target)
      continue
    }

    edges.push({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.source_handle,
      type: 'insertable',
      animated: false,
      style: edgeStyle,
    })
  }

  return {
    nodes: graph.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: layout.get(node.id) ?? node.position,
      data: node.type === 'branch'
        ? { ...(node.data as Record<string, unknown>), columnSlots: slots.get(node.id) ?? null }
        : (node.data as Record<string, unknown>),
      draggable: false,
    })),
    edges,
  }
}

type AnchorPoint = { x: number; y: number }

function findEnclosingBranchForJoinEdge(
  edge: TicketWorkflowGraph['edges'][number],
  joins: Map<string, string>,
  scopes: Map<string, Set<string>>,
): string | null {
  let match: string | null = null
  let matchSize = Infinity
  joins.forEach((joinId, branchId) => {
    const scope = scopes.get(branchId)
    if (joinId !== edge.target || !scope?.has(edge.source)) return
    if (scope.size < matchSize) {
      match = branchId
      matchSize = scope.size
    }
  })
  return match
}

function branchTopTrunkGeometry(sourceX: number, sourceY: number, topMerge?: AnchorPoint) {
  const merge = topMerge ?? { x: sourceX, y: sourceY + BRANCH_STUB_HEIGHT }
  const path = Math.abs(sourceX - merge.x) < 1
    ? `M ${sourceX} ${sourceY} L ${merge.x} ${merge.y}`
    : `M ${sourceX} ${sourceY} L ${sourceX} ${merge.y} L ${merge.x} ${merge.y}`
  return {
    path,
    insertX: sourceX,
    insertY: sourceY + (merge.y - sourceY) / 2,
  }
}

function branchTopForkGeometry(targetX: number, targetY: number, topMerge?: AnchorPoint) {
  const merge = topMerge ?? { x: targetX, y: targetY - BRANCH_STUB_HEIGHT }
  const path = Math.abs(merge.x - targetX) < 1
    ? `M ${merge.x} ${merge.y} L ${targetX} ${targetY}`
    : `M ${merge.x} ${merge.y} L ${targetX} ${merge.y} L ${targetX} ${targetY}`
  return { path }
}

function branchPathGeometry(sourceX: number, sourceY: number, bottomMerge: AnchorPoint) {
  const path = Math.abs(sourceX - bottomMerge.x) < 1
    ? `M ${sourceX} ${sourceY} L ${bottomMerge.x} ${bottomMerge.y}`
    : `M ${sourceX} ${sourceY} L ${sourceX} ${bottomMerge.y} L ${bottomMerge.x} ${bottomMerge.y}`
  return {
    path,
    insertX: sourceX,
    insertY: sourceY + (bottomMerge.y - sourceY) / 2,
  }
}

function branchBottomTrunkGeometry(targetX: number, targetY: number, bottomMerge?: AnchorPoint) {
  const merge = bottomMerge ?? { x: targetX, y: targetY - BRANCH_STUB_HEIGHT }
  const path = Math.abs(merge.x - targetX) < 1
    ? `M ${merge.x} ${merge.y} L ${targetX} ${targetY}`
    : `M ${merge.x} ${merge.y} L ${merge.x} ${targetY} L ${targetX} ${targetY}`
  return {
    path,
    insertX: merge.x,
    insertY: merge.y + (targetY - merge.y) / 2,
  }
}

function InsertableEdge({
  id,
  data,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
}: EdgeProps) {
  const edgeData = data as { logicalEdgeId?: string; insertTarget?: InsertTarget; showInsert?: boolean } | undefined
  const insertTarget = edgeData?.insertTarget ?? { kind: 'edge', edgeId: edgeData?.logicalEdgeId ?? id } satisfies InsertTarget
  const showInsert = (data as { showInsert?: boolean } | undefined)?.showInsert !== false
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })
  const insert = useContext(EdgeInsertContext)

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {insert && showInsert && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute z-20"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`, pointerEvents: 'all' }}
          >
            <EdgeInsertButton target={insertTarget} onInsert={insert.onInsert} />
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

function BranchTopTrunkEdge({
  id,
  data,
  sourceX,
  sourceY,
  style,
  markerEnd,
}: EdgeProps) {
  const edgeData = data as { logicalEdgeId?: string; insertTarget?: InsertTarget; topMerge?: AnchorPoint } | undefined
  const insertTarget = edgeData?.insertTarget ?? { kind: 'edge', edgeId: edgeData?.logicalEdgeId ?? id } satisfies InsertTarget
  const { path, insertX, insertY } = branchTopTrunkGeometry(sourceX, sourceY, edgeData?.topMerge)
  const insert = useContext(EdgeInsertContext)

  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      {insert && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute z-20"
            style={{ transform: `translate(-50%, -50%) translate(${insertX}px, ${insertY}px)`, pointerEvents: 'all' }}
          >
            <EdgeInsertButton target={insertTarget} onInsert={insert.onInsert} />
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

function BranchTopForkEdge({
  id,
  data,
  targetX,
  targetY,
  style,
  markerEnd,
}: EdgeProps) {
  const edgeData = data as { topMerge?: AnchorPoint } | undefined
  const { path } = branchTopForkGeometry(targetX, targetY, edgeData?.topMerge)
  return <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
}

function BranchPathEdge({
  id,
  data,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
}: EdgeProps) {
  const edgeData = data as { logicalEdgeId?: string; insertTarget?: InsertTarget; bottomMerge?: AnchorPoint } | undefined
  const insertTarget = edgeData?.insertTarget ?? { kind: 'edge', edgeId: edgeData?.logicalEdgeId ?? id } satisfies InsertTarget
  const smooth = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })
  const pathResult = edgeData?.bottomMerge
    ? branchPathGeometry(sourceX, sourceY, edgeData.bottomMerge)
    : { path: smooth[0], insertX: smooth[1], insertY: smooth[2] }
  const insert = useContext(EdgeInsertContext)

  return (
    <>
      <BaseEdge id={id} path={pathResult.path} style={style} markerEnd={markerEnd} />
      {insert && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute z-20"
            style={{ transform: `translate(-50%, -50%) translate(${pathResult.insertX}px, ${pathResult.insertY}px)`, pointerEvents: 'all' }}
          >
            <EdgeInsertButton target={insertTarget} onInsert={insert.onInsert} />
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

function BranchBottomTrunkEdge({
  id,
  data,
  targetX,
  targetY,
  style,
  markerEnd,
}: EdgeProps) {
  const edgeData = data as { logicalEdgeId?: string; insertTarget?: InsertTarget; bottomMerge?: AnchorPoint } | undefined
  const insertTarget = edgeData?.insertTarget ?? { kind: 'edge', edgeId: edgeData?.logicalEdgeId ?? id } satisfies InsertTarget
  const { path, insertX, insertY } = branchBottomTrunkGeometry(targetX, targetY, edgeData?.bottomMerge)
  const insert = useContext(EdgeInsertContext)

  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      {insert && (
        <EdgeLabelRenderer>
          <div
            className="nodrag nopan absolute z-20"
            style={{ transform: `translate(-50%, -50%) translate(${insertX}px, ${insertY}px)`, pointerEvents: 'all' }}
          >
            <EdgeInsertButton target={insertTarget} onInsert={insert.onInsert} />
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

const INSERT_MENU_WIDTH = 112
const INSERT_MENU_HEIGHT = 72
const INSERT_MENU_GAP = 6

function EdgeInsertButton({
  target,
  onInsert,
}: {
  target: InsertTarget
  onInsert: (target: InsertTarget, type: InsertNodeType) => void
}) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [menuCoords, setMenuCoords] = useState<{ top: number; left: number } | null>(null)

  useLayoutEffect(() => {
    if (!open) {
      setMenuCoords(null)
      return
    }
    const updatePosition = () => {
      const el = buttonRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const spaceBelow = window.innerHeight - rect.bottom
      const openAbove = spaceBelow < INSERT_MENU_HEIGHT + INSERT_MENU_GAP && rect.top > INSERT_MENU_HEIGHT + INSERT_MENU_GAP
      const top = openAbove
        ? rect.top - INSERT_MENU_HEIGHT - INSERT_MENU_GAP
        : rect.bottom + INSERT_MENU_GAP
      const left = Math.max(
        8,
        Math.min(
          window.innerWidth - INSERT_MENU_WIDTH - 8,
          rect.left + rect.width / 2 - INSERT_MENU_WIDTH / 2,
        ),
      )
      setMenuCoords({ top, left })
    }
    updatePosition()
    window.addEventListener('scroll', updatePosition, true)
    window.addEventListener('resize', updatePosition)
    return () => {
      window.removeEventListener('scroll', updatePosition, true)
      window.removeEventListener('resize', updatePosition)
    }
  }, [open])

  const pick = (type: InsertNodeType) => {
    onInsert(target, type)
    setOpen(false)
  }

  const menuPortal = open && menuCoords && typeof document !== 'undefined'
    ? createPortal(
        <>
          <button
            type="button"
            className="fixed inset-0 z-[100] cursor-default bg-transparent"
            aria-label="关闭菜单"
            onClick={() => setOpen(false)}
          />
          <div
            className="fixed z-[101] w-28 overflow-hidden rounded-md border border-[#e5e5e5] bg-white py-1 shadow-lg"
            style={{ top: menuCoords.top, left: menuCoords.left }}
          >
            <button
              type="button"
              onClick={() => pick('update_record')}
              className="flex w-full items-center gap-2 px-3 py-2 text-xs text-[#333] hover:bg-[#f5f5f5]"
            >
              <IconRefresh size={14} />
              更新记录
            </button>
            <button
              type="button"
              onClick={() => pick('branch')}
              className="flex w-full items-center gap-2 px-3 py-2 text-xs text-[#333] hover:bg-[#f5f5f5]"
            >
              <IconGitBranch size={14} />
              分支
            </button>
          </div>
        </>,
        document.body,
      )
    : null

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onPointerDown={(event) => event.stopPropagation()}
        onMouseDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation()
          setOpen((prev) => !prev)
        }}
        className="flex h-6 w-6 items-center justify-center rounded-full border border-[#d9d9d9] bg-white text-[#666] shadow-sm transition hover:border-[#1a1a1a] hover:text-[#1a1a1a]"
        aria-label="在此处添加节点"
      >
        <IconPlus size={14} />
      </button>
      {menuPortal}
    </div>
  )
}

const TICKET_WORKFLOW_EDGE_TYPES = {
  insertable: InsertableEdge,
  branchTopTrunk: BranchTopTrunkEdge,
  branchTopFork: BranchTopForkEdge,
  branchPath: BranchPathEdge,
  branchBottomTrunk: BranchBottomTrunkEdge,
}

function CanvasAutoFit() {
  const { fitView } = useReactFlow()
  const hasFit = useRef(false)

  useLayoutEffect(() => {
    if (hasFit.current) return
    hasFit.current = true
    const frame = requestAnimationFrame(() => {
      fitView({ padding: 0.28, duration: 0, maxZoom: 1 })
    })
    return () => cancelAnimationFrame(frame)
  }, [fitView])

  return null
}

function CanvasZoomControls() {
  const { fitView, zoomIn, zoomOut, zoomTo } = useReactFlow()
  const [zoom, setZoom] = useState(1)

  useOnViewportChange({
    onChange: ({ zoom: nextZoom }) => setZoom(nextZoom),
  })

  return (
    <div className="nodrag nopan absolute bottom-5 left-5 z-10 flex overflow-hidden rounded-lg border border-[#d9d9d9] bg-white shadow-sm">
      <button
        type="button"
        onClick={() => zoomOut({ duration: 160 })}
        className="flex h-9 w-10 items-center justify-center border-r border-[#e5e5e5] text-lg leading-none text-[#333] hover:bg-[#f7f7f7]"
        aria-label="缩小画布"
      >
        -
      </button>
      <button
        type="button"
        onClick={() => zoomTo(1, { duration: 160 })}
        className="flex h-9 min-w-14 items-center justify-center border-r border-[#e5e5e5] px-3 text-xs font-medium text-[#333] hover:bg-[#f7f7f7]"
        aria-label="恢复 100% 显示"
      >
        {Math.round(zoom * 100)}%
      </button>
      <button
        type="button"
        onClick={() => zoomIn({ duration: 160 })}
        className="flex h-9 w-10 items-center justify-center border-r border-[#e5e5e5] text-lg leading-none text-[#333] hover:bg-[#f7f7f7]"
        aria-label="放大画布"
      >
        +
      </button>
      <button
        type="button"
        onClick={() => fitView({ padding: 0.28, duration: 180 })}
        className="flex h-9 items-center justify-center px-3 text-xs font-medium text-[#333] hover:bg-[#f7f7f7]"
      >
        适配
      </button>
    </div>
  )
}

export function TicketWorkflowCanvas({
  graph,
  selectedNodeId,
  onSelect,
  onInsertNode,
  onAddBranch,
  onRemoveBranch,
  onDeleteNode,
}: {
  graph: TicketWorkflowGraph
  selectedNodeId: string | null
  onSelect: (id: string | null, branchId?: string | null) => void
  onInsertNode?: (target: InsertTarget, type: InsertNodeType) => void
  onAddBranch?: (nodeId: string) => void
  onRemoveBranch?: (nodeId: string, branchId: string) => void
  onDeleteNode?: (nodeId: string) => void
}) {
  const [layoutResult, setLayoutResult] = useState<WorkflowElkLayoutResult | null>(null)

  useEffect(() => {
    let cancelled = false
    setLayoutResult(null)
    layoutWorkflowWithElk(graph).then((nextLayout) => {
      if (!cancelled) setLayoutResult(nextLayout)
    })
    return () => {
      cancelled = true
    }
  }, [graph])

  const { nodes, edges } = useMemo(
    () => layoutResult ? fromWorkflowGraph(graph, layoutResult) : { nodes: [], edges: [] },
    [graph, layoutResult],
  )
  const decorated = useMemo(
    () => nodes.map((node) => ({
      ...node,
      selected: node.id === selectedNodeId,
      data: {
        ...node.data,
        onEditNode: () => onSelect(node.id),
        onEditBranch: node.type === 'branch' ? (branchId: string) => onSelect(node.id, branchId) : undefined,
        onDeleteNode: onDeleteNode && node.type !== 'trigger' && node.type !== 'end'
          ? () => onDeleteNode(node.id)
          : undefined,
        onAddBranch: node.type === 'branch' && onAddBranch ? () => onAddBranch(node.id) : undefined,
        onRemoveBranch: node.type === 'branch' && onRemoveBranch
          ? (branchId: string) => onRemoveBranch(node.id, branchId)
          : undefined,
      },
    })),
    [nodes, selectedNodeId, onSelect, onAddBranch, onRemoveBranch, onDeleteNode],
  )
  const insertContext = useMemo<EdgeInsertContextValue>(
    () => (onInsertNode ? { onInsert: onInsertNode } : null),
    [onInsertNode],
  )

  return (
    <EdgeInsertContext.Provider value={insertContext}>
      <ReactFlow
        nodes={decorated}
        edges={edges}
        className="bg-[#f4f4f5]"
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_event, node) => onSelect(node.id)}
        onPaneClick={() => onSelect(null)}
        nodeTypes={TICKET_WORKFLOW_NODE_TYPES}
        edgeTypes={TICKET_WORKFLOW_EDGE_TYPES}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        {layoutResult && <CanvasAutoFit />}
        <CanvasZoomControls />
      </ReactFlow>
    </EdgeInsertContext.Provider>
  )
}
