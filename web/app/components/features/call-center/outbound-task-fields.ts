import type { FdTreeNode } from '@/models/field-definition'
import type { OutboundTaskField } from '@/models/outbound-task'

type ConfigTreeNode = {
  label?: unknown
  value?: unknown
  children?: unknown
}

export function activeOutboundTaskFields(fields: OutboundTaskField[] | undefined): OutboundTaskField[] {
  return [...(fields ?? [])]
    .filter((field) => field.enabled)
    .sort((a, b) => a.sort_order - b.sort_order)
}

export function isEmptyOutboundFieldValue(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

export function updateOutboundTargetDraft(
  drafts: Record<number, Record<string, unknown>>,
  targetId: number,
  baseValues: Record<string, unknown>,
  fieldKey: string,
  value: unknown,
): Record<number, Record<string, unknown>> {
  return {
    ...drafts,
    [targetId]: {
      ...baseValues,
      ...(drafts[targetId] ?? {}),
      [fieldKey]: value,
    },
  }
}

export function outboundFieldTreeNodes(field: OutboundTaskField): FdTreeNode[] {
  const rawNodes = field.type_config.tree_nodes
  if (!Array.isArray(rawNodes)) return []

  const flattened: FdTreeNode[] = []
  let nextId = 1

  const visit = (raw: unknown, parentId: number | null, sortOrder: number) => {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return
    const node = raw as ConfigTreeNode
    if (typeof node.label !== 'string' || typeof node.value !== 'string') return

    const id = nextId++
    flattened.push({
      id,
      field_definition_id: 0,
      parent_id: parentId,
      label: node.label,
      value: node.value,
      sort_order: sortOrder,
      is_active: true,
      created_at: '',
      updated_at: '',
    })

    if (Array.isArray(node.children)) {
      node.children.forEach((child, index) => visit(child, id, index))
    }
  }

  rawNodes.forEach((node, index) => visit(node, null, index))
  return flattened
}
