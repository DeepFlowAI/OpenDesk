'use client'

import { useState, useCallback } from 'react'
import {
  IconPlus,
  IconTrash,
  IconChevronDown,
  IconChevronRight,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'

export type TreeNodeItem = {
  _tempId: string
  label: string
  value: string
  parent_temp_id: string | null
  children: TreeNodeItem[]
}

type TreeNodeEditorProps = {
  nodes: TreeNodeItem[]
  onChange: (nodes: TreeNodeItem[]) => void
  className?: string
  maxDepth?: number
}

let _counter = 0
export function createTempId(): string {
  return `tmp_${++_counter}_${Date.now()}`
}

function collectAllNodes(nodes: TreeNodeItem[]): TreeNodeItem[] {
  const out: TreeNodeItem[] = []
  function walk(list: TreeNodeItem[]) {
    for (const n of list) {
      out.push(n)
      walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/** Internal storage key; auto-generated, not shown in UI. */
function nextAutoTreeNodeValue(nodes: TreeNodeItem[]): string {
  let max = 0
  for (const n of collectAllNodes(nodes)) {
    const m = /^node_(\d+)$/.exec((n.value ?? '').trim())
    if (m) max = Math.max(max, Number(m[1]))
  }
  return `node_${max + 1}`
}

export function TreeNodeEditor({
  nodes,
  onChange,
  className,
  maxDepth = 5,
}: TreeNodeEditorProps) {
  const addRootNode = useCallback(() => {
    const id = createTempId()
    onChange([
      ...nodes,
      {
        _tempId: id,
        label: '',
        value: nextAutoTreeNodeValue(nodes),
        parent_temp_id: null,
        children: [],
      },
    ])
  }, [nodes, onChange])

  const updateNodeInTree = useCallback(
    (
      tree: TreeNodeItem[],
      tempId: string,
      updater: (node: TreeNodeItem) => TreeNodeItem,
    ): TreeNodeItem[] =>
      tree.map((n) => {
        if (n._tempId === tempId) return updater(n)
        return { ...n, children: updateNodeInTree(n.children, tempId, updater) }
      }),
    [],
  )

  const removeNodeFromTree = useCallback(
    (tree: TreeNodeItem[], tempId: string): TreeNodeItem[] =>
      tree
        .filter((n) => n._tempId !== tempId)
        .map((n) => ({ ...n, children: removeNodeFromTree(n.children, tempId) })),
    [],
  )

  const handleUpdateLabel = useCallback(
    (tempId: string, val: string) => {
      onChange(updateNodeInTree(nodes, tempId, (n) => ({ ...n, label: val })))
    },
    [nodes, onChange, updateNodeInTree],
  )

  const handleRemove = useCallback(
    (tempId: string) => {
      onChange(removeNodeFromTree(nodes, tempId))
    },
    [nodes, onChange, removeNodeFromTree],
  )

  const handleAddChild = useCallback(
    (parentTempId: string) => {
      const childId = createTempId()
      const newValue = nextAutoTreeNodeValue(nodes)
      onChange(
        updateNodeInTree(nodes, parentTempId, (n) => ({
          ...n,
          children: [
            ...n.children,
            {
              _tempId: childId,
              label: '',
              value: newValue,
              parent_temp_id: parentTempId,
              children: [],
            },
          ],
        })),
      )
    },
    [nodes, onChange, updateNodeInTree],
  )

  return (
    <div className={cn('space-y-1', className)}>
      {nodes.map((node) => (
        <TreeNodeRow
          key={node._tempId}
          node={node}
          depth={0}
          maxDepth={maxDepth}
          onUpdateLabel={handleUpdateLabel}
          onRemove={handleRemove}
          onAddChild={handleAddChild}
        />
      ))}
      <button
        type="button"
        onClick={addRootNode}
        className="flex h-9 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <IconPlus size={16} />
        添加根节点
      </button>
    </div>
  )
}

function TreeNodeRow({
  node,
  depth,
  maxDepth,
  onUpdateLabel,
  onRemove,
  onAddChild,
}: {
  node: TreeNodeItem
  depth: number
  maxDepth: number
  onUpdateLabel: (tempId: string, val: string) => void
  onRemove: (tempId: string) => void
  onAddChild: (parentTempId: string) => void
}) {
  const [collapsed, setCollapsed] = useState(false)
  const hasChildren = node.children.length > 0
  const canAddChild = depth < maxDepth - 1

  return (
    <div>
      <div
        className="flex items-center gap-1.5 rounded-md py-1"
        style={{ paddingLeft: depth * 24 }}
      >
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            'shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground',
            !hasChildren && 'invisible',
          )}
        >
          {collapsed ? <IconChevronRight size={14} /> : <IconChevronDown size={14} />}
        </button>

        <input
          type="text"
          value={node.label}
          onChange={(e) => onUpdateLabel(node._tempId, e.target.value)}
          placeholder="节点名称"
          className="h-8 flex-1 rounded-md border border-border bg-transparent px-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring"
        />

        {canAddChild && (
          <button
            type="button"
            onClick={() => onAddChild(node._tempId)}
            title="添加子节点"
            className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <IconPlus size={16} />
          </button>
        )}
        <button
          type="button"
          onClick={() => onRemove(node._tempId)}
          className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <IconTrash size={16} />
        </button>
      </div>

      {hasChildren && !collapsed && (
        <div>
          {node.children.map((child) => (
            <TreeNodeRow
              key={child._tempId}
              node={child}
              depth={depth + 1}
              maxDepth={maxDepth}
              onUpdateLabel={onUpdateLabel}
              onRemove={onRemove}
              onAddChild={onAddChild}
            />
          ))}
        </div>
      )}
    </div>
  )
}
