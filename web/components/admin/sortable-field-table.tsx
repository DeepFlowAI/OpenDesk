'use client'

import type { ReactNode, CSSProperties } from 'react'
import { useCallback } from 'react'
import type { DraggableAttributes, DraggableSyntheticListeners } from '@dnd-kit/core'
import { IconGripVertical } from '@tabler/icons-react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { cn } from '@/lib/utils'

export type SortableDragProps = {
  attributes: DraggableAttributes
  listeners: DraggableSyntheticListeners
}

export function SortableFieldRowsContext({
  itemIds,
  onReorderIndices,
  children,
}: {
  itemIds: string[]
  onReorderIndices: (fromIndex: number, toIndex: number) => void
  children: ReactNode
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return
      const oldIndex = itemIds.indexOf(String(active.id))
      const newIndex = itemIds.indexOf(String(over.id))
      if (oldIndex < 0 || newIndex < 0) return
      onReorderIndices(oldIndex, newIndex)
    },
    [itemIds, onReorderIndices],
  )

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
        {children}
      </SortableContext>
    </DndContext>
  )
}

/** One table row: call useSortable; place drag handle via dragCell render prop. */
export function SortableFieldTableRow({
  id,
  className,
  dragCell,
  children,
}: {
  id: string
  className?: string
  dragCell: (drag: SortableDragProps) => ReactNode
  children: ReactNode
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  const drag: SortableDragProps = { attributes, listeners }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(className, isDragging && 'relative z-10 bg-accent/20 opacity-95 shadow-sm')}
    >
      {dragCell(drag)}
      {children}
    </div>
  )
}

/** Default compact handle for first column (user/org field lists). */
export function DefaultSortDragHandle({
  attributes,
  listeners,
  handleColumnClassName = 'w-12',
}: SortableDragProps & { handleColumnClassName?: string }) {
  return (
    <div className={cn('flex shrink-0 items-center justify-start', handleColumnClassName)}>
      <span
        className="inline-flex cursor-grab touch-none select-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <IconGripVertical size={16} />
      </span>
    </div>
  )
}
