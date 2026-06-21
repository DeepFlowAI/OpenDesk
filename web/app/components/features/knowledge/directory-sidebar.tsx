'use client'

import { useEffect, useMemo, useState, type CSSProperties, type HTMLAttributes } from 'react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconDotsVertical,
  IconFolder,
  IconFolderPlus,
  IconGripVertical,
  IconPencil,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { KnowledgeDirectoryMovePayload, KnowledgeDirectoryNode } from '@/models/knowledge'
import {
  findKnowledgeDirectory,
  flattenKnowledgeDirectories,
  knowledgeRootTotal,
} from './knowledge-utils'

type DirectorySidebarProps = {
  directories: KnowledgeDirectoryNode[]
  selectedDirectoryId: number | null
  canManage: boolean
  isZh: boolean
  onSelect: (directoryId: number | null) => void
  onCreate: (parentId: number | null) => void
  onEdit: (directory: KnowledgeDirectoryNode) => void
  onDelete: (directory: KnowledgeDirectoryNode) => void
  onMove: (directoryId: number, payload: KnowledgeDirectoryMovePayload) => Promise<void>
}

function siblingDirectories(nodes: KnowledgeDirectoryNode[], parentId: number | null): KnowledgeDirectoryNode[] {
  if (parentId === null) return nodes
  const parent = findKnowledgeDirectory(nodes, parentId)
  return parent?.children ?? []
}

function sortOrderBeforeTarget(
  siblings: KnowledgeDirectoryNode[],
  activeId: number,
  targetId: number,
): number {
  const ordered = siblings
    .filter((node) => node.id !== activeId)
    .sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
  const targetIndex = ordered.findIndex((node) => node.id === targetId)
  const target = ordered[targetIndex]
  if (!target) return 0
  const previous = targetIndex > 0 ? ordered[targetIndex - 1] : null
  if (!previous) return Math.max(0, target.sort_order - 5)
  if (target.sort_order - previous.sort_order > 1) {
    return Math.floor((target.sort_order + previous.sort_order) / 2)
  }
  return target.sort_order
}

type DirectoryRowProps = {
  node: KnowledgeDirectoryNode
  depth: number
  selected: boolean
  expanded: boolean
  adjusting: boolean
  canManage: boolean
  actionOpen: boolean
  isZh: boolean
  onToggle: () => void
  onSelect: () => void
  onOpenActions: () => void
  onCloseActions: () => void
  onCreate: () => void
  onEdit: () => void
  onDelete: () => void
}

