import type { TreeNodeItem } from '@/app/components/features/field-system'
import type { CreateFdTreeNodePayload } from '@/models/field-definition'

/**
 * Fill empty node.value with node_N so API validation (min_length=1) passes.
 */
function ensureTreeNodeValues(nodes: TreeNodeItem[]): TreeNodeItem[] {
  function collectAll(list: TreeNodeItem[]): TreeNodeItem[] {
    const out: TreeNodeItem[] = []
    function w(ns: TreeNodeItem[]) {
      for (const n of ns) {
        out.push(n)
        w(n.children)
      }
    }
    w(list)
    return out
  }
  let max = 0
  for (const n of collectAll(nodes)) {
    const m = /^node_(\d+)$/.exec((n.value ?? '').trim())
    if (m) max = Math.max(max, Number(m[1]))
  }
  function assign(list: TreeNodeItem[]): TreeNodeItem[] {
    return list.map((n) => {
      let val = (n.value ?? '').trim()
      if (!val) {
        max += 1
        val = `node_${max}`
      }
      return {
        ...n,
        value: val,
        children: assign(n.children),
      }
    })
  }
  return assign(nodes)
}

/**
 * DFS flatten for batch create: parent always appears before children.
 * Uses parent_index (index in this array) so the server can resolve parent_id after inserts.
 */
export function flattenTreeForPayload(nodes: TreeNodeItem[]): CreateFdTreeNodePayload[] {
  const withValues = ensureTreeNodeValues(nodes)
  const flat: CreateFdTreeNodePayload[] = []

  function walk(nlist: TreeNodeItem[], parentFlatIndex: number | null) {
    nlist.forEach((node, idx) => {
      const myIndex = flat.length
      const item: CreateFdTreeNodePayload = {
        label: node.label.trim(),
        value: node.value.trim(),
        sort_order: idx + 1,
      }
      if (parentFlatIndex !== null) {
        item.parent_index = parentFlatIndex
      }
      flat.push(item)
      if (node.children.length > 0) {
        walk(node.children, myIndex)
      }
    })
  }

  walk(withValues, null)
  return flat
}
