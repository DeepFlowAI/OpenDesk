'use client'

import { useState, useCallback, useMemo, useEffect, Fragment, type ReactNode, type CSSProperties } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconGripVertical,
  IconX,
  IconLayoutDashboard,
  IconLayoutGrid,
  IconChevronDown,
  IconChevronRight,
} from '@tabler/icons-react'
import {
  DndContext,
  DragOverlay,
  useDraggable,
  useDroppable,
  PointerSensor,
  useSensor,
  useSensors,
  pointerWithin,
  rectIntersection,
  closestCenter,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
  type CollisionDetection,
} from '@dnd-kit/core'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { useFormLayout, useUpdateFormLayout } from '@/service/use-form-layouts'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { useFieldDefinitions } from '@/service/use-field-definitions'
import { FIELD_TYPE_LABELS, FieldDefaultState, FieldType } from '@/types/field-enums'
import type { FdFieldDefinition, UnifiedField } from '@/models/field-definition'
import { InteractionRulesTab, type FieldOption } from '@/app/components/features/interaction-rules-tab'
import type {
  CreateFdFormLayoutTabPayload,
  CreateFdFormLayoutSectionPayload,
  CreateFdFormLayoutFieldPayload,
  FieldSource,
} from '@/models/form-layout'

// ── Drag data types ──

type PoolFieldDragData = {
  origin: 'pool-field'
  source: 'system' | 'custom'
  fieldSource: FieldSource
  fieldKey: string | null
  fieldDefId: number | null
  displayName: string
  fieldType: string
}

type MetadataFieldDef = {
  key: string
  name_zh: string
  name_en: string
  field_type: FieldType
}

const METADATA_FIELDS: MetadataFieldDef[] = [
  { key: 'created_at', name_zh: '创建时间', name_en: 'Created At', field_type: FieldType.DATETIME },
  { key: 'updated_at', name_zh: '更新时间', name_en: 'Updated At', field_type: FieldType.DATETIME },
]

type CanvasItemDragData = {
  origin: 'canvas-item'
  itemUid: string
}

type DragData = PoolFieldDragData | CanvasItemDragData

// ── Drop target: where the active drag would land if released right now ──

type DropTarget =
  | { kind: 'before'; refUid: string; disabled: boolean }
  | { kind: 'after'; refUid: string; disabled: boolean }
  | { kind: 'row-end'; tabUid: string; rowIdx: number; disabled: boolean }
  | { kind: 'inter-row'; tabUid: string; afterRowIdx: number; disabled: boolean }

// ── Canvas item: flat list of sections (dividers) and fields ──

type SectionItem = {
  _uid: string
  _tabUid: string
  itemType: 'section'
  name: string
}

type FieldItem = {
  _uid: string
  _tabUid: string
  itemType: 'field'
  field_definition_id: number | null
  field_key: string | null
  field_source: FieldSource
  default_state: string
  column_span: number
}

type CanvasItem = SectionItem | FieldItem

type LocalTab = {
  _uid: string
  id?: number
  name: string
  sort_order: number
}

type Selection =
  | { type: 'form' }
  | { type: 'field'; uid: string }
  | { type: 'section'; uid: string }
  | { type: 'tab'; tabUid: string }

let uidCounter = 0
function uid() {
  return `_local_${++uidCounter}_${Date.now()}`
}

function customDefinitionToUnifiedField(field: FdFieldDefinition): UnifiedField {
  return {
    key: field.key,
    id: field.id,
    domain: field.domain,
    source: 'custom',
    name: field.name,
    description: field.description,
    help_text: field.help_text,
    field_type: field.field_type,
    type_config: field.type_config,
    applicable_modules: field.applicable_modules,
    slot_column: field.slot_column,
    show_in_workspace: field.show_in_workspace,
    sort_order: field.sort_order,
    status: field.status,
    options: field.options,
    tree_nodes: field.tree_nodes,
    created_at: field.created_at,
    updated_at: field.updated_at,
  }
}

function metadataToUnifiedField(field: MetadataFieldDef, locale: 'zh' | 'en'): UnifiedField {
  return {
    key: field.key,
    id: null,
    domain: 'ticket_metadata',
    source: 'metadata',
    name: locale === 'zh' ? field.name_zh : field.name_en,
    description: null,
    help_text: null,
    field_type: field.field_type as FieldType,
    type_config: {},
    applicable_modules: null,
    slot_column: null,
    show_in_workspace: null,
    sort_order: 0,
    status: 'active',
    options: [],
    tree_nodes: [],
    created_at: null,
    updated_at: null,
  }
}

/** Count fields belonging to a section item (fields after it until the next section). */
function countSectionFields(items: CanvasItem[], sectionUid: string): number {
  const idx = items.findIndex((i) => i._uid === sectionUid)
  if (idx < 0) return 0
  let count = 0
  for (let i = idx + 1; i < items.length; i++) {
    if (items[i].itemType === 'section') break
    count++
  }
  return count
}

// ── Row layout: pack flat items into visual rows according to columnsPerRow. ──

type Row =
  | { kind: 'section'; item: SectionItem }
  | { kind: 'fields'; items: FieldItem[]; colsUsed: number }

function buildRows(items: CanvasItem[], cols: number): Row[] {
  const rows: Row[] = []
  let buf: FieldItem[] = []
  let used = 0
  const flush = () => {
    if (buf.length) {
      rows.push({ kind: 'fields', items: buf, colsUsed: used })
      buf = []
      used = 0
    }
  }
  for (const item of items) {
    if (item.itemType === 'section') {
      flush()
      rows.push({ kind: 'section', item })
      continue
    }
    const span = Math.max(1, Math.min(item.column_span, cols))
    if (used + span > cols) flush()
    buf.push(item)
    used += span
  }
  flush()
  return rows
}

// ── Collision detection: pointerWithin → rectIntersection → closestCenter ──

const collisionDetection: CollisionDetection = (args) => {
  const p = pointerWithin(args)
  if (p.length > 0) return p
  const r = rectIntersection(args)
  if (r.length > 0) return r
  return closestCenter(args)
}

// ── Compute the precise drop target from a DnD event. ──

function computeDropTarget(
  event: DragOverEvent | DragEndEvent,
  items: CanvasItem[],
  columnsPerRow: number,
): DropTarget | null {
  const { active, over } = event
  if (!over) return null

  const dragData = active.data.current as DragData | undefined
  const overId = String(over.id)

  // Detect duplicate-field / drop-on-self → mark as disabled (visual hint only).
  const isDuplicate = (() => {
    if (dragData?.origin !== 'pool-field') return false
    return items.some((i) => {
      if (i.itemType !== 'field') return false
      if (i.field_source !== dragData.fieldSource) return false
      if (dragData.source === 'system') return i.field_key === dragData.fieldKey
      return i.field_definition_id === dragData.fieldDefId
    })
  })()
  const isDropOnSelf = (refUid: string) =>
    dragData?.origin === 'canvas-item' && dragData.itemUid === refUid

  // Row-end drop zone: id like `row-end-<tabUid>-<rowIdx>`.
  if (overId.startsWith('row-end-')) {
    const m = overId.match(/^row-end-(.+)-(\d+)$/)
    if (m) {
      return {
        kind: 'row-end',
        tabUid: m[1],
        rowIdx: Number(m[2]),
        disabled: isDuplicate,
      }
    }
  }

  // Inter-row drop zone: id like `inter-row-<tabUid>-<afterRowIdx>` (afterRowIdx may be -1).
  if (overId.startsWith('inter-row-')) {
    const m = overId.match(/^inter-row-(.+)-(-?\d+)$/)
    if (m) {
      return {
        kind: 'inter-row',
        tabUid: m[1],
        afterRowIdx: Number(m[2]),
        disabled: isDuplicate,
      }
    }
  }

  // Whole-tab drop zone: degrade to "append after the last row".
  if (overId.startsWith('tab-drop-')) {
    const tabUid = overId.replace('tab-drop-', '')
    const tabItems = items.filter((i) => i._tabUid === tabUid)
    const rows = buildRows(tabItems, columnsPerRow)
    return {
      kind: 'inter-row',
      tabUid,
      afterRowIdx: rows.length - 1,
      disabled: isDuplicate,
    }
  }

  // Hit a concrete canvas item: decide before/after by pointer position.
  const item = items.find((i) => i._uid === overId)
  if (!item) return null

  const overRect = over.rect
  const activeRect = active.rect.current.translated ?? active.rect.current.initial
  const disabled = isDuplicate || isDropOnSelf(overId)

  if (!activeRect || !overRect) {
    return { kind: 'before', refUid: overId, disabled }
  }

  // Section dividers span the whole row → use Y; fields → use X.
  if (item.itemType === 'section') {
    const activeMid = activeRect.top + activeRect.height / 2
    const overMid = overRect.top + overRect.height / 2
    return {
      kind: activeMid < overMid ? 'before' : 'after',
      refUid: overId,
      disabled,
    }
  }
  const activeMid = activeRect.left + activeRect.width / 2
  const overMid = overRect.left + overRect.width / 2
  return {
    kind: activeMid < overMid ? 'before' : 'after',
    refUid: overId,
    disabled,
  }
}

