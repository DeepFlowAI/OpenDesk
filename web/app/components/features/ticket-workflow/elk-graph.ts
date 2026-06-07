import type {
  ELK as ElkInstance,
  ElkNode as ElkLayoutNode,
  LayoutOptions,
} from 'elkjs/lib/elk.bundled.js'
import {
  BRANCH_CHIP_WIDTH,
  BRANCH_GAP_X,
  BRANCH_PADDING_X,
  branchColumnsCenterX,
  branchNodeWidth,
} from './branch-geometry'
import type { TicketWorkflowGraph, TicketWorkflowNode } from '@/models/ticket-workflow-graph'

const NODE_WIDTH = 280
const NODE_HEIGHT = 116
const END_NODE_WIDTH = 96
const END_NODE_HEIGHT = 64
const BRANCH_NODE_HEIGHT = 122
const PORT_SIZE = 8

export type ElkPortSide = 'NORTH' | 'SOUTH'

export type ElkLayoutOptions = LayoutOptions

export type ElkPort = {
  id: string
  width: number
  height: number
  x?: number
  y?: number
  layoutOptions?: ElkLayoutOptions
}

export type ElkNode = {
  id: string
  width: number
  height: number
  ports?: ElkPort[]
  layoutOptions?: ElkLayoutOptions
}

export type ElkEdge = {
  id: string
  sources: string[]
  targets: string[]
  layoutOptions?: ElkLayoutOptions
}

export type ElkGraph = {
  id: string
  layoutOptions: ElkLayoutOptions
  children: ElkNode[]
  edges: ElkEdge[]
}

export type WorkflowElkLayoutResult = {
  positions: Map<string, { x: number; y: number }>
  virtualPositions: Map<string, { x: number; y: number }>
  joins: Map<string, string>
  scopes: Map<string, Set<string>>
  slots: Map<string, number[]>
}

let elkInstance: ElkInstance | null = null

export async function layoutWorkflowWithElk(graph: TicketWorkflowGraph): Promise<WorkflowElkLayoutResult> {
  const elk = await getElk()
  const branchLayout = analyzeBranches(graph)
  const laidOut = await elk.layout(toElkGraph(graph, branchLayout) as ElkLayoutNode)
  const positions = new Map<string, { x: number; y: number }>()
  const virtualPositions = new Map<string, { x: number; y: number }>()
  const slots = new Map<string, number[]>()

  laidOut.children?.forEach((node) => {
    const position = { x: node.x ?? 0, y: node.y ?? 0 }
    if (isVirtualMergeNodeId(node.id)) {
      virtualPositions.set(node.id, {
        x: position.x + (node.width ?? 0) / 2,
        y: position.y + (node.height ?? 0) / 2,
      })
      return
    }
    positions.set(node.id, position)
  })

  graph.nodes.forEach((node) => {
    if (node.type === 'branch') {
      slots.set(node.id, node.data.branches.map(() => BRANCH_CHIP_WIDTH))
    }
  })

  return {
    positions,
    virtualPositions,
    slots,
    joins: branchLayout.joins,
    scopes: branchLayout.scopes,
  }
}

async function getElk(): Promise<ElkInstance> {
  if (elkInstance) return elkInstance
  const { default: ELK } = await import('elkjs/lib/elk.bundled.js')
  elkInstance = new ELK()
  return elkInstance
}

export function toElkGraph(graph: TicketWorkflowGraph, branchLayout = analyzeBranches(graph)): ElkGraph {
  return {
    id: 'ticket-workflow',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'DOWN',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': '96',
      'elk.spacing.nodeNode': '80',
      'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    },
    children: [
      ...graph.nodes.map(toElkNode),
      ...graph.nodes
        .filter((node) => node.type === 'branch')
        .flatMap((node) => [
          virtualMergeNode(topMergeId(node.id)),
          ...(branchLayout.joins.has(node.id) ? [virtualMergeNode(bottomMergeId(node.id))] : []),
        ]),
    ],
    edges: toElkEdges(graph, branchLayout),
  }
}

function toElkNode(node: TicketWorkflowNode): ElkNode {
  const size = nodeSize(node)
  const ports = nodePorts(node, size)
  return {
    id: node.id,
    width: size.width,
    height: size.height,
    ...(ports.length ? { ports } : {}),
    layoutOptions: {
      'elk.portConstraints': 'FIXED_POS',
    },
  }
}

