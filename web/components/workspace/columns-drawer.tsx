'use client'

import { useState, useMemo, useCallback, type CSSProperties } from 'react'
import { IconGripVertical, IconSearch } from '@tabler/icons-react'
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
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { cn } from '@/lib/utils'
import type { UnifiedField } from '@/models/field-definition'

import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'

/** Same shape as admin ColumnConfigItem (user / ticket / org views). */
export type WorkspaceColumnConfigItem = {
  field_id: number | null
  field_key: string | null
  visible: boolean
  sort_order: number
}

function columnFieldUid(c: WorkspaceColumnConfigItem): string {
  if (c.field_id != null) return `id:${c.field_id}`
  if (c.field_key != null) return `key:${c.field_key}`
  return ''
}

/** When only a search subset is reordered, merge that order back into the full visible list. */
function mergeColumnOrderBySubsequence(
  full: WorkspaceColumnConfigItem[],
  sub: WorkspaceColumnConfigItem[],
  reorderedSub: WorkspaceColumnConfigItem[],
): WorkspaceColumnConfigItem[] {
  const subUidSet = new Set(sub.map(columnFieldUid))
  const queue = [...reorderedSub]
  return full.map((c) => {
    if (!subUidSet.has(columnFieldUid(c))) return c
    const next = queue.shift()
    return next ?? c
  })
}

function SortableVisibleColumnRow({
  id,
  fieldName,
  onToggle,
}: {
  id: string
  fieldName: string
  onToggle: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'flex h-11 items-center gap-2.5 border-b border-border px-3 last:border-b-0',
        isDragging && 'relative z-10 bg-accent/25 opacity-90 shadow-sm',
      )}
    >
      <span
        className="inline-flex shrink-0 cursor-grab touch-none select-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <IconGripVertical size={16} />
      </span>
      <Switch checked={true} onCheckedChange={onToggle} />
      <span className="min-w-0 flex-1 truncate text-sm text-foreground">{fieldName}</span>
    </div>
  )
}

export type WorkspaceColumnsDrawerProps = {
  locale: string
  fields: UnifiedField[]
  baselineConfig: WorkspaceColumnConfigItem[] | null
  currentOverride: WorkspaceColumnConfigItem[] | null
  onApply: (cols: WorkspaceColumnConfigItem[]) => void
  onReset: () => void
  onClose: () => void
}

