import type {
  OutboundScript,
  OutboundScriptNode,
  OutboundScriptNodeType,
} from '@/models/outbound-task'

export type OutboundScriptIssue = { message: string; nodeId?: string }

const nodeLabels: Record<OutboundScriptNodeType, string> = {
  start: '开始',
  script: '话术',
  branch: '情景分支',
  end: '结束',
}

export function outboundScriptNodeLabel(type: OutboundScriptNodeType): string {
  return nodeLabels[type]
}

function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

export function createOutboundScript(): OutboundScript {
  return {
    version: 1,
    nodes: [{
      id: newId('start'),
      type: 'start',
      title: '开始',
      branches: [],
      position: { x: 80, y: 220 },
    }],
  }
}

export function createOutboundScriptNode(type: Exclude<OutboundScriptNodeType, 'start'>): OutboundScriptNode {
  const node: OutboundScriptNode = {
    id: newId(type),
    type,
    title: type === 'script' ? '新话术步骤' : type === 'branch' ? '新情景分支' : '结束',
    content: type === 'script' ? '<p></p>' : null,
    agent_tip: null,
    branches: [],
    position: { x: 0, y: 0 },
  }
  if (type === 'branch') {
    node.branches = [
      { id: newId('option'), label: '选项 1', next_node_id: '' },
      { id: newId('option'), label: '选项 2', next_node_id: '' },
    ]
  }
  return node
}

export function outboundScriptNodeMap(script: OutboundScript): Map<string, OutboundScriptNode> {
  return new Map(script.nodes.map((node) => [node.id, node]))
}

// When jumping from the all-scripts directory, both the branch node and its
// target must be appended so "previous step" walks back through the branch.
export function appendOutboundScriptHistory(history: string[], branchNodeId: string, targetNodeId: string): string[] {
  const base = history[history.length - 1] === branchNodeId ? history : [...history, branchNodeId]
  return [...base, targetNodeId]
}

export function outboundScriptChildren(node: OutboundScriptNode): string[] {
  if (node.type === 'branch') return node.branches.map((branch) => branch.next_node_id).filter(Boolean)
  return node.next_node_id ? [node.next_node_id] : []
}

export function firstOutboundScriptNode(script: OutboundScript): OutboundScriptNode | null {
  const start = script.nodes.find((node) => node.type === 'start')
  if (!start?.next_node_id) return null
  return script.nodes.find((node) => node.id === start.next_node_id) ?? null
}

export function stripOutboundScriptHtml(value?: string | null): string {
  if (!value) return ''
  if (typeof document === 'undefined') return value.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
  const element = document.createElement('div')
  element.innerHTML = value
  return (element.textContent ?? '').replace(/\u200b/g, '').trim()
}

export function validateOutboundScript(script: OutboundScript): OutboundScriptIssue[] {
  const issues: OutboundScriptIssue[] = []
  const map = outboundScriptNodeMap(script)
  const starts = script.nodes.filter((node) => node.type === 'start')
  if (starts.length !== 1) issues.push({ message: '话术流程必须包含一个开始节点' })
  if (script.nodes.length > 100) issues.push({ message: '话术流程最多支持 100 个节点' })

  const incoming = new Map(script.nodes.map((node) => [node.id, 0]))
  for (const node of script.nodes) {
    if (node.type !== 'start' && !node.title.trim()) issues.push({ nodeId: node.id, message: '请输入步骤标题' })
    if (node.type === 'script' && !stripOutboundScriptHtml(node.content)) {
      issues.push({ nodeId: node.id, message: '请输入建议话术' })
    }
    if (stripOutboundScriptHtml(node.content).length > 5000) {
      issues.push({ nodeId: node.id, message: '建议话术最多 5000 个字符' })
    }
    if (stripOutboundScriptHtml(node.agent_tip).length > 1000) {
      issues.push({ nodeId: node.id, message: '客服提示最多 1000 个字符' })
    }
    if (node.type === 'branch') {
      if (node.branches.length < 2 || node.branches.length > 8) {
        issues.push({ nodeId: node.id, message: '情景分支需要 2–8 个选项' })
      }
      const labels = node.branches.map((branch) => branch.label.trim().toLocaleLowerCase())
      if (labels.some((label) => !label)) issues.push({ nodeId: node.id, message: '请输入分支选项文案' })
      if (new Set(labels).size !== labels.length) issues.push({ nodeId: node.id, message: '同一情景分支中的选项名称不能重复' })
    }
    const children = outboundScriptChildren(node)
    if (node.type !== 'end' && children.length === 0) {
      issues.push({ nodeId: node.id, message: node.type === 'start' ? '请为开始节点配置后续步骤' : `请为“${node.title}”配置后续步骤` })
    }
    for (const childId of children) {
      if (!map.has(childId)) issues.push({ nodeId: node.id, message: '存在未连接的后续步骤' })
      else incoming.set(childId, (incoming.get(childId) ?? 0) + 1)
    }
  }
  if ([...incoming.values()].some((count) => count > 1)) issues.push({ message: '首期不支持多个分支汇聚到同一步骤' })

  const start = starts[0]
  if (start) {
    const visited = new Set<string>()
    const active = new Set<string>()
    const visit = (id: string, depth: number) => {
      if (depth > 20) issues.push({ nodeId: id, message: '话术流程最多支持 20 层' })
      if (active.has(id)) {
        issues.push({ nodeId: id, message: '话术流程不支持循环连接' })
        return
      }
      if (visited.has(id)) return
      active.add(id)
      const node = map.get(id)
      if (node) outboundScriptChildren(node).forEach((childId) => visit(childId, depth + 1))
      active.delete(id)
      visited.add(id)
    }
    visit(start.id, 1)
    if (visited.size !== script.nodes.length) issues.push({ message: '存在未连接到开始节点的步骤' })
  }
  return issues.filter((issue, index, all) => all.findIndex((item) => item.message === issue.message && item.nodeId === issue.nodeId) === index)
}

