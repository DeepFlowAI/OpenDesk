'use client'

import { useState, useEffect, useMemo, useCallback, type CSSProperties } from 'react'
import {
  IconGripVertical,
  IconPencil,
  IconTrash,
  IconPlus,
  IconArrowLeft,
  IconSearch,
  IconRefresh,
  IconLoader2,
} from '@tabler/icons-react'
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
import { Switch } from '@/components/ui/switch'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  SortableFieldRowsContext,
  SortableFieldTableRow,
  DefaultSortDragHandle,
} from '@/components/admin/sortable-field-table'
import {
  useUserViews,
  useCreateUserView,
  useUpdateUserView,
  useDeleteUserView,
  useToggleUserView,
  useSortUserViews,
} from '@/service/use-user-views'
import { useUnifiedFields } from '@/service/use-field-definitions'
import type { UserView, ConditionItem, ColumnConfigItem } from '@/models/user-view'
import type { UnifiedField } from '@/models/field-definition'
import {
  FilterValueEditor,
  NO_VALUE_OPS,
  operatorsForFieldType,
  valueShape,
} from '@/components/filter'

// ── Unified field identifier helpers ──
// System fields have key (string) but id=null; custom fields have id (number) but key=null.
// We use a string uid to uniquely identify both: "id:123" or "key:some_key".

function fieldUid(f: UnifiedField): string {
  if (f.id != null) return `id:${f.id}`
  if (f.key != null) return `key:${f.key}`
  return ''
}

function conditionFieldUid(c: ConditionItem): string {
  if (c.field_id != null) return `id:${c.field_id}`
  if (c.field_key != null) return `key:${c.field_key}`
  return ''
}

function columnFieldUid(c: ColumnConfigItem): string {
  if (c.field_id != null) return `id:${c.field_id}`
  if (c.field_key != null) return `key:${c.field_key}`
  return ''
}

function parseUidToConditionPatch(uid: string): Pick<ConditionItem, 'field_id' | 'field_key'> {
  if (uid.startsWith('id:')) return { field_id: Number(uid.slice(3)), field_key: null }
  if (uid.startsWith('key:')) return { field_id: null, field_key: uid.slice(4) }
  return { field_id: null, field_key: null }
}

function parseUidToColumnItem(uid: string, visible: boolean, sortOrder: number): ColumnConfigItem {
  if (uid.startsWith('id:')) return { field_id: Number(uid.slice(3)), field_key: null, visible, sort_order: sortOrder }
  if (uid.startsWith('key:')) return { field_id: null, field_key: uid.slice(4), visible, sort_order: sortOrder }
  return { field_id: null, field_key: null, visible, sort_order: sortOrder }
}

const GROUPABLE_TYPES = new Set(['single_select', 'multi_select'])

function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ── Main Page ──