export function WorkspaceColumnsDrawer({
  locale,
  fields,
  baselineConfig,
  currentOverride,
  onApply,
  onReset,
  onClose,
}: WorkspaceColumnsDrawerProps) {
  const isZh = locale === 'zh'

  const initialDraft = useMemo<WorkspaceColumnConfigItem[]>(() => {
    if (currentOverride) return [...currentOverride]
    if (baselineConfig && baselineConfig.length > 0) return [...baselineConfig]
    return fields.map((f, idx) => ({
      field_id: f.id,
      field_key: f.key,
      visible: true,
      sort_order: idx,
    }))
  }, [currentOverride, baselineConfig, fields])

  const [draft, setDraft] = useState<WorkspaceColumnConfigItem[]>(initialDraft)
  const [searchTerm, setSearchTerm] = useState('')

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const visibleCols = useMemo(
    () => draft.filter((c) => c.visible).sort((a, b) => a.sort_order - b.sort_order),
    [draft],
  )
  const hiddenCols = useMemo(
    () => draft.filter((c) => !c.visible).sort((a, b) => a.sort_order - b.sort_order),
    [draft],
  )

  const getFieldName = useCallback(
    (col: WorkspaceColumnConfigItem) => {
      const field = fields.find((f) =>
        col.field_key ? f.key === col.field_key : f.id === col.field_id,
      )
      return field?.name ?? col.field_key ?? `#${col.field_id}`
    },
    [fields],
  )

  const toggleVisibility = useCallback((col: WorkspaceColumnConfigItem) => {
    setDraft((prev) =>
      prev.map((c) => {
        const match = col.field_key
          ? c.field_key === col.field_key
          : c.field_id === col.field_id
        if (!match) return c
        return { ...c, visible: !c.visible }
      }),
    )
  }, [])

  const handleShowAll = useCallback(() => {
    setDraft((prev) => prev.map((c) => ({ ...c, visible: true })))
  }, [])

  const handleHideAll = useCallback(() => {
    setDraft((prev) => prev.map((c) => ({ ...c, visible: false })))
  }, [])

  const handleReset = useCallback(() => {
    onReset()
    onClose()
  }, [onReset, onClose])

  const handleConfirm = useCallback(() => {
    onApply(draft)
    onClose()
  }, [draft, onApply, onClose])

  const filterColumns = useCallback(
    (cols: WorkspaceColumnConfigItem[]) => {
      if (!searchTerm.trim()) return cols
      const q = searchTerm.toLowerCase()
      return cols.filter((c) => getFieldName(c).toLowerCase().includes(q))
    },
    [searchTerm, getFieldName],
  )

  const filteredHidden = filterColumns(hiddenCols)
  const displayCols = searchTerm.trim() ? filterColumns(visibleCols) : visibleCols

  const sortableIds = useMemo(() => displayCols.map((c) => columnFieldUid(c)), [displayCols])

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      if (!over || active.id === over.id) return
      setDraft((prev) => {
        const vis = prev.filter((c) => c.visible).sort((a, b) => a.sort_order - b.sort_order)
        const hid = prev.filter((c) => !c.visible).sort((a, b) => a.sort_order - b.sort_order)
        const q = searchTerm.trim().toLowerCase()
        const filt = searchTerm.trim()
          ? vis.filter((c) => getFieldName(c).toLowerCase().includes(q))
          : vis
        const disp = searchTerm.trim() ? filt : vis
        const ids = disp.map((c) => columnFieldUid(c))
        const oldIndex = ids.indexOf(String(active.id))
        const newIndex = ids.indexOf(String(over.id))
        if (oldIndex < 0 || newIndex < 0) return prev
        if (searchTerm.trim()) {
          const reordered = arrayMove(filt, oldIndex, newIndex)
          const merged = mergeColumnOrderBySubsequence(vis, filt, reordered)
          const updated = merged.map((c, i) => ({ ...c, sort_order: i }))
          const hiddenUpdated = hid.map((c, i) => ({ ...c, sort_order: updated.length + i }))
          return [...updated, ...hiddenUpdated]
        }
        const newVis = arrayMove(vis, oldIndex, newIndex)
        const updated = newVis.map((c, i) => ({ ...c, sort_order: i }))
        const hiddenUpdated = hid.map((c, i) => ({ ...c, sort_order: updated.length + i }))
        return [...updated, ...hiddenUpdated]
      })
    },
    [searchTerm, getFieldName],
  )

  return (
    <Sheet open onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent
        side="right"
        className="flex flex-col gap-0 p-0 data-[side=right]:w-full sm:data-[side=right]:w-[560px] data-[side=right]:sm:max-w-[560px]"
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        showCloseButton={false}
      >
        <SheetHeader className="flex h-14 shrink-0 flex-row items-center justify-between border-b border-border bg-white px-5 py-0">
          <SheetTitle>{isZh ? '显示列' : 'Display Columns'}</SheetTitle>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex h-9 shrink-0 items-center rounded-lg bg-[#252525] px-4 text-sm font-medium text-white transition-colors hover:bg-[#252525]/90"
          >
            {isZh ? '确定' : 'Confirm'}
          </button>
        </SheetHeader>

        <div className="flex flex-col gap-2.5 border-b px-5 py-3">
          <div className="flex items-center gap-2">
            <div className="flex flex-1 items-center gap-1.5 rounded-lg border border-border px-2.5 py-2">
              <IconSearch size={16} className="shrink-0 text-muted-foreground" />
              <input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder={isZh ? '查找字段' : 'Find field'}
                className="min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
              />
            </div>
            <button
              type="button"
              onClick={handleShowAll}
              className="shrink-0 px-2 py-1.5 text-[13px] text-foreground/80 hover:text-foreground"
            >
              {isZh ? '全显示' : 'Show all'}
            </button>
            <button
              type="button"
              onClick={handleHideAll}
              className="shrink-0 px-2 py-1.5 text-[13px] text-foreground/80 hover:text-foreground"
            >
              {isZh ? '全隐藏' : 'Hide all'}
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="shrink-0 px-2 py-1.5 text-[13px] text-muted-foreground hover:text-foreground"
            >
              {isZh ? '重置' : 'Reset'}
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted-foreground">
                {isZh ? `显示 (${visibleCols.length})` : `Visible (${visibleCols.length})`}
              </span>
            </div>
            <div className="overflow-hidden rounded-lg border border-border">
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
                  {displayCols.map((col) => {
                    const uid = columnFieldUid(col)
                    return (
                      <SortableVisibleColumnRow
                        key={uid}
                        id={uid}
                        fieldName={getFieldName(col)}
                        onToggle={() => toggleVisibility(col)}
                      />
                    )
                  })}
                </SortableContext>
              </DndContext>
              {displayCols.length === 0 && (
                <div className="flex h-11 items-center justify-center text-xs text-muted-foreground">—</div>
              )}
            </div>
          </div>

          <div className="mt-4 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted-foreground">
                {isZh ? `隐藏 (${hiddenCols.length})` : `Hidden (${hiddenCols.length})`}
              </span>
            </div>
            <div className="overflow-hidden rounded-lg border border-border">
              {filteredHidden.map((col) => (
                <div
                  key={columnFieldUid(col)}
                  className="flex h-11 items-center gap-2.5 border-b border-border px-3 last:border-b-0"
                >
                  <IconGripVertical size={16} className="shrink-0 text-muted-foreground" aria-hidden />
                  <Switch checked={false} onCheckedChange={() => toggleVisibility(col)} />
                  <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                    {getFieldName(col)}
                  </span>
                </div>
              ))}
              {filteredHidden.length === 0 && (
                <div className="flex h-11 items-center justify-center text-xs text-muted-foreground">—</div>
              )}
            </div>
          </div>
        </div>

        <SheetFooter className="border-t px-5 py-3">
          <p className="text-[11px] text-muted-foreground">
            {isZh
              ? '拖拽可调整列顺序，开关控制列显示隐藏'
              : 'Drag the handle to reorder columns. Use the switch to show or hide each column.'}
          </p>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