function DirectoryRow({
  node,
  depth,
  selected,
  expanded,
  adjusting,
  canManage,
  actionOpen,
  isZh,
  onToggle,
  onSelect,
  onOpenActions,
  onCloseActions,
  onCreate,
  onEdit,
  onDelete,
}: DirectoryRowProps) {
  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: node.id,
    disabled: !adjusting,
  })
  const { attributes, listeners, setNodeRef: setDragRef, transform, isDragging } = useDraggable({
    id: node.id,
    disabled: !adjusting,
  })
  const rowRef = (element: HTMLDivElement | null) => {
    setDropRef(element)
    setDragRef(element)
  }
  const style: CSSProperties = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : {}
  const hasChildren = node.children.length > 0

  return (
    <div
      ref={rowRef}
      style={style}
      className={cn(
        'group relative flex h-9 items-center gap-1 rounded-lg pr-1 text-sm transition-colors',
        selected ? 'bg-[#E5E5E5] text-[#1A1A1A]' : 'text-[#404040] hover:bg-[#F5F5F5]',
        isOver && 'ring-1 ring-[#1A1A1A]',
        isDragging && 'z-10 opacity-70 shadow-sm',
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-1" style={{ paddingLeft: 8 + (depth - 1) * 16 }}>
        {adjusting ? (
          <button
            type="button"
            className="flex h-6 w-6 shrink-0 cursor-grab items-center justify-center rounded-md text-[#999999] active:cursor-grabbing"
            title={isZh ? '拖动排序' : 'Drag to sort'}
            {...(listeners as HTMLAttributes<HTMLButtonElement>)}
            {...attributes}
          >
            <IconGripVertical size={16} />
          </button>
        ) : (
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              if (hasChildren) onToggle()
            }}
            className={cn(
              'flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[#999999]',
              hasChildren ? 'hover:bg-white' : 'opacity-0',
            )}
            title={expanded ? (isZh ? '收起' : 'Collapse') : (isZh ? '展开' : 'Expand')}
          >
            {expanded ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}
          </button>
        )}

        <button
          type="button"
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          title={node.name}
        >
          <IconFolder size={16} className="shrink-0 text-[#737373]" />
          <span className="truncate">{node.name}</span>
          <span className="ml-auto shrink-0 text-xs text-[#999999]">{node.document_count}</span>
        </button>
      </div>

      {canManage && !adjusting && (
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              if (actionOpen) onCloseActions()
              else onOpenActions()
            }}
            className="flex h-7 w-7 items-center justify-center rounded-md text-[#999999] opacity-0 transition-opacity hover:bg-white hover:text-[#1A1A1A] group-hover:opacity-100"
            title={isZh ? '更多操作' : 'More actions'}
          >
            <IconDotsVertical size={16} />
          </button>
          {actionOpen && (
            <div className="absolute right-0 top-8 z-20 w-32 overflow-hidden rounded-lg border border-[#E5E5E5] bg-white py-1 shadow-lg">
              <button
                type="button"
                onClick={onCreate}
                disabled={depth >= 3}
                className="flex h-8 w-full items-center gap-2 px-3 text-left text-xs text-[#404040] hover:bg-[#F5F5F5] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <IconFolderPlus size={14} />
                {isZh ? '新建子目录' : 'New Child'}
              </button>
              <button
                type="button"
                onClick={onEdit}
                className="flex h-8 w-full items-center gap-2 px-3 text-left text-xs text-[#404040] hover:bg-[#F5F5F5]"
              >
                <IconPencil size={14} />
                {isZh ? '编辑' : 'Edit'}
              </button>
              <button
                type="button"
                onClick={onDelete}
                className="flex h-8 w-full items-center gap-2 px-3 text-left text-xs text-[#DC2626] hover:bg-[#FEF2F2]"
              >
                <IconTrash size={14} />
                {isZh ? '删除' : 'Delete'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function DirectorySidebar({
  directories,
  selectedDirectoryId,
  canManage,
  isZh,
  onSelect,
  onCreate,
  onEdit,
  onDelete,
  onMove,
}: DirectorySidebarProps) {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())
  const [actionOpenId, setActionOpenId] = useState<number | null>(null)
  const [adjusting, setAdjusting] = useState(false)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  const flat = useMemo(() => flattenKnowledgeDirectories(directories), [directories])
  const total = useMemo(() => knowledgeRootTotal(directories), [directories])

  useEffect(() => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      for (const item of flat) next.add(item.node.id)
      return next
    })
  }, [flat])

  const handleDragEnd = (event: DragEndEvent) => {
    const activeId = Number(event.active.id)
    const overId = Number(event.over?.id)
    if (!Number.isFinite(activeId) || !Number.isFinite(overId) || activeId === overId) return
    const target = findKnowledgeDirectory(directories, overId)
    if (!target) return
    const parentId = target.parent_id
    const siblings = siblingDirectories(directories, parentId)
    const sortOrder = sortOrderBeforeTarget(siblings, activeId, overId)
    void onMove(activeId, { parent_id: parentId, sort_order: sortOrder })
  }

  const toggleExpanded = (directoryId: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(directoryId)) next.delete(directoryId)
      else next.add(directoryId)
      return next
    })
  }

  const renderNodes = (nodes: KnowledgeDirectoryNode[], depth = 1): React.ReactNode =>
    nodes.map((node) => (
      <div key={node.id} className="space-y-1">
        <DirectoryRow
          node={node}
          depth={depth}
          selected={selectedDirectoryId === node.id}
          expanded={expandedIds.has(node.id)}
          adjusting={adjusting}
          canManage={canManage}
          actionOpen={actionOpenId === node.id}
          isZh={isZh}
          onToggle={() => toggleExpanded(node.id)}
          onSelect={() => onSelect(node.id)}
          onOpenActions={() => setActionOpenId(node.id)}
          onCloseActions={() => setActionOpenId(null)}
          onCreate={() => {
            setActionOpenId(null)
            onCreate(node.id)
          }}
          onEdit={() => {
            setActionOpenId(null)
            onEdit(node)
          }}
          onDelete={() => {
            setActionOpenId(null)
            onDelete(node)
          }}
        />
        {expandedIds.has(node.id) && node.children.length > 0 && renderNodes(node.children, depth + 1)}
      </div>
    ))

  return (
    <aside className="flex h-full w-[240px] shrink-0 flex-col border-r border-[#E5E5E5] bg-[#FAFAFA] px-4 py-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-[#1A1A1A]">{isZh ? '知识库' : 'Knowledge'}</h2>
        <div className="flex items-center gap-1">
          {canManage && (
            <>
              <button
                type="button"
                onClick={() => onCreate(null)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[#737373] transition-colors hover:bg-[#E5E5E5] hover:text-[#1A1A1A]"
                title={isZh ? '新建目录' : 'New directory'}
              >
                <IconPlus size={18} />
              </button>
              <button
                type="button"
                onClick={() => {
                  setAdjusting((prev) => !prev)
                  setActionOpenId(null)
                }}
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-lg transition-colors',
                  adjusting ? 'bg-[#1A1A1A] text-white' : 'text-[#737373] hover:bg-[#E5E5E5] hover:text-[#1A1A1A]',
                )}
                title={adjusting ? (isZh ? '完成排序' : 'Done sorting') : (isZh ? '调整顺序' : 'Sort directories')}
              >
                {adjusting ? <IconCheck size={18} /> : <IconGripVertical size={18} />}
              </button>
            </>
          )}
        </div>
      </div>

      <button
        type="button"
        onClick={() => onSelect(null)}
        className={cn(
          'mb-2 flex h-9 items-center gap-2 rounded-lg px-2 text-left text-sm transition-colors',
          selectedDirectoryId === null ? 'bg-[#E5E5E5] text-[#1A1A1A]' : 'text-[#404040] hover:bg-[#F5F5F5]',
        )}
      >
        <IconFolder size={16} className="text-[#737373]" />
        <span className="min-w-0 flex-1 truncate">{isZh ? '全部知识' : 'All Articles'}</span>
        <span className="shrink-0 text-xs text-[#999999]">{total}</span>
      </button>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-1">
          {directories.length > 0 ? (
            renderNodes(directories)
          ) : (
            <div className="rounded-lg border border-dashed border-[#D4D4D4] px-3 py-8 text-center text-sm text-[#999999]">
              {isZh ? '暂无目录' : 'No directories'}
            </div>
          )}
        </div>
      </DndContext>
    </aside>
  )
}