export function layoutOutboundScript(script: OutboundScript): OutboundScript {
  const map = outboundScriptNodeMap(script)
  const start = script.nodes.find((node) => node.type === 'start')
  if (!start) return script
  const rows = new Map<number, string[]>()
  const visit = (id: string, depth: number) => {
    const row = rows.get(depth) ?? []
    if (row.includes(id)) return
    row.push(id)
    rows.set(depth, row)
    const node = map.get(id)
    if (node) outboundScriptChildren(node).forEach((childId) => visit(childId, depth + 1))
  }
  visit(start.id, 0)
  const positions = new Map<string, { x: number; y: number }>()
  rows.forEach((ids, depth) => ids.forEach((id, index) => positions.set(id, { x: 80 + depth * 260, y: 80 + index * 160 })))
  return { ...script, nodes: script.nodes.map((node) => ({ ...node, position: positions.get(node.id) ?? node.position })) }
}

export function addOutboundScriptChild(
  script: OutboundScript,
  parentId: string,
  type: Exclude<OutboundScriptNodeType, 'start'>,
  branchId?: string,
): { script: OutboundScript; nodeId: string } {
  const child = createOutboundScriptNode(type)
  const nodes = script.nodes.map((node) => {
    if (node.id !== parentId) return node
    if (node.type === 'branch') {
      return { ...node, branches: node.branches.map((branch) => branch.id === branchId ? { ...branch, next_node_id: child.id } : branch) }
    }
    return { ...node, next_node_id: child.id }
  })
  return { script: layoutOutboundScript({ ...script, nodes: [...nodes, child] }), nodeId: child.id }
}

export function deleteOutboundScriptSubtree(script: OutboundScript, rootId: string): OutboundScript {
  const map = outboundScriptNodeMap(script)
  const deleted = new Set<string>()
  const visit = (id: string) => {
    if (deleted.has(id)) return
    deleted.add(id)
    const node = map.get(id)
    if (node) outboundScriptChildren(node).forEach(visit)
  }
  visit(rootId)
  const nodes = script.nodes
    .filter((node) => !deleted.has(node.id))
    .map((node) => ({
      ...node,
      next_node_id: node.next_node_id && deleted.has(node.next_node_id) ? null : node.next_node_id,
      branches: node.branches.map((branch) => deleted.has(branch.next_node_id) ? { ...branch, next_node_id: '' } : branch),
    }))
  return layoutOutboundScript({ ...script, nodes })
}

export function outboundScriptMaxDepth(script: OutboundScript): number {
  const map = outboundScriptNodeMap(script)
  const start = script.nodes.find((node) => node.type === 'start')
  if (!start) return 0
  const visit = (id: string, active: Set<string>): number => {
    if (active.has(id)) return 0
    const node = map.get(id)
    if (!node) return 0
    const next = new Set(active).add(id)
    return 1 + Math.max(0, ...outboundScriptChildren(node).map((child) => visit(child, next)))
  }
  return visit(start.id, new Set())
}