function nodePorts(node: TicketWorkflowNode, size: { width: number; height: number }): ElkPort[] {
  if (node.type === 'trigger') {
    return [port(sourcePortId(node.id, 'next'), 'SOUTH', size.width / 2, size.height)]
  }

  if (node.type === 'update_record') {
    return [
      port(targetPortId(node.id), 'NORTH', size.width / 2, 0),
      port(sourcePortId(node.id, 'next'), 'SOUTH', size.width / 2, size.height),
    ]
  }

  if (node.type === 'end') {
    return [port(targetPortId(node.id), 'NORTH', size.width / 2, 0)]
  }

  return [
    port(targetPortId(node.id), 'NORTH', branchColumnsCenterX(node.data.branches.length), 0),
    ...node.data.branches.map((branch, index) => {
      const centerX = BRANCH_PADDING_X + index * (BRANCH_CHIP_WIDTH + BRANCH_GAP_X) + BRANCH_CHIP_WIDTH / 2
      return port(sourcePortId(node.id, branch.id), 'SOUTH', centerX, size.height)
    }),
  ]
}

function virtualMergeNode(id: string): ElkNode {
  return {
    id,
    width: PORT_SIZE,
    height: PORT_SIZE,
  }
}

function toElkEdges(graph: TicketWorkflowGraph, branchLayout: BranchLayout): ElkEdge[] {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]))
  const edges: ElkEdge[] = []
  const bottomTrunksAdded = new Set<string>()

  const addBottomTrunk = (branchId: string, joinId: string) => {
    const key = `${branchId}::${joinId}`
    if (bottomTrunksAdded.has(key)) return
    bottomTrunksAdded.add(key)
    edges.push({
      id: `layout-bottom-trunk__${branchId}__${joinId}`,
      sources: [bottomMergeId(branchId)],
      targets: [targetNodeOrTopMerge(joinId, byId)],
    })
  }

  graph.edges.forEach((edge) => {
    const sourceNode = byId.get(edge.source)
    const targetNode = byId.get(edge.target)

    if (targetNode?.type === 'branch') {
      edges.push({
        id: `layout-top-trunk__${edge.id}`,
        sources: [sourcePortId(edge.source, edge.source_handle)],
        targets: [topMergeId(edge.target)],
      })
      edges.push({
        id: `layout-top-enter__${edge.id}`,
        sources: [topMergeId(edge.target)],
        targets: [targetPortId(edge.target)],
      })
      return
    }

    if (sourceNode?.type === 'branch') {
      const joinId = branchLayout.joins.get(edge.source)
      if (joinId === edge.target) {
        edges.push({
          id: `layout-path__${edge.id}`,
          sources: [sourcePortId(edge.source, edge.source_handle)],
          targets: [bottomMergeId(edge.source)],
        })
        addBottomTrunk(edge.source, joinId)
        return
      }
    }

    const enclosingBranchId = findEnclosingBranchForJoinEdge(edge, branchLayout)
    if (enclosingBranchId) {
      edges.push({
        id: `layout-path__${edge.id}`,
        sources: [sourcePortId(edge.source, edge.source_handle)],
        targets: [bottomMergeId(enclosingBranchId)],
      })
      addBottomTrunk(enclosingBranchId, edge.target)
      return
    }

    edges.push({
      id: `layout__${edge.id}`,
      sources: [sourcePortId(edge.source, edge.source_handle)],
      targets: [targetNodeOrTopMerge(edge.target, byId)],
    })
  })

  return edges
}

function port(id: string, side: ElkPortSide, centerX: number, centerY: number): ElkPort {
  return {
    id,
    width: PORT_SIZE,
    height: PORT_SIZE,
    x: centerX - PORT_SIZE / 2,
    y: side === 'NORTH' ? centerY - PORT_SIZE : centerY,
    layoutOptions: {
      'elk.port.side': side,
    },
  }
}

function nodeSize(node: TicketWorkflowNode | undefined): { width: number; height: number } {
  if (!node) return { width: NODE_WIDTH, height: NODE_HEIGHT }

  if (node.type === 'branch') {
    const branchCount = node.data.branches.length
    return {
      width: branchNodeWidth(branchCount),
      height: BRANCH_NODE_HEIGHT,
    }
  }

  if (node.type === 'end') return { width: END_NODE_WIDTH, height: END_NODE_HEIGHT }
  return { width: NODE_WIDTH, height: NODE_HEIGHT }
}

