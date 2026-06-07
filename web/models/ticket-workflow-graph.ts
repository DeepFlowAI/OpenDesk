export type ConditionLogic = 'AND' | 'OR'
export type TicketWorkflowEventType = 'create' | 'update'
export type ValueScope = 'current' | 'before'

export type WorkflowCondition = {
  field_id?: number | null
  field_key?: string | null
  value_scope?: ValueScope | null
  operator: string
  value?: unknown
}

export type TriggerData = {
  event_types: TicketWorkflowEventType[]
  condition_logic: ConditionLogic
  conditions: WorkflowCondition[]
}

export type BranchItem = {
  id: string
  name: string
  is_default: boolean
  condition_logic: ConditionLogic
  conditions: WorkflowCondition[]
}

export type BranchData = {
  branches: BranchItem[]
}

export type UpdateOperation = {
  target_field_id?: number | null
  target_field_key?: string | null
  action: 'set' | 'clear'
  value?: unknown
}

export type UpdateRecordData = {
  operations: UpdateOperation[]
}

export type NodePosition = { x: number; y: number }

export type TriggerNode = {
  id: string
  type: 'trigger'
  position: NodePosition
  data: TriggerData
}

export type BranchNode = {
  id: string
  type: 'branch'
  position: NodePosition
  data: BranchData
}

export type UpdateRecordNode = {
  id: string
  type: 'update_record'
  position: NodePosition
  data: UpdateRecordData
}

export type EndNode = {
  id: string
  type: 'end'
  position: NodePosition
  data: Record<string, never>
}

export type TicketWorkflowNode = TriggerNode | BranchNode | UpdateRecordNode | EndNode

export type TicketWorkflowEdge = {
  id: string
  source: string
  target: string
  source_handle: string
}

export type TicketWorkflowGraph = {
  version: number
  nodes: TicketWorkflowNode[]
  edges: TicketWorkflowEdge[]
}

export function defaultTicketWorkflowGraph(): TicketWorkflowGraph {
  return {
    version: 1,
    nodes: [
      {
        id: 'trigger',
        type: 'trigger',
        position: { x: 0, y: 0 },
        data: { event_types: ['create', 'update'], condition_logic: 'AND', conditions: [] },
      },
      { id: 'end', type: 'end', position: { x: 0, y: 220 }, data: {} },
    ],
    edges: [{ id: 'edge-trigger-end', source: 'trigger', target: 'end', source_handle: 'next' }],
  }
}

export function newUpdateNode(): UpdateRecordNode {
  const id = `update_${Date.now().toString(36)}`
  return {
    id,
    type: 'update_record',
    position: { x: 0, y: 160 },
    data: {
      operations: [{ target_field_key: 'priority', target_field_id: null, action: 'set', value: 'medium' }],
    },
  }
}

export function newBranchNode(): BranchNode {
  const id = `branch_${Date.now().toString(36)}`
  return {
    id,
    type: 'branch',
    position: { x: 0, y: 160 },
    data: {
      branches: [
        { id: 'branch_1', name: '分支 1', is_default: false, condition_logic: 'AND', conditions: [] },
        { id: 'default', name: '否则', is_default: true, condition_logic: 'AND', conditions: [] },
      ],
    },
  }
}

export function appendBranch(data: BranchData): BranchData {
  const count = nextBranchNumber(data.branches)
  return {
    ...data,
    branches: [
      ...data.branches.filter((branch) => !branch.is_default),
      { id: `branch_${count}`, name: `分支 ${count}`, is_default: false, condition_logic: 'AND', conditions: [] },
      ...data.branches.filter((branch) => branch.is_default),
    ],
  }
}

function nextBranchNumber(branches: BranchItem[]): number {
  const usedIds = new Set(branches.map((branch) => branch.id))
  let next = branches.reduce((max, branch) => {
    const match = /^branch_(\d+)$/.exec(branch.id)
    return match ? Math.max(max, Number.parseInt(match[1], 10)) : max
  }, 0) + 1
  while (usedIds.has(`branch_${next}`)) next += 1
  return next
}

export function fieldRefFromUid(uid: string): { field_id?: number | null; field_key?: string | null } {
  if (uid.startsWith('id:')) return { field_id: Number(uid.slice(3)), field_key: null }
  if (uid.startsWith('key:')) return { field_id: null, field_key: uid.slice(4) }
  return { field_id: null, field_key: null }
}

export function fieldUid(ref: { field_id?: number | null; field_key?: string | null }): string {
  if (ref.field_id) return `id:${ref.field_id}`
  if (ref.field_key) return `key:${ref.field_key}`
  return ''
}