export default function UserViewsPage() {
  const { locale } = useLocaleStore()
  const { data, isLoading, refetch } = useUserViews({ page: 1, per_page: 200 })
  const items = data?.items ?? []

  const [sorting, setSorting] = useState(false)
  const [sortedItems, setSortedItems] = useState<UserView[]>([])
  const [drawerView, setDrawerView] = useState<UserView | null | 'new'>(null)
  const [confirmDelete, setConfirmDelete] = useState<UserView | null>(null)

  const createView = useCreateUserView()
  const deleteView = useDeleteUserView()
  const toggleView = useToggleUserView()
  const sortViews = useSortUserViews()

  useEffect(() => {
    if (sorting) setSortedItems([...items])
  }, [sorting]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleNewView = async () => {
    try {
      const created = await createView.mutateAsync({ name: t('uv.defaultName', locale) })
      await refetch()
      setDrawerView(created)
    } catch { /* handled by base */ }
  }

  const handleToggle = async (view: UserView, checked: boolean) => {
    await toggleView.mutateAsync({ id: view.id, data: { is_enabled: checked } })
  }

  const handleConfirmDelete = async () => {
    if (!confirmDelete) return
    await deleteView.mutateAsync(confirmDelete.id)
    setConfirmDelete(null)
  }

  const enterSortMode = () => {
    setSortedItems([...items])
    setSorting(true)
  }

  const cancelSort = () => setSorting(false)

  const confirmSort = async () => {
    const payload = sortedItems.map((item, idx) => ({ id: item.id, sort_order: idx + 1 }))
    await sortViews.mutateAsync({ items: payload })
    setSorting(false)
    refetch()
  }

  const displayItems = sorting ? sortedItems : items

  const viewSortIds = useMemo(() => sortedItems.map((v) => String(v.id)), [sortedItems])

  return (
    <div className="flex flex-col gap-4">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">{t('uv.title', locale)}</h1>
        <div className="flex items-center gap-2">
          {sorting ? (
            <>
              <button
                onClick={cancelSort}
                className="flex h-10 items-center rounded-lg border border-border bg-white px-4 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                {t('uv.cancel', locale)}
              </button>
              <button
                onClick={confirmSort}
                disabled={sortViews.isPending}
                className="flex h-10 items-center rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
              >
                {t('uv.confirm', locale)}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={enterSortMode}
                className="flex h-10 items-center rounded-lg border border-border bg-white px-4 text-sm font-medium text-foreground transition-colors hover:bg-accent"
              >
                {t('uv.sort', locale)}
              </button>
              <button
                onClick={handleNewView}
                disabled={createView.isPending}
                className="flex h-10 items-center rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
              >
                {t('uv.newView', locale)}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-border">
        {/* Header row */}
        <div className="flex h-12 items-center gap-6 bg-muted px-6">
          <div className="w-[72px] text-sm font-semibold text-foreground/80">{t('uv.col.index', locale)}</div>
          <div className="flex-1 text-sm font-semibold text-foreground/80">{t('uv.col.name', locale)}</div>
          <div className="w-[160px] text-sm font-semibold text-foreground/80">{t('uv.col.updatedAt', locale)}</div>
          <div className="flex w-[72px] justify-center text-sm font-semibold text-foreground/80">{t('uv.col.enabled', locale)}</div>
          <div className="w-[80px] text-sm font-semibold text-foreground/80">{t('uv.col.actions', locale)}</div>
        </div>

        {isLoading && (
          <div className="flex h-40 items-center justify-center">
            <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
          </div>
        )}

        {!isLoading && displayItems.length === 0 && (
          <div className="flex h-40 flex-col items-center justify-center gap-3">
            <p className="text-sm text-muted-foreground">{t('uv.empty', locale)}</p>
            <button
              onClick={handleNewView}
              className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/80"
            >
              <IconPlus size={16} />
              {t('uv.newView', locale)}
            </button>
          </div>
        )}

        {!isLoading && displayItems.length > 0 && (sorting ? (
          <SortableFieldRowsContext
            itemIds={viewSortIds}
            onReorderIndices={(from, to) =>
              setSortedItems((prev) => arrayMove(prev, from, to))
            }
          >
            {sortedItems.map((view) => (
              <SortableFieldTableRow
                key={view.id}
                id={String(view.id)}
                className="flex h-14 items-center gap-6 border-b border-border px-6 last:border-b-0"
                dragCell={(d) => (
                  <DefaultSortDragHandle {...d} handleColumnClassName="w-[72px]" />
                )}
              >
                <div className="flex-1 truncate text-sm text-foreground">{view.name}</div>
                <div className="w-[160px] text-sm text-muted-foreground">{formatDate(view.updated_at)}</div>
                <div className="flex w-[72px] justify-center">
                  <Switch checked={view.is_enabled} onCheckedChange={(checked) => handleToggle(view, checked)} disabled />
                </div>
                <div className="w-[80px]" />
              </SortableFieldTableRow>
            ))}
          </SortableFieldRowsContext>
        ) : (
          items.map((view, idx) => (
            <div
              key={view.id}
              className="flex h-14 items-center gap-6 border-b border-border px-6 last:border-b-0"
            >
              <div className="flex w-[72px] items-center">
                <span className="text-sm text-foreground">{idx + 1}</span>
              </div>
              <div className="flex-1 truncate text-sm text-foreground">{view.name}</div>
              <div className="w-[160px] text-sm text-muted-foreground">{formatDate(view.updated_at)}</div>
              <div className="flex w-[72px] justify-center">
                <Switch checked={view.is_enabled} onCheckedChange={(checked) => handleToggle(view, checked)} />
              </div>
              <div className="flex w-[80px] items-center gap-3">
                <button onClick={() => setDrawerView(view)} className="text-foreground/80 transition-colors hover:text-foreground">
                  <IconPencil size={18} />
                </button>
                <button onClick={() => setConfirmDelete(view)} className="text-foreground/80 transition-colors hover:text-red-600">
                  <IconTrash size={18} />
                </button>
              </div>
            </div>
          ))
        ))}
      </div>

      {drawerView && (
        <ViewDrawer
          view={drawerView === 'new' ? null : drawerView}
          onClose={() => { setDrawerView(null); refetch() }}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title={t('uv.delete.title', locale)}
          message={t('uv.delete.message', locale)}
          itemName={confirmDelete.name}
          onCancel={() => setConfirmDelete(null)}
          onConfirm={handleConfirmDelete}
          loading={deleteView.isPending}
        />
      )}
    </div>
  )
}

// ── Confirm Dialog ──

function ConfirmDialog({
  title, message, itemName, onCancel, onConfirm, loading,
}: {
  title: string; message: string; itemName: string
  onCancel: () => void; onConfirm: () => void; loading: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-[400px] rounded-xl bg-white p-6 shadow-xl">
        <h3 className="text-base font-semibold text-foreground">{title}</h3>
        <p className="mt-3 text-sm text-muted-foreground">{message}</p>
        <p className="mt-2 text-sm font-medium text-foreground">{itemName}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="flex h-9 items-center rounded-lg border border-border px-4 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            {t('uv.cancel', locale)}
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex h-9 items-center rounded-lg bg-red-600 px-4 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
          >
            {t('uv.delete.confirm', locale)}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── View Drawer ──

function ViewDrawer({ view, onClose }: { view: UserView | null; onClose: () => void }) {
  const { locale } = useLocaleStore()
  const updateView = useUpdateUserView()

  const { data: fieldsData } = useUnifiedFields({ domain: 'user', locale })
  const fields: UnifiedField[] = fieldsData?.items ?? []

  const fieldByUid = useMemo(() => {
    const m = new Map<string, UnifiedField>()
    fields.forEach((f) => { const uid = fieldUid(f); if (uid) m.set(uid, f) })
    return m
  }, [fields])

  const [name, setName] = useState(view?.name ?? '')
  const [tab, setTab] = useState<'filter' | 'group' | 'columns'>('filter')
  const [conditionLogic, setConditionLogic] = useState<string>(view?.condition_logic ?? 'and')
  const [conditions, setConditions] = useState<ConditionItem[]>(view?.conditions ?? [])
  const [groupFieldId, setGroupFieldId] = useState<number | null>(view?.group_field_id ?? null)
  const [customColumnsEnabled, setCustomColumnsEnabled] = useState(view?.custom_columns_enabled ?? false)
  const [columnsConfig, setColumnsConfig] = useState<ColumnConfigItem[]>(view?.columns_config ?? [])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (customColumnsEnabled && columnsConfig.length === 0 && fields.length > 0) {
      setColumnsConfig(
        fields.map((f, i) => parseUidToColumnItem(fieldUid(f), true, i)).filter(c => c.field_id != null || c.field_key != null)
      )
    }
  }, [customColumnsEnabled, fields]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSave = async () => {
    if (!name.trim() || !view) return
    setSaving(true)
    try {
      await updateView.mutateAsync({
        id: view.id,
        data: {
          name: name.trim(),
          condition_logic: conditionLogic,
          conditions,
          group_field_id: groupFieldId,
          custom_columns_enabled: customColumnsEnabled,
          columns_config: columnsConfig,
        },
      })
      onClose()
    } catch { /* handled by base */ } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = '' }
  }, [])

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [onClose])

  const groupableFields = useMemo(
    () => fields.filter((f) => GROUPABLE_TYPES.has(f.field_type)),
    [fields]
  )

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-10 flex h-full w-[560px] flex-col bg-white shadow-xl">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
          <button onClick={onClose} className="flex items-center gap-2">
            <IconArrowLeft size={20} className="text-muted-foreground transition-colors hover:text-foreground" />
            <span className="text-base font-semibold text-foreground">{t('uv.drawer.title', locale)}</span>
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name.trim()}
            className="flex h-8 items-center rounded-lg bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {saving ? t('uv.drawer.saving', locale) : t('uv.drawer.save', locale)}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-8">
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium text-foreground">{t('uv.drawer.name', locale)}</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('uv.drawer.namePlaceholder', locale)}
                className="h-10 rounded-lg border border-border px-3.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring"
              />
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex rounded-lg bg-muted p-0.5">
                {(['filter', 'group', 'columns'] as const).map((key) => (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    className={cn(
                      'flex-1 rounded-md px-3 py-2 text-center text-sm transition-colors',
                      tab === key
                        ? 'border border-border bg-white font-medium text-foreground'
                        : 'text-muted-foreground hover:text-muted-foreground'
                    )}
                  >
                    {t(`uv.tab.${key}`, locale)}
                  </button>
                ))}
              </div>

              {tab === 'filter' && (
                <FilterTab
                  fields={fields}
                  fieldByUid={fieldByUid}
                  conditionLogic={conditionLogic}
                  onLogicChange={setConditionLogic}
                  conditions={conditions}
                  onConditionsChange={setConditions}
                />
              )}
              {tab === 'group' && (
                <GroupTab
                  fields={groupableFields}
                  groupFieldId={groupFieldId}
                  onGroupFieldChange={setGroupFieldId}
                />
              )}
              {tab === 'columns' && (
                <ColumnsTab
                  fields={fields}
                  fieldByUid={fieldByUid}
                  customColumnsEnabled={customColumnsEnabled}
                  onCustomColumnsEnabledChange={setCustomColumnsEnabled}
                  columnsConfig={columnsConfig}
                  onColumnsConfigChange={setColumnsConfig}
                />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Filter Tab ──

function FilterTab({
  fields, fieldByUid: fieldMap, conditionLogic, onLogicChange, conditions, onConditionsChange,
}: {
  fields: UnifiedField[]
  fieldByUid: Map<string, UnifiedField>
  conditionLogic: string
  onLogicChange: (v: string) => void
  conditions: ConditionItem[]
  onConditionsChange: (v: ConditionItem[]) => void
}) {
  const { locale } = useLocaleStore()

  const addCondition = () => {
    onConditionsChange([...conditions, { field_id: null, field_key: null, operator: '', value: null }])
  }

  const removeCondition = (idx: number) => {
    onConditionsChange(conditions.filter((_, i) => i !== idx))
  }

  const updateConditionField = (idx: number, uid: string) => {
    const next = [...conditions]
    const patch = parseUidToConditionPatch(uid)
    next[idx] = { ...next[idx], ...patch, operator: '', value: null }
    onConditionsChange(next)
  }

  const updateConditionOperator = (idx: number, operator: string) => {
    const next = [...conditions]
    const prevShape = valueShape(next[idx].operator)
    const nextShape = valueShape(operator)
    const resetValue = nextShape === 'none' || nextShape !== prevShape
    next[idx] = {
      ...next[idx],
      operator,
      value: resetValue ? null : next[idx].value,
    }
    onConditionsChange(next)
  }

  const updateConditionValue = (idx: number, value: unknown) => {
    const next = [...conditions]
    next[idx] = { ...next[idx], value: value as ConditionItem['value'] }
    onConditionsChange(next)
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Match mode */}
      <div className="flex rounded-lg bg-muted p-0.5">
        {(['and', 'or'] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => onLogicChange(mode)}
            className={cn(
              'rounded-md px-3 py-1.5 text-[13px] transition-colors',
              conditionLogic === mode
                ? 'border border-border bg-white font-medium text-foreground/80'
                : 'text-muted-foreground'
            )}
          >
            {t(`uv.filter.${mode}`, locale)}
          </button>
        ))}
      </div>

      {/* Condition rows */}
      {conditions.length > 0 && (
        <div className="overflow-visible rounded-lg border border-border">
          {conditions.map((cond, idx) => {
            const uid = conditionFieldUid(cond)
            const field = uid ? fieldMap.get(uid) : undefined
            const ops = field ? operatorsForFieldType(field.field_type) : []
            const hasField = !!uid
            const showValueEditor = !!cond.operator && !NO_VALUE_OPS.has(cond.operator)
            return (
              <div key={idx} className="flex items-center gap-2.5 border-b border-border px-3 py-2 last:border-b-0">
                {/* Field select */}
                <select
                  value={uid}
                  onChange={(e) => updateConditionField(idx, e.target.value)}
                  className="h-9 w-[140px] rounded-md border border-border px-3 text-sm text-foreground outline-none"
                >
                  <option value="">{t('uv.filter.selectField', locale)}</option>
                  {fields.map((f) => {
                    const fuid = fieldUid(f)
                    if (!fuid) return null
                    return <option key={fuid} value={fuid}>{f.name}</option>
                  })}
                </select>

                {/* Operator select */}
                <select
                  value={cond.operator}
                  onChange={(e) => updateConditionOperator(idx, e.target.value)}
                  className="h-9 w-[110px] rounded-md border border-border px-3 text-sm text-foreground outline-none disabled:bg-accent disabled:text-muted-foreground"
                  disabled={!hasField}
                >
                  <option value="">{t('uv.filter.selectOp', locale)}</option>
                  {ops.map((op) => (
                    <option key={op} value={op}>{t(`uv.op.${op}`, locale)}</option>
                  ))}
                </select>

                {/* Value input (shared, driven by field_type + operator) */}
                {showValueEditor && (
                  <div className="min-w-[160px] flex-1">
                    <FilterValueEditor
                      field={field}
                      operator={cond.operator}
                      value={cond.value}
                      onChange={(v) => updateConditionValue(idx, v)}
                      placeholder={t('uv.filter.valuePlaceholder', locale)}
                    />
                  </div>
                )}

                <button onClick={() => removeCondition(idx)} className="shrink-0 text-muted-foreground hover:text-red-600">
                  <IconTrash size={16} />
                </button>
              </div>
            )
          })}
        </div>
      )}

      <button
        onClick={addCondition}
        className="flex h-9 w-fit items-center gap-1.5 rounded-lg border border-border px-3.5 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
      >
        <IconPlus size={16} />
        {t('uv.filter.add', locale)}
      </button>
    </div>
  )
}