/** Apply a DropTarget to the items array. movingUid !== null = reordering an existing item; otherwise inserting newItem. */
function applyDropTarget(
  items: CanvasItem[],
  movingUid: string | null,
  newItem: CanvasItem | null,
  target: DropTarget,
  cols: number,
): CanvasItem[] {
  const without = movingUid ? items.filter((i) => i._uid !== movingUid) : items
  const baseInsert = newItem ?? items.find((i) => i._uid === movingUid)
  if (!baseInsert) return items

  const insertAt = (arr: CanvasItem[], idx: number, tabUid: string): CanvasItem[] => {
    const adjusted: CanvasItem = { ...baseInsert, _tabUid: tabUid }
    const copy = [...arr]
    copy.splice(idx, 0, adjusted)
    return copy
  }

  if (target.kind === 'before' || target.kind === 'after') {
    const refIdx = without.findIndex((i) => i._uid === target.refUid)
    if (refIdx < 0) return items
    const refItem = without[refIdx]
    return insertAt(without, target.kind === 'before' ? refIdx : refIdx + 1, refItem._tabUid)
  }

  // For row-end / inter-row we use the ORIGINAL rows (matching what the user saw on screen)
  // to pick a terminator UID, then map that UID into the `without` array. If the terminator
  // happens to be the moving item itself, walk backwards to the previous row's terminator.
  const tabItemsOrig = items.filter((i) => i._tabUid === target.tabUid)
  const rowsOrig = buildRows(tabItemsOrig, cols)
  const findTerminatorUid = (rowIdx: number): string | null => {
    for (let i = rowIdx; i >= 0; i--) {
      const r = rowsOrig[i]
      if (!r) continue
      const lastUid = r.kind === 'section' ? r.item._uid : r.items[r.items.length - 1]._uid
      if (lastUid !== movingUid) return lastUid
    }
    return null
  }
  const prependToTab = () => {
    const firstIdx = without.findIndex((i) => i._tabUid === target.tabUid)
    return insertAt(without, firstIdx < 0 ? without.length : firstIdx, target.tabUid)
  }

  if (target.kind === 'row-end') {
    const refUid = findTerminatorUid(target.rowIdx)
    if (refUid == null) return prependToTab()
    const refIdx = without.findIndex((i) => i._uid === refUid)
    return insertAt(without, refIdx + 1, target.tabUid)
  }

  // inter-row
  if (target.afterRowIdx < 0) return prependToTab()
  const refUid = findTerminatorUid(target.afterRowIdx)
  if (refUid == null) return prependToTab()
  const refIdx = without.findIndex((i) => i._uid === refUid)
  return insertAt(without, refIdx + 1, target.tabUid)
}

/** Reconstruct Tab→Section→Field payloads from flat items list for save. */
function buildTabPayloads(
  tabs: LocalTab[],
  items: CanvasItem[],
  locale: 'zh' | 'en',
): CreateFdFormLayoutTabPayload[] {
  return tabs.map((tb, ti) => {
    const tabItems = items.filter((i) => i._tabUid === tb._uid)
    const sections: CreateFdFormLayoutSectionPayload[] = []
    let currentFields: CreateFdFormLayoutFieldPayload[] = []
    let currentSectionName: string | null = null

    for (const item of tabItems) {
      if (item.itemType === 'section') {
        if (currentSectionName !== null || currentFields.length > 0) {
          sections.push({
            name: currentSectionName ?? '',
            sort_order: sections.length,
            is_collapsed: false,
            fields: currentFields.map((f, fi) => ({ ...f, sort_order: fi })),
          })
          currentFields = []
        }
        currentSectionName = item.name
      } else {
        currentFields.push({
          field_definition_id: item.field_definition_id,
          field_key: item.field_key,
          field_source: item.field_source,
          default_state: item.default_state as FieldDefaultState,
          column_span: item.column_span,
        })
      }
    }

    if (currentSectionName !== null || currentFields.length > 0) {
      sections.push({
        name: currentSectionName ?? '',
        sort_order: sections.length,
        is_collapsed: false,
        fields: currentFields.map((f, fi) => ({ ...f, sort_order: fi })),
      })
    }

    return { name: tb.name, sort_order: ti, sections }
  })
}

// ── Main page ──