function sourcePortId(nodeId: string, handleId: string): string {
  return `${nodeId}::out::${handleId}`
}

function targetPortId(nodeId: string): string {
  return `${nodeId}::in`
}

export function topMergeId(branchId: string): string {
  return `${branchId}::topMerge`
}

export function bottomMergeId(branchId: string): string {
  return `${branchId}::bottomMerge`
}

function isVirtualMergeNodeId(id: string): boolean {
  return id.endsWith('::topMerge') || id.endsWith('::bottomMerge')
}

function targetNodeOrTopMerge(nodeId: string, byId: Map<string, TicketWorkflowNode>): string {
  return byId.get(nodeId)?.type === 'branch' ? topMergeId(nodeId) : targetPortId(nodeId)
}

type BranchLayout = {
  joins: Map<string, string>
  scopes: Map<string, Set<string>>
}

function analyzeBranches(graph: TicketWorkflowGraph): BranchLayout {
  const joins = new Map<string, string>()
  const scopes = new Map<string, Set<string>>()
  const byId = new Map(graph.nodes.map((node) => [node.id, node]))
  const outgoing = new Map<string, TicketWorkflowGraph['edges']>()
  graph.edges.forEach((edge) => {
    const out = outgoing.get(edge.source) ?? []
    out.push(edge)
    outgoing.set(edge.source, out)
  })

  const childrenFor = (nodeId: string): string[] =>
    [...new Set((outgoing.get(nodeId) ?? []).map((edge) => edge.target))].filter((id) => byId.has(id))

  const reachableFrom = (startId: string): Set<string> => {
    const seen = new Set<string>()
    const stack = [startId]
    while (stack.length) {
      const current = stack.pop()
      if (current == null || seen.has(current)) continue
      seen.add(current)
      childrenFor(current).forEach((child) => stack.push(child))
    }
    return seen
  }

  const distancesFrom = (startId: string): Map<string, number> => {
    const dist = new Map<string, number>([[startId, 0]])
    const queue = [startId]
    while (queue.length) {
      const current = queue.shift() as string
      const depth = dist.get(current) ?? 0
      childrenFor(current).forEach((child) => {
        if (dist.has(child)) return
        dist.set(child, depth + 1)
        queue.push(child)
      })
    }
    return dist
  }

  graph.nodes.forEach((node) => {
    if (node.type !== 'branch') return

    const edgesOut = outgoing.get(node.id) ?? []
    const firstNodes = node.data.branches
      .map((branch) => edgesOut.find((edge) => edge.source_handle === branch.id)?.target)
      .filter((id): id is string => Boolean(id) && byId.has(id as string))

    if (!firstNodes.length) return

    const reaches = firstNodes.map(reachableFrom)
    let shared = reaches[0]
    for (let i = 1; i < reaches.length; i += 1) {
      shared = new Set([...shared].filter((id) => reaches[i].has(id)))
    }
    if (!shared.size) return

    const dist = distancesFrom(node.id)
    let join: string | null = null
    let bestDistance = Infinity
    shared.forEach((id) => {
      const d = dist.get(id) ?? Infinity
      if (d < bestDistance) {
        bestDistance = d
        join = id
      }
    })
    if (join) {
      joins.set(node.id, join)
      const scope = new Set<string>()
      firstNodes.forEach((firstNode) => {
        reachableFrom(firstNode).forEach((id) => {
          if (id !== join) scope.add(id)
        })
      })
      scopes.set(node.id, scope)
    }
  })

  return { joins, scopes }
}

function findEnclosingBranchForJoinEdge(
  edge: TicketWorkflowGraph['edges'][number],
  branchLayout: BranchLayout,
): string | null {
  let match: string | null = null
  let matchSize = Infinity
  branchLayout.joins.forEach((joinId, branchId) => {
    const scope = branchLayout.scopes.get(branchId)
    if (joinId !== edge.target || !scope?.has(edge.source)) return
    if (scope.size < matchSize) {
      match = branchId
      matchSize = scope.size
    }
  })
  return match
}