// ── Group Tab ──

function GroupTab({
  fields, groupFieldId, onGroupFieldChange,
}: {
  fields: UnifiedField[]
  groupFieldId: number | null
  onGroupFieldChange: (v: number | null) => void
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">{t('uv.group.hint', locale)}</p>
      <select
        value={groupFieldId ?? ''}
        onChange={(e) => onGroupFieldChange(e.target.value ? Number(e.target.value) : null)}
        className="h-10 rounded-lg border border-border px-3.5 text-sm text-foreground outline-none"
      >
        <option value="">{t('uv.group.placeholder', locale)}</option>
        {fields.map((f) => {
          const fid = f.id
          if (fid == null) return null
          return <option key={fid} value={fid}>{f.name}</option>
        })}
      </select>
    </div>
  )
}

// ── Columns Tab ──

/** When only a search subset is reordered, merge that order back into the full visible list. */
function mergeColumnOrderBySubsequence(
  full: ColumnConfigItem[],
  sub: ColumnConfigItem[],
  reorderedSub: ColumnConfigItem[],
): ColumnConfigItem[] {
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
      <span className="text-sm text-foreground">{fieldName}</span>
    </div>
  )
}

function ColumnsTab({
  fields, fieldByUid: fieldMap, customColumnsEnabled, onCustomColumnsEnabledChange,
  columnsConfig, onColumnsConfigChange,
}: {
  fields: UnifiedField[]
  fieldByUid: Map<string, UnifiedField>
  customColumnsEnabled: boolean
  onCustomColumnsEnabledChange: (v: boolean) => void
  columnsConfig: ColumnConfigItem[]
  onColumnsConfigChange: (v: ColumnConfigItem[]) => void
}) {
  const { locale } = useLocaleStore()
  const [search, setSearch] = useState('')

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const visibleCols = columnsConfig.filter(c => c.visible).sort((a, b) => a.sort_order - b.sort_order)
  const hiddenCols = columnsConfig.filter(c => !c.visible).sort((a, b) => a.sort_order - b.sort_order)

  const toggleColumn = (uid: string) => {
    onColumnsConfigChange(
      columnsConfig.map(c => columnFieldUid(c) === uid ? { ...c, visible: !c.visible } : c)
    )
  }

  const showAll = () => onColumnsConfigChange(columnsConfig.map(c => ({ ...c, visible: true })))
  const hideAll = () => onColumnsConfigChange(columnsConfig.map(c => ({ ...c, visible: false })))

  const resetColumns = () => {
    onColumnsConfigChange(
      fields.map((f, i) => parseUidToColumnItem(fieldUid(f), true, i)).filter(c => c.field_id != null || c.field_key != null)
    )
  }

  const commitVisibleOrder = useCallback((newVisible: ColumnConfigItem[]) => {
    const updated = newVisible.map((c, i) => ({ ...c, sort_order: i }))
    const hiddenUpdated = hiddenCols.map((c, i) => ({ ...c, sort_order: updated.length + i }))
    onColumnsConfigChange([...updated, ...hiddenUpdated])
  }, [hiddenCols, onColumnsConfigChange])

  const filterBySearch = (cols: ColumnConfigItem[]) => {
    if (!search.trim()) return cols
    const q = search.toLowerCase()
    return cols.filter(c => {
      const f = fieldMap.get(columnFieldUid(c))
      return f?.name.toLowerCase().includes(q)
    })
  }

  const searchActive = search.trim().length > 0
  const filteredVisible = filterBySearch(visibleCols)
  const displayCols = searchActive ? filteredVisible : visibleCols

  const sortableIds = useMemo(() => displayCols.map(c => columnFieldUid(c)), [displayCols])

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const oldIndex = sortableIds.indexOf(String(active.id))
    const newIndex = sortableIds.indexOf(String(over.id))
    if (oldIndex < 0 || newIndex < 0) return
    if (searchActive) {
      const reordered = arrayMove(filteredVisible, oldIndex, newIndex)
      const merged = mergeColumnOrderBySubsequence(visibleCols, filteredVisible, reordered)
      commitVisibleOrder(merged)
    } else {
      const newVisible = arrayMove(visibleCols, oldIndex, newIndex)
      commitVisibleOrder(newVisible)
    }
  }, [searchActive, sortableIds, filteredVisible, visibleCols, commitVisibleOrder])

  const getFieldName = (col: ColumnConfigItem): string => {
    const f = fieldMap.get(columnFieldUid(col))
    return f?.name ?? (col.field_key || `Field ${col.field_id}`)
  }

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-col gap-1.5 pb-1">
        <div className="flex items-center gap-2.5">
          <Switch checked={customColumnsEnabled} onCheckedChange={onCustomColumnsEnabledChange} />
          <span className="text-sm font-medium text-foreground">{t('uv.columns.customToggle', locale)}</span>
        </div>
        <p className="text-xs text-muted-foreground">{t('uv.columns.hint', locale)}</p>
      </div>

      {customColumnsEnabled && (
        <>
          <div className="flex items-center gap-2">
            <div className="flex flex-1 items-center gap-1.5 rounded-lg border border-border px-2.5 py-2">
              <IconSearch size={16} className="text-muted-foreground" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('uv.columns.search', locale)}
                className="flex-1 text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
              />
            </div>
            <button onClick={showAll} className="px-2 py-1.5 text-[13px] text-foreground/80 hover:text-foreground">
              {t('uv.columns.showAll', locale)}
            </button>
            <button onClick={hideAll} className="px-2 py-1.5 text-[13px] text-foreground/80 hover:text-foreground">
              {t('uv.columns.hideAll', locale)}
            </button>
            <button onClick={resetColumns} className="text-muted-foreground hover:text-foreground">
              <IconRefresh size={18} />
            </button>
          </div>

          {/* Visible section */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted-foreground">{t('uv.columns.visible', locale)}</span>
              <span className="text-xs text-muted-foreground">{visibleCols.length}</span>
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
                        onToggle={() => toggleColumn(uid)}
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

          {/* Hidden section */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted-foreground">{t('uv.columns.hidden', locale)}</span>
              <span className="text-xs text-muted-foreground">{hiddenCols.length}</span>
            </div>
            <div className="overflow-hidden rounded-lg border border-border">
              {filterBySearch(hiddenCols).map((col) => (
                <div key={columnFieldUid(col)} className="flex h-11 items-center gap-2.5 border-b border-border px-3 last:border-b-0">
                  <IconGripVertical size={16} className="text-muted-foreground" />
                  <Switch checked={false} onCheckedChange={() => toggleColumn(columnFieldUid(col))} />
                  <span className="text-sm text-muted-foreground">{getFieldName(col)}</span>
                </div>
              ))}
              {filterBySearch(hiddenCols).length === 0 && (
                <div className="flex h-11 items-center justify-center text-xs text-muted-foreground">—</div>
              )}
            </div>
          </div>

          <p className="text-[11px] text-muted-foreground">{t('uv.columns.footer', locale)}</p>
        </>
      )}
    </div>
  )
}