export default function FormLayoutEditorPage() {
  const params = useParams()
  const router = useRouter()
  const { locale } = useLocaleStore()
  const layoutId = Number(params.id)

  const { data: layout, isLoading } = useFormLayout(layoutId)
  const updateMutation = useUpdateFormLayout()

  const { data: systemFieldsData } = useUnifiedFields({ domain: 'ticket' })
  const { data: customFieldsData } = useFieldDefinitions({ domain: 'shared_pool' })
  const { data: userFieldsData } = useUnifiedFields({ domain: 'user' })
  const { data: orgFieldsData } = useUnifiedFields({ domain: 'organization' })

  const [activeTab, setActiveTab] = useState<'form' | 'rules'>('form')
  const [selection, setSelection] = useState<Selection>({ type: 'form' })

  const [layoutName, setLayoutName] = useState('')
  const [columnsPerRow, setColumnsPerRow] = useState(2)
  const [labelPosition, setLabelPosition] = useState('top')
  const [tabs, setTabs] = useState<LocalTab[]>([])
  const [items, setItems] = useState<CanvasItem[]>([])
  const [activeCanvasTabIdx, setActiveCanvasTabIdx] = useState(0)
  const [dirty, setDirty] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Initialize from server data
  useEffect(() => {
    if (!layout) return
    setLayoutName(layout.name)
    setColumnsPerRow(layout.columns_per_row)
    setLabelPosition(layout.label_position)

    const localTabs: LocalTab[] = []
    const localItems: CanvasItem[] = []

    for (const serverTab of layout.tabs || []) {
      const tabUid = uid()
      localTabs.push({ _uid: tabUid, id: serverTab.id, name: serverTab.name, sort_order: serverTab.sort_order })

      for (const serverSec of serverTab.sections || []) {
        if (serverSec.name) {
          localItems.push({ _uid: uid(), _tabUid: tabUid, itemType: 'section', name: serverSec.name })
        }
        for (const serverField of serverSec.fields || []) {
          localItems.push({
            _uid: uid(),
            _tabUid: tabUid,
            itemType: 'field',
            field_definition_id: serverField.field_definition_id,
            field_key: serverField.field_key,
            field_source: (serverField.field_source as FieldSource) || 'ticket',
            default_state: serverField.default_state,
            column_span: serverField.column_span,
          })
        }
      }
    }

    setTabs(localTabs)
    setItems(localItems)
    setActiveCanvasTabIdx(0)
    setDirty(false)
  }, [layout])

  // ── Derived ──

  const isTicketDetail = layout?.scene === 'ticket_detail'

  const systemFields: UnifiedField[] = useMemo(
    () => (systemFieldsData?.items ?? []).filter((f) => f.source === 'system'),
    [systemFieldsData]
  )

  /** Left-panel list only; omits fields meaningless or unsupported on the create form. */
  const paletteSystemFields = useMemo(() => {
    if (layout?.scene !== 'new_ticket') return systemFields
    const excluded = new Set([
      'ticket_number',
      'conversation_id',
      'created_by',
      'updated_by',
    ])
    return systemFields.filter((f) => f.key && !excluded.has(f.key))
  }, [systemFields, layout?.scene])

  const customFields = useMemo(
    () => (customFieldsData?.items ?? []).filter((f) => f.applicable_modules?.includes('ticket')),
    [customFieldsData]
  )

  const metadataFields = useMemo<MetadataFieldDef[]>(() => {
    return isTicketDetail ? METADATA_FIELDS : []
  }, [isTicketDetail])

  const userFields: UnifiedField[] = useMemo(
    () => (isTicketDetail ? (userFieldsData?.items ?? []) : []),
    [isTicketDetail, userFieldsData]
  )

  const orgFields: UnifiedField[] = useMemo(
    () => (isTicketDetail ? (orgFieldsData?.items ?? []) : []),
    [isTicketDetail, orgFieldsData]
  )

  const isFieldOnCanvas = useCallback(
    (fieldSource: FieldSource, key: string | null, defId: number | null) =>
      items.some((i) => {
        if (i.itemType !== 'field') return false
        if (i.field_source !== fieldSource) return false
        if (key) return i.field_key === key
        return i.field_definition_id === defId
      }),
    [items]
  )

  const getFieldDisplayInfo = useCallback(
    (f: FieldItem): { name: string; type: string } => {
      if (f.field_source === 'ticket_metadata') {
        const meta = METADATA_FIELDS.find((m) => m.key === f.field_key)
        if (meta) {
          const name = locale === 'zh' ? meta.name_zh : meta.name_en
          return { name, type: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[meta.field_type]?.[locale] ?? meta.field_type }
        }
      }
      if (f.field_source === 'user') {
        const uf = (userFieldsData?.items ?? []).find((u) =>
          f.field_key ? u.key === f.field_key : u.id === f.field_definition_id
        )
        if (uf) return { name: uf.name, type: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[uf.field_type]?.[locale] ?? uf.field_type }
      }
      if (f.field_source === 'organization') {
        const of_ = (orgFieldsData?.items ?? []).find((o) =>
          f.field_key ? o.key === f.field_key : o.id === f.field_definition_id
        )
        if (of_) return { name: of_.name, type: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[of_.field_type]?.[locale] ?? of_.field_type }
      }
      if (f.field_key) {
        const sys = systemFields.find((s) => s.key === f.field_key)
        if (sys) return { name: sys.name, type: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[sys.field_type]?.[locale] ?? sys.field_type }
      }
      if (f.field_definition_id) {
        const cust = customFields.find((c) => c.id === f.field_definition_id)
        if (cust) return { name: cust.name, type: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[cust.field_type]?.[locale] ?? cust.field_type }
      }
      return { name: f.field_key || `Field #${f.field_definition_id}`, type: '' }
    },
    [systemFields, customFields, userFieldsData, orgFieldsData, locale]
  )

  const activeCanvasTab = tabs[activeCanvasTabIdx] ?? null

  const itemsByTab = useMemo(() => {
    const map = new Map<string, CanvasItem[]>()
    for (const tb of tabs) map.set(tb._uid, [])
    for (const item of items) {
      const arr = map.get(item._tabUid)
      if (arr) arr.push(item)
    }
    return map
  }, [items, tabs])

  const activeTabItems = useMemo(
    () => (activeCanvasTab ? (itemsByTab.get(activeCanvasTab._uid) ?? []) : []),
    [itemsByTab, activeCanvasTab]
  )

  const availableFieldOptions = useMemo(() => {
    const opts: FieldOption[] = []
    for (const i of items) {
      if (i.itemType !== 'field') continue
      if (i.field_source === 'ticket_metadata' && i.field_key) {
        const meta = METADATA_FIELDS.find((m) => m.key === i.field_key)
        if (meta) {
          const field = metadataToUnifiedField(meta, locale)
          opts.push({ value: `key:${i.field_key}`, label: field.name, isSystem: true, field })
        }
      } else if (i.field_source === 'user') {
        const field = (userFieldsData?.items ?? []).find((u) =>
          i.field_key ? u.key === i.field_key : u.id === i.field_definition_id
        )
        if (field) {
          const value = field.key ? `key:${field.key}` : `def:${field.id}`
          opts.push({ value, label: field.name, isSystem: field.source === 'system', field })
        }
      } else if (i.field_source === 'organization') {
        const field = (orgFieldsData?.items ?? []).find((o) =>
          i.field_key ? o.key === i.field_key : o.id === i.field_definition_id
        )
        if (field) {
          const value = field.key ? `key:${field.key}` : `def:${field.id}`
          opts.push({ value, label: field.name, isSystem: field.source === 'system', field })
        }
      } else if (i.field_key) {
        const sys = systemFields.find((s) => s.key === i.field_key)
        if (sys) opts.push({ value: `key:${i.field_key}`, label: sys.name, isSystem: true, field: sys })
      } else if (i.field_definition_id) {
        const cust = customFields.find((c) => c.id === i.field_definition_id)
        if (cust) {
          const field = customDefinitionToUnifiedField(cust)
          opts.push({ value: `def:${i.field_definition_id}`, label: field.name, isSystem: false, field })
        }
      }
    }
    return opts
  }, [items, systemFields, customFields, userFieldsData, orgFieldsData, locale])

  // ── Actions ──

  const markDirty = useCallback(() => setDirty(true), [])

  /** Get the target tab for adding items (first tab if none selected) */
  const getTargetTab = useCallback((): LocalTab | null => {
    return activeCanvasTab ?? tabs[0] ?? null
  }, [activeCanvasTab, tabs])

  const addFieldToActiveTab = useCallback(
    (fieldSource: FieldSource, source: 'system' | 'custom', field: UnifiedField | MetadataFieldDef | { id: number; name: string; field_type: string }) => {
      const targetTab = getTargetTab()
      if (!targetTab) return
      const isRef = fieldSource === 'user' || fieldSource === 'organization' || fieldSource === 'ticket_metadata'
      const newItem: FieldItem = {
        _uid: uid(),
        _tabUid: targetTab._uid,
        itemType: 'field',
        field_definition_id: source === 'custom' ? (field as { id: number }).id : null,
        field_key: source === 'system' ? ((field as UnifiedField).key ?? (field as MetadataFieldDef).key) : null,
        field_source: fieldSource,
        default_state: isRef ? 'readonly' : 'optional',
        column_span: 1,
      }
      setItems((prev) => [...prev, newItem])
      markDirty()
    },
    [getTargetTab, markDirty]
  )

  const addSection = useCallback(() => {
    const targetTab = getTargetTab()
    if (!targetTab) return
    const newItem: SectionItem = {
      _uid: uid(),
      _tabUid: targetTab._uid,
      itemType: 'section',
      name: locale === 'zh' ? '新分段' : 'New Section',
    }
    setItems((prev) => [...prev, newItem])
    setSelection({ type: 'section', uid: newItem._uid })
    markDirty()
  }, [getTargetTab, locale, markDirty])

  const addTab = useCallback(() => {
    const newTab: LocalTab = {
      _uid: uid(),
      name: `${locale === 'zh' ? '标签' : 'Tab'} ${tabs.length + 1}`,
      sort_order: tabs.length,
    }
    setTabs((prev) => [...prev, newTab])
    setActiveCanvasTabIdx(tabs.length)
    setSelection({ type: 'tab', tabUid: newTab._uid })
    markDirty()
  }, [tabs.length, locale, markDirty])

  const removeTab = useCallback((tabUid: string) => {
    if (tabs.length <= 1) return
    setItems((prev) => prev.filter((i) => i._tabUid !== tabUid))
    setTabs((prev) => prev.filter((tb) => tb._uid !== tabUid))
    setActiveCanvasTabIdx((prev) => Math.min(prev, tabs.length - 2))
    setSelection({ type: 'form' })
    markDirty()
  }, [tabs, markDirty])

  const removeItem = useCallback(
    (itemUid: string) => {
      setItems((prev) => prev.filter((i) => i._uid !== itemUid))
      if ((selection.type === 'field' || selection.type === 'section') && selection.uid === itemUid) {
        setSelection({ type: 'form' })
      }
      markDirty()
    },
    [selection, markDirty]
  )

  // ── Save ──

  const handleSave = useCallback(async () => {
    if (!layout) return
    try {
      const tabPayloads = buildTabPayloads(tabs, items, locale)
      await updateMutation.mutateAsync({
        id: layoutId,
        data: {
          name: layoutName,
          columns_per_row: columnsPerRow,
          label_position: labelPosition,
          tabs: tabPayloads,
        },
      })
      setDirty(false)
      setToast({ type: 'success', text: t('fl.saveSuccess', locale) })
      setTimeout(() => setToast(null), 3000)
    } catch {
      setToast({ type: 'error', text: t('fl.saveFailed', locale) })
      setTimeout(() => setToast(null), 3000)
    }
  }, [layout, layoutId, layoutName, columnsPerRow, labelPosition, tabs, items, updateMutation, locale])

  // ── DnD ──

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))
  const [activeDrag, setActiveDrag] = useState<DragData | null>(null)
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null)

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveDrag((event.active.data.current as DragData) ?? null)
    setDropTarget(null)
  }, [])

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      const next = computeDropTarget(event, items, columnsPerRow)
      setDropTarget(next)
    },
    [items, columnsPerRow]
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const target = computeDropTarget(event, items, columnsPerRow)
      setActiveDrag(null)
      setDropTarget(null)
      if (!target || target.disabled) return

      const dragData = event.active.data.current as DragData | undefined
      if (!dragData) return

      if (dragData.origin === 'pool-field') {
        const isRef =
          dragData.fieldSource === 'user' ||
          dragData.fieldSource === 'organization' ||
          dragData.fieldSource === 'ticket_metadata'
        const newItem: FieldItem = {
          _uid: uid(),
          _tabUid: '', // overwritten by applyDropTarget
          itemType: 'field',
          field_definition_id: dragData.source === 'custom' ? dragData.fieldDefId : null,
          field_key: dragData.source === 'system' ? dragData.fieldKey : null,
          field_source: dragData.fieldSource,
          default_state: isRef ? 'readonly' : 'optional',
          column_span: 1,
        }
        setItems((prev) => applyDropTarget(prev, null, newItem, target, columnsPerRow))
        markDirty()
        return
      }

      // canvas-item: reorder
      setItems((prev) => applyDropTarget(prev, dragData.itemUid, null, target, columnsPerRow))
      markDirty()
    },
    [items, columnsPerRow, markDirty]
  )

  const handleDragCancel = useCallback(() => {
    setActiveDrag(null)
    setDropTarget(null)
  }, [])

  const handleBack = useCallback(() => {
    if (dirty && !window.confirm(t('fl.leaveConfirm', locale))) return
    router.push('/form-layouts')
  }, [dirty, locale, router])

  // ── Loading / error ──

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">{t('fl.loading', locale)}</p>
      </div>
    )
  }
  if (!layout) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Layout not found</p>
      </div>
    )
  }

  const selectedField = selection.type === 'field' ? (items.find((i) => i._uid === selection.uid && i.itemType === 'field') as FieldItem | undefined) : null
  const selectedSection = selection.type === 'section' ? (items.find((i) => i._uid === selection.uid && i.itemType === 'section') as SectionItem | undefined) : null

  return (
    <div className="-m-8 flex h-[calc(100vh-64px)] flex-col">
      {toast && (
        <div
          className={cn(
            'absolute left-1/2 top-4 z-50 -translate-x-1/2 rounded-lg px-4 py-2 text-sm shadow-lg',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          )}
        >
          {toast.text}
        </div>
      )}

      {/* Top bar */}
      <div className="flex h-[60px] shrink-0 items-center justify-between border-b border-border px-7">
        <div className="flex items-center gap-4">
          <button onClick={handleBack} className="text-foreground/80 transition-colors hover:text-foreground">
            <IconArrowLeft size={20} />
          </button>
          <span className="text-base font-semibold text-foreground">{t('fl.title', locale)}</span>
          <div className="ml-4 flex gap-0.5 rounded-lg bg-accent p-0.5">
            <button
              onClick={() => setActiveTab('form')}
              className={cn(
                'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
                activeTab === 'form' ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground/80'
              )}
            >
              {t('fl.tab.editForm', locale)}
            </button>
            <button
              onClick={() => setActiveTab('rules')}
              className={cn(
                'rounded-md px-4 py-1.5 text-sm font-medium transition-colors',
                activeTab === 'rules' ? 'bg-white text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground/80'
              )}
            >
              {t('fl.tab.interactionRules', locale)}
            </button>
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={updateMutation.isPending}
          className="flex h-9 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
        >
          {updateMutation.isPending ? t('fl.saving', locale) : t('fl.save', locale)}
        </button>
      </div>

      {/* Body */}
      {activeTab === 'form' ? (
        <DndContext
          sensors={sensors}
          collisionDetection={collisionDetection}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
          <div className="flex flex-1 overflow-hidden">
            {/* Left panel */}
            <LeftPanel
              locale={locale}
              scene={layout.scene}
              systemFields={paletteSystemFields}
              customFields={customFields}
              metadataFields={metadataFields}
              userFields={userFields}
              orgFields={orgFields}
              isFieldOnCanvas={isFieldOnCanvas}
              onAddField={addFieldToActiveTab}
              onAddSection={addSection}
              onAddTab={addTab}
            />

            {/* Center — Canvas */}
            <CanvasArea
              locale={locale}
              tabs={tabs}
              itemsByTab={itemsByTab}
              selection={selection}
              columnsPerRow={columnsPerRow}
              labelPosition={labelPosition}
              dropTarget={dropTarget}
              isDragging={activeDrag !== null}
              onSelectTab={(idx) => { setActiveCanvasTabIdx(idx); setSelection({ type: 'tab', tabUid: tabs[idx]?._uid ?? '' }) }}
              onSelectField={(uid) => setSelection({ type: 'field', uid })}
              onSelectSection={(uid) => setSelection({ type: 'section', uid })}
              onSelectForm={() => setSelection({ type: 'form' })}
              onRemoveItem={removeItem}
              onRemoveTab={removeTab}
              getFieldDisplayInfo={getFieldDisplayInfo}
            />

            {/* Right panel */}
            <RightPanel
              locale={locale}
              scene={layout.scene}
              selection={selection}
              columnsPerRow={columnsPerRow}
              labelPosition={labelPosition}
              selectedField={selectedField ?? null}
              selectedSection={selectedSection ?? null}
              tabs={tabs}
              onColumnsChange={(v) => { setColumnsPerRow(v); markDirty() }}
              onLabelPositionChange={(v) => { setLabelPosition(v); markDirty() }}
              onFieldStateChange={(uid, state) => {
                setItems((prev) => prev.map((i) => (i._uid === uid && i.itemType === 'field' ? { ...i, default_state: state } : i)))
                markDirty()
              }}
              onFieldSpanChange={(uid, span) => {
                setItems((prev) => prev.map((i) => (i._uid === uid && i.itemType === 'field' ? { ...i, column_span: span } : i)))
                markDirty()
              }}
              onSectionNameChange={(uid, name) => {
                setItems((prev) => prev.map((i) => (i._uid === uid && i.itemType === 'section' ? { ...i, name } : i)))
                markDirty()
              }}
              onTabNameChange={(tabUid, name) => {
                setTabs((prev) => prev.map((tb) => (tb._uid === tabUid ? { ...tb, name } : tb)))
                markDirty()
              }}
              onRemoveTab={removeTab}
              getFieldDisplayInfo={getFieldDisplayInfo}
            />
          </div>

          {/* Drag overlay — keep it visually distinct from the in-place placeholder */}
          <DragOverlay dropAnimation={null}>
            {activeDrag?.origin === 'pool-field' && (
              <div className="flex w-[260px] rotate-2 items-center gap-2 rounded-lg border-2 border-primary bg-white px-3 py-2 text-sm shadow-2xl ring-4 ring-primary/15">
                <IconGripVertical size={14} className="text-primary" />
                <span className="flex-1 truncate font-medium text-foreground">{activeDrag.displayName}</span>
                <span className="text-xs text-muted-foreground">{activeDrag.fieldType}</span>
              </div>
            )}
            {activeDrag?.origin === 'canvas-item' && (() => {
              const item = items.find((i) => i._uid === activeDrag.itemUid)
              if (!item) return null
              if (item.itemType === 'section') {
                return (
                  <div className="flex w-[400px] rotate-1 items-center gap-2 rounded-lg border-2 border-primary bg-white px-3 py-2 text-sm shadow-2xl ring-4 ring-primary/15">
                    <IconGripVertical size={14} className="text-primary" />
                    <div className="h-4 w-1 rounded-full bg-primary" />
                    <span className="font-semibold text-foreground">{item.name}</span>
                  </div>
                )
              }
              const info = getFieldDisplayInfo(item)
              return (
                <div className="flex w-[280px] rotate-2 items-center gap-2 rounded-lg border-2 border-primary bg-white px-3 py-2.5 text-sm shadow-2xl ring-4 ring-primary/15">
                  <IconGripVertical size={14} className="text-primary" />
                  <span className="font-medium text-foreground">{info.name}</span>
                </div>
              )
            })()}
          </DragOverlay>
        </DndContext>
      ) : (
        <InteractionRulesTab layoutId={layoutId} availableFields={availableFieldOptions} />
      )}
    </div>
  )
}

// ── Left Panel ──

function LeftPanel({
  locale,
  scene,
  systemFields,
  customFields,
  metadataFields,
  userFields,
  orgFields,
  isFieldOnCanvas,
  onAddField,
  onAddSection,
  onAddTab,
}: {
  locale: 'zh' | 'en'
  scene: string
  systemFields: UnifiedField[]
  customFields: { id: number; name: string; field_type: import('@/types/field-enums').FieldType }[]
  metadataFields: MetadataFieldDef[]
  userFields: UnifiedField[]
  orgFields: UnifiedField[]
  isFieldOnCanvas: (fieldSource: FieldSource, key: string | null, defId: number | null) => boolean
  onAddField: (fieldSource: FieldSource, source: 'system' | 'custom', field: UnifiedField | MetadataFieldDef | { id: number; name: string; field_type: string }) => void
  onAddSection: () => void
  onAddTab: () => void
}) {
  const isDetail = scene === 'ticket_detail'
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  return (
    <aside className="flex w-[300px] shrink-0 flex-col overflow-y-auto border-r border-border bg-white">
      <div className="p-5">
        <h3 className="text-sm font-semibold text-foreground">{t('fl.leftPanel.title', locale)}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{t('fl.leftPanel.legend', locale)}</p>
      </div>

      <CollapsibleFieldGroup
        title={t('fl.leftPanel.layoutComponents', locale)}
        collapsed={collapsedGroups.has('layout')}
        onToggle={() => toggleGroup('layout')}
      >
        <div className="flex gap-2">
          <button
            onClick={onAddSection}
            className="flex flex-1 items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-accent"
          >
            <IconLayoutDashboard size={16} />
            {t('fl.leftPanel.segment', locale)}
          </button>
          <button
            onClick={onAddTab}
            className="flex flex-1 items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-foreground/80 transition-colors hover:bg-accent"
          >
            <IconLayoutGrid size={16} />
            {t('fl.leftPanel.tabPage', locale)}
          </button>
        </div>
      </CollapsibleFieldGroup>

      {/* Ticket system fields */}
      <CollapsibleFieldGroup
        title={t('fl.leftPanel.systemFields', locale)}
        collapsed={collapsedGroups.has('system')}
        onToggle={() => toggleGroup('system')}
      >
        <div className="flex flex-col gap-1.5">
          {systemFields.map((f) => {
            const onCanvas = isFieldOnCanvas('ticket', f.key, null)
            return (
              <DraggablePoolItem
                key={`sys-${f.key}`}
                id={`pool-sys-${f.key}`}
                dragData={{ origin: 'pool-field', source: 'system', fieldSource: 'ticket', fieldKey: f.key, fieldDefId: null, displayName: f.name, fieldType: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type }}
                onCanvas={onCanvas}
                onClick={() => !onCanvas && onAddField('ticket', 'system', f)}
                name={f.name}
                typeName={(FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type}
              />
            )
          })}
        </div>
      </CollapsibleFieldGroup>

      {/* Ticket custom fields */}
      {customFields.length > 0 && (
        <CollapsibleFieldGroup
          title={t('fl.leftPanel.customFields', locale)}
          collapsed={collapsedGroups.has('custom')}
          onToggle={() => toggleGroup('custom')}
        >
          <div className="flex flex-col gap-1.5">
            {customFields.map((f) => {
              const onCanvas = isFieldOnCanvas('ticket', null, f.id)
              return (
                <DraggablePoolItem
                  key={`cust-${f.id}`}
                  id={`pool-cust-${f.id}`}
                  dragData={{ origin: 'pool-field', source: 'custom', fieldSource: 'ticket', fieldKey: null, fieldDefId: f.id, displayName: f.name, fieldType: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type }}
                  onCanvas={onCanvas}
                  onClick={() => !onCanvas && onAddField('ticket', 'custom', f)}
                  name={f.name}
                  typeName={(FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type}
                />
              )
            })}
          </div>
        </CollapsibleFieldGroup>
      )}

      {/* User fields — ticket_detail only */}
      {isDetail && userFields.length > 0 && (
        <CollapsibleFieldGroup
          title={locale === 'zh' ? '用户字段' : 'User Fields'}
          collapsed={collapsedGroups.has('user')}
          onToggle={() => toggleGroup('user')}
        >
          <p className="mb-2 text-xs text-muted-foreground">{locale === 'zh' ? '引用字段，仅支持只读或隐藏' : 'Reference fields, readonly or hidden only'}</p>
          <div className="flex flex-col gap-1.5">
            {userFields.map((f) => {
              const isSystem = f.source === 'system'
              const onCanvas = isFieldOnCanvas('user', isSystem ? f.key : null, isSystem ? null : f.id ?? null)
              return (
                <DraggablePoolItem
                  key={`user-${f.key ?? f.id}`}
                  id={`pool-user-${f.key ?? f.id}`}
                  dragData={{ origin: 'pool-field', source: isSystem ? 'system' : 'custom', fieldSource: 'user', fieldKey: isSystem ? f.key : null, fieldDefId: isSystem ? null : f.id ?? null, displayName: f.name, fieldType: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type }}
                  onCanvas={onCanvas}
                  onClick={() => !onCanvas && onAddField('user', isSystem ? 'system' : 'custom', f)}
                  name={f.name}
                  typeName={(FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type}
                />
              )
            })}
          </div>
        </CollapsibleFieldGroup>
      )}

      {/* Organization fields — ticket_detail only */}
      {isDetail && orgFields.length > 0 && (
        <CollapsibleFieldGroup
          title={locale === 'zh' ? '组织字段' : 'Organization Fields'}
          collapsed={collapsedGroups.has('organization')}
          onToggle={() => toggleGroup('organization')}
        >
          <p className="mb-2 text-xs text-muted-foreground">{locale === 'zh' ? '引用字段，仅支持只读或隐藏' : 'Reference fields, readonly or hidden only'}</p>
          <div className="flex flex-col gap-1.5">
            {orgFields.map((f) => {
              const isSystem = f.source === 'system'
              const onCanvas = isFieldOnCanvas('organization', isSystem ? f.key : null, isSystem ? null : f.id ?? null)
              return (
                <DraggablePoolItem
                  key={`org-${f.key ?? f.id}`}
                  id={`pool-org-${f.key ?? f.id}`}
                  dragData={{ origin: 'pool-field', source: isSystem ? 'system' : 'custom', fieldSource: 'organization', fieldKey: isSystem ? f.key : null, fieldDefId: isSystem ? null : f.id ?? null, displayName: f.name, fieldType: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type }}
                  onCanvas={onCanvas}
                  onClick={() => !onCanvas && onAddField('organization', isSystem ? 'system' : 'custom', f)}
                  name={f.name}
                  typeName={(FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type}
                />
              )
            })}
          </div>
        </CollapsibleFieldGroup>
      )}

      {/* Metadata fields — ticket_detail only */}
      {isDetail && metadataFields.length > 0 && (
        <CollapsibleFieldGroup
          title={locale === 'zh' ? '元数据字段' : 'Metadata Fields'}
          collapsed={collapsedGroups.has('metadata')}
          onToggle={() => toggleGroup('metadata')}
        >
          <div className="flex flex-col gap-1.5">
            {metadataFields.map((f) => {
              const onCanvas = isFieldOnCanvas('ticket_metadata', f.key, null)
              const name = locale === 'zh' ? f.name_zh : f.name_en
              return (
                <DraggablePoolItem
                  key={`meta-${f.key}`}
                  id={`pool-meta-${f.key}`}
                  dragData={{ origin: 'pool-field', source: 'system', fieldSource: 'ticket_metadata', fieldKey: f.key, fieldDefId: null, displayName: name, fieldType: (FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type }}
                  onCanvas={onCanvas}
                  onClick={() => !onCanvas && onAddField('ticket_metadata', 'system', f)}
                  name={name}
                  typeName={(FIELD_TYPE_LABELS as Record<string, Record<string, string>>)[f.field_type]?.[locale] ?? f.field_type}
                />
              )
            })}
          </div>
        </CollapsibleFieldGroup>
      )}
    </aside>
  )
}

function CollapsibleFieldGroup({
  title,
  collapsed,
  onToggle,
  children,
}: {
  title: string
  collapsed: boolean
  onToggle: () => void
  children: ReactNode
}) {
  return (
    <div className="px-5 pb-4">
      <button
        type="button"
        aria-expanded={!collapsed}
        onClick={onToggle}
        className="mb-2 flex w-full items-center justify-between text-xs font-semibold uppercase text-muted-foreground"
      >
        <span>{title}</span>
        {collapsed ? <IconChevronRight size={14} /> : <IconChevronDown size={14} />}
      </button>
      {!collapsed && children}
    </div>
  )
}

function DraggablePoolItem({ id, dragData, onCanvas, onClick, name, typeName }: {
  id: string; dragData: PoolFieldDragData; onCanvas: boolean; onClick: () => void; name: string; typeName: string
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id, data: dragData, disabled: onCanvas })
  return (
    <div
      ref={setNodeRef}
      onClick={onClick}
      className={cn(
        'flex cursor-grab items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors',
        onCanvas ? 'cursor-default border-info/40 bg-info/10 text-foreground/80' : 'border-border bg-white text-foreground/80 hover:bg-accent',
        isDragging && 'opacity-40'
      )}
      {...listeners}
      {...attributes}
    >
      <IconGripVertical size={14} className="shrink-0 text-border" />
      <span className="flex-1 truncate">{name}</span>
      <span className="shrink-0 text-xs text-muted-foreground">{typeName}</span>
    </div>
  )
}

// ── Canvas Area ──

function CanvasArea({
  locale,
  tabs,
  itemsByTab,
  selection,
  columnsPerRow,
  labelPosition,
  dropTarget,
  isDragging,
  onSelectTab,
  onSelectField,
  onSelectSection,
  onSelectForm,
  onRemoveItem,
  onRemoveTab,
  getFieldDisplayInfo,
}: {
  locale: 'zh' | 'en'
  tabs: LocalTab[]
  itemsByTab: Map<string, CanvasItem[]>
  selection: Selection
  columnsPerRow: number
  labelPosition: string
  dropTarget: DropTarget | null
  isDragging: boolean
  onSelectTab: (idx: number) => void
  onSelectField: (uid: string) => void
  onSelectSection: (uid: string) => void
  onSelectForm: () => void
  onRemoveItem: (uid: string) => void
  onRemoveTab: (tabUid: string) => void
  getFieldDisplayInfo: (f: FieldItem) => { name: string; type: string }
}) {
  return (
    <div
      className="flex flex-1 flex-col gap-5 overflow-y-auto bg-accent p-6"
      onClick={(e) => { if (e.target === e.currentTarget) onSelectForm() }}
    >
      {tabs.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-muted-foreground">{t('fl.canvas.empty', locale)}</p>
        </div>
      ) : (
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
          {tabs.map((tb, idx) => {
            const tabItems = itemsByTab.get(tb._uid) ?? []
            const isTabSelected = selection.type === 'tab' && selection.tabUid === tb._uid
            return (
              <TabCard
                key={tb._uid}
                tab={tb}
                tabIdx={idx}
                tabItems={tabItems}
                isSelected={isTabSelected}
                canDelete={tabs.length > 1}
                selection={selection}
                columnsPerRow={columnsPerRow}
                labelPosition={labelPosition}
                locale={locale}
                dropTarget={dropTarget}
                isDragging={isDragging}
                onSelectTab={() => onSelectTab(idx)}
                onSelectField={onSelectField}
                onSelectSection={onSelectSection}
                onRemoveItem={onRemoveItem}
                onRemoveTab={() => onRemoveTab(tb._uid)}
                getFieldDisplayInfo={getFieldDisplayInfo}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function TabCard({
  tab,
  tabIdx: _tabIdx,
  tabItems,
  isSelected,
  canDelete,
  selection,
  columnsPerRow,
  labelPosition,
  locale,
  dropTarget,
  isDragging,
  onSelectTab,
  onSelectField,
  onSelectSection,
  onRemoveItem,
  onRemoveTab,
  getFieldDisplayInfo,
}: {
  tab: LocalTab
  tabIdx: number
  tabItems: CanvasItem[]
  isSelected: boolean
  canDelete: boolean
  selection: Selection
  columnsPerRow: number
  labelPosition: string
  locale: 'zh' | 'en'
  dropTarget: DropTarget | null
  isDragging: boolean
  onSelectTab: () => void
  onSelectField: (uid: string) => void
  onSelectSection: (uid: string) => void
  onRemoveItem: (uid: string) => void
  onRemoveTab: () => void
  getFieldDisplayInfo: (f: FieldItem) => { name: string; type: string }
}) {
  // Tab-level droppable acts as a fallback target so the card itself can catch drops in empty space.
  const { setNodeRef: setDropRef } = useDroppable({ id: `tab-drop-${tab._uid}` })
  const rows = useMemo(() => buildRows(tabItems, columnsPerRow), [tabItems, columnsPerRow])
  const isEmpty = rows.length === 0

  return (
    <div
      ref={setDropRef}
      onClick={(e) => { e.stopPropagation(); onSelectTab() }}
      className={cn(
        'rounded-[10px] border bg-white shadow-sm transition-colors',
        isSelected ? 'border-2 border-ring' : 'border-border'
      )}
    >
      {/* Tab card header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <span className="text-sm font-semibold text-foreground">{tab.name}</span>
        {canDelete && (
          <button
            onClick={(e) => { e.stopPropagation(); onRemoveTab() }}
            className="text-border transition-colors hover:text-destructive"
          >
            <IconX size={16} />
          </button>
        )}
      </div>

      <div className="p-5">
        {/* Top-of-tab inter-row zone (also handles the fully-empty tab case) */}
        <InterRowDropZone
          tabUid={tab._uid}
          afterRowIdx={-1}
          dropTarget={dropTarget}
          isDragging={isDragging}
          isEmpty={isEmpty}
          locale={locale}
        />

        {rows.map((row, rIdx) => (
          <Fragment key={row.kind === 'section' ? row.item._uid : `r-${rIdx}-${row.items.map((i) => i._uid).join('_')}`}>
            {row.kind === 'section' ? (
              <SectionDividerRow
                item={row.item}
                fieldCount={countSectionFields(tabItems, row.item._uid)}
                isSelected={selection.type === 'section' && selection.uid === row.item._uid}
                locale={locale}
                dropTarget={dropTarget}
                onSelect={() => onSelectSection(row.item._uid)}
                onRemove={() => onRemoveItem(row.item._uid)}
              />
            ) : (
              <RowGrid
                tabUid={tab._uid}
                rowIdx={rIdx}
                row={row}
                columnsPerRow={columnsPerRow}
                labelPosition={labelPosition}
                selection={selection}
                dropTarget={dropTarget}
                isDragging={isDragging}
                onSelectField={onSelectField}
                onRemoveItem={onRemoveItem}
                getFieldDisplayInfo={getFieldDisplayInfo}
              />
            )}
            <InterRowDropZone
              tabUid={tab._uid}
              afterRowIdx={rIdx}
              dropTarget={dropTarget}
              isDragging={isDragging}
              locale={locale}
            />
          </Fragment>
        ))}
      </div>
    </div>
  )
}

// ── A row of fields rendered as a grid; pads remaining cells with an EndOfRow drop zone. ──

function RowGrid({
  tabUid,
  rowIdx,
  row,
  columnsPerRow,
  labelPosition,
  selection,
  dropTarget,
  isDragging,
  onSelectField,
  onRemoveItem,
  getFieldDisplayInfo,
}: {
  tabUid: string
  rowIdx: number
  row: { kind: 'fields'; items: FieldItem[]; colsUsed: number }
  columnsPerRow: number
  labelPosition: string
  selection: Selection
  dropTarget: DropTarget | null
  isDragging: boolean
  onSelectField: (uid: string) => void
  onRemoveItem: (uid: string) => void
  getFieldDisplayInfo: (f: FieldItem) => { name: string; type: string }
}) {
  const remaining = columnsPerRow - row.colsUsed
  const showRowEnd = remaining > 0

  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${columnsPerRow}, 1fr)` }}>
      {row.items.map((item) => {
        const isSel = selection.type === 'field' && selection.uid === item._uid
        const info = getFieldDisplayInfo(item)
        const dropPos: 'before' | 'after' | null =
          dropTarget && (dropTarget.kind === 'before' || dropTarget.kind === 'after') && dropTarget.refUid === item._uid
            ? dropTarget.kind
            : null
        return (
          <DraggableFieldCell
            key={item._uid}
            uid={item._uid}
            name={info.name}
            fieldSource={item.field_source}
            columnSpan={item.column_span}
            columnsPerRow={columnsPerRow}
            labelPosition={labelPosition}
            isSelected={isSel}
            isReadonly={item.default_state === 'readonly'}
            dropPosition={dropPos}
            dropDisabled={dropTarget?.disabled === true}
            onClick={() => onSelectField(item._uid)}
            onRemove={() => onRemoveItem(item._uid)}
          />
        )
      })}
      {showRowEnd && (
        <EndOfRowDropZone
          tabUid={tabUid}
          rowIdx={rowIdx}
          remaining={remaining}
          dropTarget={dropTarget}
          isDragging={isDragging}
        />
      )}
    </div>
  )
}

// ── Inter-row drop zone (between rows / above first row / below last row) ──

function InterRowDropZone({
  tabUid,
  afterRowIdx,
  dropTarget,
  isDragging,
  isEmpty = false,
  locale,
}: {
  tabUid: string
  afterRowIdx: number
  dropTarget: DropTarget | null
  isDragging: boolean
  isEmpty?: boolean
  locale: 'zh' | 'en'
}) {
  const id = `inter-row-${tabUid}-${afterRowIdx}`
  const { setNodeRef } = useDroppable({ id })
  const isActive =
    dropTarget?.kind === 'inter-row' && dropTarget.tabUid === tabUid && dropTarget.afterRowIdx === afterRowIdx
  const disabled = isActive && dropTarget?.disabled === true

  if (isEmpty) {
    return (
      <div
        ref={setNodeRef}
        className={cn(
          'flex min-h-[120px] items-center justify-center rounded-lg border-2 border-dashed text-xs transition-colors',
          isActive && !disabled && 'border-primary bg-primary/5 text-primary',
          isActive && disabled && 'border-destructive bg-destructive/5 text-destructive',
          !isActive && 'border-border text-muted-foreground'
        )}
      >
        {isActive && disabled
          ? (locale === 'zh' ? '该字段已存在' : 'Field already added')
          : isActive
            ? (locale === 'zh' ? '释放以添加到此处' : 'Release to add here')
            : (locale === 'zh' ? '从左侧拖动字段到此处' : 'Drag a field from the left')}
      </div>
    )
  }

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'transition-all',
        // Reserve a small hit area only while dragging so it does not affect the static layout.
        isDragging ? 'h-[10px] my-0.5' : 'h-0 overflow-hidden',
        isActive && !disabled && 'h-[14px] rounded-full bg-primary/10 ring-2 ring-primary/60',
        isActive && disabled && 'h-[14px] rounded-full bg-destructive/10 ring-2 ring-destructive/60'
      )}
    />
  )
}

// ── End-of-row drop zone (fills remaining grid cells of a partially used row) ──

function EndOfRowDropZone({
  tabUid,
  rowIdx,
  remaining,
  dropTarget,
  isDragging,
}: {
  tabUid: string
  rowIdx: number
  remaining: number
  dropTarget: DropTarget | null
  isDragging: boolean
}) {
  const id = `row-end-${tabUid}-${rowIdx}`
  const { setNodeRef } = useDroppable({ id })
  const isActive = dropTarget?.kind === 'row-end' && dropTarget.tabUid === tabUid && dropTarget.rowIdx === rowIdx
  const disabled = isActive && dropTarget?.disabled === true

  return (
    <div
      ref={setNodeRef}
      style={{ gridColumn: `span ${remaining}` }}
      className={cn(
        'rounded-lg border-2 border-dashed transition-colors',
        isDragging ? 'border-border/40' : 'border-transparent',
        isActive && !disabled && 'border-primary bg-primary/5',
        isActive && disabled && 'border-destructive bg-destructive/5'
      )}
    />
  )
}

// ── Drop indicator line, drawn as an absolute overlay around the hovered item ──

function DropLine({
  position,
  disabled,
}: {
  position: 'left' | 'right' | 'top' | 'bottom'
  disabled: boolean
}) {
  const positionClass: Record<string, string> = {
    left: 'left-[-7px] top-0 bottom-0 w-[3px]',
    right: 'right-[-7px] top-0 bottom-0 w-[3px]',
    top: 'left-0 right-0 top-[-7px] h-[3px]',
    bottom: 'left-0 right-0 bottom-[-7px] h-[3px]',
  }
  return (
    <div
      className={cn(
        'pointer-events-none absolute z-20 rounded-full',
        positionClass[position],
        disabled ? 'bg-destructive shadow-[0_0_0_2px_rgba(239,68,68,0.2)]' : 'bg-primary shadow-[0_0_0_2px_rgba(59,130,246,0.25)]'
      )}
    />
  )
}

// ── Section divider rendered inline (not as a grid item) ──

function SectionDividerRow({
  item,
  fieldCount,
  isSelected,
  locale,
  dropTarget,
  onSelect,
  onRemove,
}: {
  item: SectionItem
  fieldCount: number
  isSelected: boolean
  locale: 'zh' | 'en'
  dropTarget: DropTarget | null
  onSelect: () => void
  onRemove: () => void
}) {
  const { setNodeRef: setDragRef, attributes, listeners, isDragging } = useDraggable({
    id: item._uid,
    data: { origin: 'canvas-item', itemUid: item._uid } as CanvasItemDragData,
  })
  const { setNodeRef: setDropRef } = useDroppable({ id: item._uid })
  const setRef = (node: HTMLElement | null) => {
    setDragRef(node)
    setDropRef(node)
  }

  const dropPos: 'before' | 'after' | null =
    dropTarget && (dropTarget.kind === 'before' || dropTarget.kind === 'after') && dropTarget.refUid === item._uid
      ? dropTarget.kind
      : null
  const dropDisabled = dropTarget?.disabled === true

  // While dragging, collapse to a single placeholder line so it never coexists visually with the DragOverlay.
  if (isDragging) {
    return (
      <div className="my-2 h-[36px] rounded-lg border-2 border-dashed border-primary/40 bg-primary/5" />
    )
  }

  return (
    <div ref={setRef} className="relative">
      {dropPos === 'before' && <DropLine position="top" disabled={dropDisabled} />}
      {dropPos === 'after' && <DropLine position="bottom" disabled={dropDisabled} />}
      <div
        onClick={(e) => { e.stopPropagation(); onSelect() }}
        className={cn(
          'group flex cursor-pointer items-center gap-3 rounded-lg px-1 py-2 transition-colors',
          isSelected ? 'bg-info/10' : 'hover:bg-accent/50'
        )}
      >
        <div className="shrink-0 cursor-grab touch-none text-border" {...listeners} {...attributes}>
          <IconGripVertical size={14} />
        </div>
        <div className={cn('h-5 w-1 shrink-0 rounded-full', isSelected ? 'bg-ring' : 'bg-primary')} />
        <span className="text-sm font-semibold text-foreground">{item.name}</span>
        <div className="flex-1" />
        <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {t('fl.canvas.fieldCount', locale, { n: fieldCount })}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); onRemove() }}
          className="shrink-0 text-border opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
        >
          <IconX size={14} />
        </button>
      </div>
    </div>
  )
}

// ── Field cell: pure draggable+droppable, with explicit drop indicator and collapsed placeholder while dragging. ──

const SOURCE_TAG: Record<string, { zh: string; en: string; color: string }> = {
  user: { zh: '用户', en: 'User', color: 'bg-purple-50 text-purple-600' },
  organization: { zh: '组织', en: 'Org', color: 'bg-amber-50 text-amber-600' },
  ticket_metadata: { zh: '元数据', en: 'Meta', color: 'bg-teal-50 text-teal-600' },
}

function DraggableFieldCell({
  uid: fieldUid,
  name,
  fieldSource,
  columnSpan,
  columnsPerRow,
  labelPosition,
  isSelected,
  isReadonly,
  dropPosition,
  dropDisabled,
  onClick,
  onRemove,
}: {
  uid: string
  name: string
  fieldSource: FieldSource
  columnSpan: number
  columnsPerRow: number
  labelPosition: string
  isSelected: boolean
  isReadonly: boolean
  dropPosition: 'before' | 'after' | null
  dropDisabled: boolean
  onClick: () => void
  onRemove: () => void
}) {
  const { locale } = useLocaleStore()
  const { setNodeRef: setDragRef, attributes, listeners, isDragging } = useDraggable({
    id: fieldUid,
    data: { origin: 'canvas-item', itemUid: fieldUid } as CanvasItemDragData,
  })
  const { setNodeRef: setDropRef } = useDroppable({ id: fieldUid })
  const setRef = (node: HTMLElement | null) => {
    setDragRef(node)
    setDropRef(node)
  }

  const effectiveSpan = Math.min(columnSpan, columnsPerRow)
  const wrapperStyle: CSSProperties = { gridColumn: `span ${effectiveSpan}` }
  const isTop = labelPosition === 'top'
  const tag = SOURCE_TAG[fieldSource]

  // Collapse to a dashed placeholder while dragging so it can't be confused with the DragOverlay.
  if (isDragging) {
    return (
      <div ref={setRef} style={wrapperStyle} className="relative">
        <div className={cn('rounded-lg border-2 border-dashed border-primary/40 bg-primary/5', isTop ? 'h-[68px]' : 'h-[44px]')} />
      </div>
    )
  }

  return (
    <div ref={setRef} style={wrapperStyle} className="relative">
      {dropPosition === 'before' && <DropLine position="left" disabled={dropDisabled} />}
      {dropPosition === 'after' && <DropLine position="right" disabled={dropDisabled} />}
      <div
        onClick={(e) => { e.stopPropagation(); onClick() }}
        className={cn(
          'group cursor-pointer rounded-lg border px-3 py-2.5 transition-colors',
          isTop ? 'flex flex-col gap-1.5' : 'flex items-center gap-2',
          isSelected ? 'border-ring border-2 bg-info/10' : 'border-border hover:border-input'
        )}
      >
        {isTop ? (
          <>
            <div className="flex items-center gap-1.5">
              <div className="shrink-0 cursor-grab touch-none" {...listeners} {...attributes}>
                <IconGripVertical size={14} className="text-border" />
              </div>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{name}</span>
              {tag && (
                <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium', tag.color)}>
                  {locale === 'zh' ? tag.zh : tag.en}
                </span>
              )}
              <button
                onClick={(e) => { e.stopPropagation(); onRemove() }}
                className="shrink-0 text-border opacity-0 transition-opacity group-hover:opacity-100 hover:text-muted-foreground"
              >
                <IconX size={14} />
              </button>
            </div>
            <div className={cn('h-8 w-full rounded border', isReadonly ? 'border-border bg-accent' : 'border-border bg-white')} />
          </>
        ) : (
          <>
            <div className="shrink-0 cursor-grab touch-none" {...listeners} {...attributes}>
              <IconGripVertical size={14} className="text-border" />
            </div>
            <span className="w-28 shrink-0 truncate text-sm text-foreground">{name}</span>
            {tag && (
              <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium', tag.color)}>
                {locale === 'zh' ? tag.zh : tag.en}
              </span>
            )}
            <div className={cn('h-8 flex-1 rounded border', isReadonly ? 'border-border bg-accent' : 'border-border bg-white')} />
            <button
              onClick={(e) => { e.stopPropagation(); onRemove() }}
              className="shrink-0 text-border opacity-0 transition-opacity group-hover:opacity-100 hover:text-muted-foreground"
            >
              <IconX size={14} />
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ── Right Panel ──

function RightPanel({
  locale,
  scene,
  selection,
  columnsPerRow,
  labelPosition,
  selectedField,
  selectedSection,
  tabs,
  onColumnsChange,
  onLabelPositionChange,
  onFieldStateChange,
  onFieldSpanChange,
  onSectionNameChange,
  onTabNameChange,
  onRemoveTab,
  getFieldDisplayInfo,
}: {
  locale: 'zh' | 'en'
  scene: string
  selection: Selection
  columnsPerRow: number
  labelPosition: string
  selectedField: FieldItem | null
  selectedSection: SectionItem | null
  tabs: LocalTab[]
  onColumnsChange: (v: number) => void
  onLabelPositionChange: (v: string) => void
  onFieldStateChange: (uid: string, state: string) => void
  onFieldSpanChange: (uid: string, span: number) => void
  onSectionNameChange: (uid: string, name: string) => void
  onTabNameChange: (tabUid: string, name: string) => void
  onRemoveTab: (tabUid: string) => void
  getFieldDisplayInfo: (f: FieldItem) => { name: string; type: string }
}) {
  const [deleteTabTarget, setDeleteTabTarget] = useState<LocalTab | null>(null)

  return (
    <aside className="flex w-[360px] shrink-0 flex-col overflow-y-auto border-l border-border bg-white">
      <div className="p-5">
        {selection.type === 'form' && (
          <FormProperties locale={locale} columnsPerRow={columnsPerRow} labelPosition={labelPosition} onColumnsChange={onColumnsChange} onLabelPositionChange={onLabelPositionChange} />
        )}

        {selection.type === 'field' && selectedField && (
          <FieldProperties locale={locale} field={selectedField} columnsPerRow={columnsPerRow} onStateChange={(s) => onFieldStateChange(selectedField._uid, s)} onSpanChange={(s) => onFieldSpanChange(selectedField._uid, s)} getFieldDisplayInfo={getFieldDisplayInfo} />
        )}

        {selection.type === 'section' && selectedSection && (
          <SectionProperties locale={locale} name={selectedSection.name} onNameChange={(name) => onSectionNameChange(selectedSection._uid, name)} />
        )}

        {selection.type === 'tab' && (() => {
          const selectedTab = tabs.find((tb) => tb._uid === selection.tabUid)
          if (!selectedTab) return null
          return (
            <SingleTabProperties
              locale={locale}
              tab={selectedTab}
              canDelete={tabs.length > 1}
              onTabNameChange={(name) => onTabNameChange(selectedTab._uid, name)}
              onRemoveTab={() => {
                if (tabs.length > 1) setDeleteTabTarget(selectedTab)
              }}
            />
          )
        })()}
      </div>

      {deleteTabTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-[420px] rounded-xl bg-white p-6">
            <h2 className="text-lg font-semibold text-foreground">{t('fl.deleteTab.title', locale)}</h2>
            <p className="mt-3 text-sm text-muted-foreground">
              {t('fl.deleteTab.confirm', locale, { name: deleteTabTarget.name })}
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button onClick={() => setDeleteTabTarget(null)} className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent">
                {t('fl.deleteTab.cancel', locale)}
              </button>
              <button
                onClick={() => { onRemoveTab(deleteTabTarget._uid); setDeleteTabTarget(null) }}
                className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white transition-colors hover:bg-destructive/80"
              >
                {t('fl.deleteTab.ok', locale)}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}

// ── Sub-panels ──

function FormProperties({ locale, columnsPerRow, labelPosition, onColumnsChange, onLabelPositionChange }: {
  locale: 'zh' | 'en'; columnsPerRow: number; labelPosition: string; onColumnsChange: (v: number) => void; onLabelPositionChange: (v: string) => void
}) {
  return (
    <div className="flex flex-col gap-5">
      <h3 className="text-sm font-semibold text-foreground">{t('fl.rightPanel.formStyle', locale)}</h3>
      <div>
        <label className="mb-2 block text-sm text-foreground/80">{t('fl.rightPanel.columnsPerRow', locale)}</label>
        <div className="flex gap-1.5">
          {[1, 2, 3, 4].map((n) => (
            <button key={n} onClick={() => onColumnsChange(n)} className={cn('flex h-9 w-10 items-center justify-center rounded-lg border text-sm font-medium transition-colors', columnsPerRow === n ? 'border-foreground bg-primary text-white' : 'border-border bg-white text-foreground/80 hover:bg-accent')}>
              {n}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="mb-2 block text-sm text-foreground/80">{t('fl.rightPanel.labelPosition', locale)}</label>
        <select value={labelPosition} onChange={(e) => onLabelPositionChange(e.target.value)} className="h-9 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground outline-none focus:border-ring">
          <option value="top">{t('fl.rightPanel.labelPosition.top', locale)}</option>
          <option value="left">{t('fl.rightPanel.labelPosition.left', locale)}</option>
        </select>
      </div>
    </div>
  )
}

function FieldProperties({ locale, field, columnsPerRow, onStateChange, onSpanChange, getFieldDisplayInfo }: {
  locale: 'zh' | 'en'; field: FieldItem; columnsPerRow: number; onStateChange: (s: string) => void; onSpanChange: (s: number) => void; getFieldDisplayInfo: (f: FieldItem) => { name: string; type: string }
}) {
  const info = getFieldDisplayInfo(field)
  const isRefField = field.field_source === 'user' || field.field_source === 'organization' || field.field_source === 'ticket_metadata'

  const stateOptions = isRefField
    ? [
        { value: 'readonly', label: t('fl.state.readonly', locale) },
        { value: 'hidden', label: t('fl.state.hidden', locale) },
      ]
    : [
        { value: 'readonly', label: t('fl.state.readonly', locale) },
        { value: 'required', label: t('fl.state.required', locale) },
        { value: 'optional', label: t('fl.state.optional', locale) },
        { value: 'hidden', label: t('fl.state.hidden', locale) },
      ]

  const sourceLabel = field.field_source === 'user'
    ? (locale === 'zh' ? '用户字段' : 'User Field')
    : field.field_source === 'organization'
      ? (locale === 'zh' ? '组织字段' : 'Org Field')
      : field.field_source === 'ticket_metadata'
        ? (locale === 'zh' ? '元数据字段' : 'Metadata Field')
        : null

  return (
    <div className="flex flex-col gap-5">
      <h3 className="text-sm font-semibold text-foreground">{t('fl.rightPanel.fieldProperties', locale)}</h3>
      <p className="text-sm text-muted-foreground">{info.name} · {info.type}</p>
      {sourceLabel && (
        <span className="inline-flex w-fit items-center rounded-full bg-info/10 px-2.5 py-0.5 text-xs font-medium text-info">
          {sourceLabel}
        </span>
      )}
      {isRefField && (
        <p className="text-xs text-muted-foreground">
          {locale === 'zh' ? '引用字段，仅支持「只读」和「隐藏」两种状态' : 'Reference field, only supports "readonly" and "hidden" states'}
        </p>
      )}
      <div>
        <label className="mb-1 block text-sm text-foreground/80">{t('fl.rightPanel.defaultState', locale)}</label>
        <p className="mb-2 text-xs text-muted-foreground">{t('fl.rightPanel.defaultState.hint', locale)}</p>
        <select value={field.default_state} onChange={(e) => onStateChange(e.target.value)} className="h-9 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground outline-none focus:border-ring">
          {stateOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-sm text-foreground/80">{t('fl.rightPanel.columnSpan', locale)}</label>
        <p className="mb-2 text-xs text-muted-foreground">{t('fl.rightPanel.columnSpan.hint', locale, { n: columnsPerRow })}</p>
        <div className="flex gap-1.5">
          {Array.from({ length: columnsPerRow }, (_, i) => i + 1).map((n) => (
            <button key={n} onClick={() => onSpanChange(n)} className={cn('flex h-9 items-center justify-center rounded-lg border px-3 text-sm font-medium transition-colors', field.column_span === n ? 'border-foreground bg-primary text-white' : 'border-border bg-white text-foreground/80 hover:bg-accent')}>
              {n} / {columnsPerRow}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function SectionProperties({ locale, name, onNameChange }: {
  locale: 'zh' | 'en'; name: string; onNameChange: (name: string) => void
}) {
  return (
    <div className="flex flex-col gap-5">
      <h3 className="text-sm font-semibold text-foreground">{t('fl.rightPanel.sectionProperties', locale)}</h3>
      <div>
        <label className="mb-2 block text-sm text-foreground/80">{t('fl.rightPanel.sectionName', locale)}</label>
        <input type="text" value={name} onChange={(e) => onNameChange(e.target.value)} placeholder={t('fl.rightPanel.sectionName.placeholder', locale)} className="h-9 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground outline-none focus:border-ring" />
      </div>
    </div>
  )
}

function SingleTabProperties({ locale, tab, canDelete, onTabNameChange, onRemoveTab }: {
  locale: 'zh' | 'en'; tab: LocalTab; canDelete: boolean; onTabNameChange: (name: string) => void; onRemoveTab: () => void
}) {
  return (
    <div className="flex flex-col gap-5">
      <h3 className="text-sm font-semibold text-foreground">{t('fl.rightPanel.tabProperties', locale)}</h3>
      <div>
        <label className="mb-2 block text-sm text-foreground/80">{locale === 'zh' ? '标签页名称' : 'Tab Name'}</label>
        <input
          type="text"
          value={tab.name}
          onChange={(e) => onTabNameChange(e.target.value)}
          className="h-9 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground outline-none focus:border-ring"
        />
      </div>
      {canDelete && (
        <button
          onClick={onRemoveTab}
          className="flex items-center gap-1 text-sm font-medium text-destructive transition-colors hover:text-destructive/80"
        >
          <IconX size={16} />
          {locale === 'zh' ? '删除此标签页' : 'Delete this tab'}
        </button>
      )}
      {!canDelete && <p className="text-xs text-muted-foreground">{t('fl.rightPanel.tabMinHint', locale)}</p>}
    </div>
  )
}
