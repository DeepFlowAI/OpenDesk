'use client'

import { useState, useMemo, useCallback } from 'react'
import {
  IconGripVertical,
  IconTrash,
  IconPlus,
  IconArrowLeft,
  IconEdit,
  IconArrowsSort,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  useSessionSummaryFields,
  useAddSessionSummaryField,
  useDeleteSessionSummaryField,
  useSortSessionSummaryFields,
  useUpdateSessionSummaryField,
  useSessionSummaryRules,
  useCreateSessionSummaryRule,
  useUpdateSessionSummaryRule,
  useDeleteSessionSummaryRule,
  useSortSessionSummaryRules,
} from '@/service/use-session-summary'
import { useFieldDefinitions } from '@/service/use-field-definitions'
import type { CsSummaryConfigField, CsSummaryInteractionRule } from '@/models/session-summary'
import type { FdFieldDefinition, UnifiedField } from '@/models/field-definition'
import { FIELD_TYPE_LABELS } from '@/types/field-enums'
import type { FieldType } from '@/types/field-enums'
import {
  FilterValueEditor,
  NO_VALUE_OPS,
  operatorsForFieldType,
  valueShape,
} from '@/components/filter'

type TabId = 'fields' | 'rules'

export default function SessionSummaryPage() {
  const { locale } = useLocaleStore()
  const [activeTab, setActiveTab] = useState<TabId>('fields')

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold text-foreground">{t('ss.title', locale)}</h1>

      <div className="flex gap-4 border-b border-border">
        {(['fields', 'rules'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'pb-2 text-sm font-medium transition-colors',
              activeTab === tab
                ? 'border-b-2 border-foreground text-foreground'
                : 'text-muted-foreground hover:text-foreground/80'
            )}
          >
            {t(tab === 'fields' ? 'ss.tab.fieldsSort' : 'ss.tab.interactionRules', locale)}
          </button>
        ))}
      </div>

      {activeTab === 'fields' ? <FieldsTab /> : <RulesTab />}
    </div>
  )
}

/* ====================================================================
   Fields & Sorting Tab
   ==================================================================== */

function FieldsTab() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSessionSummaryFields()
  const deleteMutation = useDeleteSessionSummaryField()
  const sortMutation = useSortSessionSummaryFields()
  const updateMutation = useUpdateSessionSummaryField()

  const { data: poolData } = useFieldDefinitions({
    domain: 'shared_pool',
    status: 'active',
    per_page: 200,
  })

  const [sorting, setSorting] = useState(false)
  const [sortedItems, setSortedItems] = useState<CsSummaryConfigField[]>([])
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [showPoolModal, setShowPoolModal] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<CsSummaryConfigField | null>(null)

  const fields = data?.items ?? []

  const poolFields = useMemo(() => {
    if (!poolData?.items) return []
    const addedDefIds = new Set(fields.map((f) => f.field_definition_id).filter(Boolean))
    return poolData.items.filter(
      (fd) =>
        fd.applicable_modules?.includes('session_summary') && !addedDefIds.has(fd.id)
    )
  }, [poolData, fields])

  const startSort = () => {
    setSortedItems([...fields])
    setSorting(true)
  }

  const cancelSort = () => {
    setSorting(false)
    setSortedItems([])
  }

  const confirmSort = async () => {
    const items = sortedItems.map((f, i) => ({ id: f.id, sort_order: i }))
    try {
      await sortMutation.mutateAsync(items)
      setSorting(false)
    } catch {
      /* handled by mutation */
    }
  }

  const handleDragStart = (idx: number) => setDragIdx(idx)
  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    if (dragIdx === null || dragIdx === idx) return
    const updated = [...sortedItems]
    const [moved] = updated.splice(dragIdx, 1)
    updated.splice(idx, 0, moved)
    setSortedItems(updated)
    setDragIdx(idx)
  }
  const handleDragEnd = () => setDragIdx(null)

  const confirmDelete = async () => {
    if (!deleteConfirm) return
    try {
      await deleteMutation.mutateAsync(deleteConfirm.id)
    } catch {
      /* */
    }
    setDeleteConfirm(null)
  }

  const toggleActive = (field: CsSummaryConfigField) => {
    updateMutation.mutate({ id: field.id, data: { is_active: !field.is_active } })
  }

  const displayItems = sorting ? sortedItems : fields

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">{t('ss.fields.loading', locale)}</p>
  }

  return (
    <>
      {/* Toolbar */}
      {sorting ? (
        <div className="flex items-center justify-between rounded-lg bg-accent px-4 py-3">
          <span className="text-sm text-muted-foreground">{t('ss.fields.sortHint', locale)}</span>
          <div className="flex gap-2">
            <button
              onClick={cancelSort}
              className="rounded-lg border border-border bg-white px-4 py-1.5 text-sm"
            >
              {t('ss.fields.sortCancel', locale)}
            </button>
            <button
              onClick={confirmSort}
              className="rounded-lg bg-primary px-4 py-1.5 text-sm text-white"
            >
              {t('ss.fields.sortConfirm', locale)}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          {fields.length > 1 && (
            <button
              onClick={startSort}
              className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-1.5 text-sm hover:bg-accent"
            >
              <IconArrowsSort size={16} />
              {t('ss.fields.sort', locale)}
            </button>
          )}
          <button
            onClick={() => setShowPoolModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-1.5 text-sm text-white hover:bg-primary/80"
          >
            <IconPlus size={16} />
            {t('ss.fields.addFromPool', locale)}
          </button>
        </div>
      )}

      {/* Table */}
      {displayItems.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
          <p className="text-sm">{t('ss.fields.empty', locale)}</p>
          <button
            onClick={() => setShowPoolModal(true)}
            className="text-sm font-medium text-foreground underline"
          >
            {t('ss.fields.addFromPool', locale)}
          </button>
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              {sorting && <th className="w-10 py-2" />}
              <th className="w-16 py-2">{t('ss.fields.col.index', locale)}</th>
              <th className="py-2">{t('ss.fields.col.name', locale)}</th>
              <th className="py-2">{t('ss.fields.col.type', locale)}</th>
              <th className="w-20 py-2">{t('ss.fields.col.status', locale)}</th>
              {!sorting && <th className="w-24 py-2">{t('ss.fields.col.actions', locale)}</th>}
            </tr>
          </thead>
          <tbody>
            {displayItems.map((field, idx) => (
              <FieldRow
                key={field.id}
                field={field}
                index={idx}
                sorting={sorting}
                poolFields={poolData?.items ?? []}
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={handleDragEnd}
                onToggle={() => toggleActive(field)}
                onDelete={() => setDeleteConfirm(field)}
                locale={locale}
              />
            ))}
          </tbody>
        </table>
      )}

      {/* Pool modal */}
      {showPoolModal && (
        <PoolModal
          poolFields={poolFields}
          onClose={() => setShowPoolModal(false)}
        />
      )}

      {/* Delete confirm */}
      {deleteConfirm && (
        <ConfirmDialog
          title={t('ss.fields.delete.title', locale)}
          message={t('ss.fields.delete.confirm', locale)}
          cancelLabel={t('ss.fields.delete.cancel', locale)}
          okLabel={t('ss.fields.delete.ok', locale)}
          onCancel={() => setDeleteConfirm(null)}
          onConfirm={confirmDelete}
        />
      )}
    </>
  )
}

function FieldRow({
  field,
  index,
  sorting,
  poolFields,
  onDragStart,
  onDragOver,
  onDragEnd,
  onToggle,
  onDelete,
  locale,
}: {
  field: CsSummaryConfigField
  index: number
  sorting: boolean
  poolFields: FdFieldDefinition[]
  onDragStart: () => void
  onDragOver: (e: React.DragEvent) => void
  onDragEnd: () => void
  onToggle: () => void
  onDelete: () => void
  locale: string
}) {
  const def = poolFields.find((fd) => fd.id === field.field_definition_id)
  const name = def?.name ?? field.field_key ?? '—'
  const typeLabel = def?.field_type
    ? FIELD_TYPE_LABELS[def.field_type as FieldType]?.[locale as 'zh' | 'en'] ?? def.field_type
    : '—'

  return (
    <tr
      draggable={sorting}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDragEnd={onDragEnd}
      className="border-b border-border transition-colors hover:bg-accent/50"
    >
      {sorting && (
        <td className="py-3 text-center">
          <IconGripVertical size={16} className="cursor-grab text-muted-foreground" />
        </td>
      )}
      <td className="py-3 text-muted-foreground">{index + 1}</td>
      <td className="py-3 font-medium text-foreground">{name}</td>
      <td className="py-3 text-muted-foreground">{typeLabel}</td>
      <td className="py-3">
        <button
          onClick={onToggle}
          className={cn(
            'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
            field.is_active ? 'bg-primary' : 'bg-input'
          )}
        >
          <span
            className={cn(
              'inline-block h-4 w-4 rounded-full bg-white transition-transform',
              field.is_active ? 'translate-x-[18px]' : 'translate-x-[2px]'
            )}
          />
        </button>
      </td>
      {!sorting && (
        <td className="py-3">
          <div className="flex gap-2">
            <button onClick={onDelete} className="text-muted-foreground hover:text-destructive">
              <IconTrash size={16} />
            </button>
          </div>
        </td>
      )}
    </tr>
  )
}

/* ====================================================================
   Pool Modal — add fields from shared pool
   ==================================================================== */

function PoolModal({
  poolFields,
  onClose,
}: {
  poolFields: FdFieldDefinition[]
  onClose: () => void
}) {
  const { locale } = useLocaleStore()
  const addMutation = useAddSessionSummaryField()

  const handleAdd = async (fd: FdFieldDefinition) => {
    try {
      await addMutation.mutateAsync({ field_definition_id: fd.id })
    } catch {
      /* */
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-[520px] rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h3 className="text-lg font-semibold">{t('ss.fields.pool.title', locale)}</h3>
          <button onClick={onClose} className="text-sm text-muted-foreground hover:text-foreground">
            {t('ss.fields.pool.close', locale)}
          </button>
        </div>
        <div className="max-h-[400px] overflow-y-auto px-6 py-4">
          {poolFields.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              {t('ss.fields.pool.empty', locale)}
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {poolFields.map((fd) => (
                <div
                  key={fd.id}
                  className="flex items-center justify-between rounded-lg border border-border px-4 py-2.5"
                >
                  <div>
                    <span className="text-sm font-medium text-foreground">{fd.name}</span>
                    <span className="ml-3 text-xs text-muted-foreground">
                      {FIELD_TYPE_LABELS[fd.field_type as FieldType]?.[locale as 'zh' | 'en'] ?? fd.field_type}
                    </span>
                  </div>
                  <button
                    onClick={() => handleAdd(fd)}
                    disabled={addMutation.isPending}
                    className="rounded-md bg-primary px-3 py-1 text-xs text-white hover:bg-primary/80 disabled:opacity-50"
                  >
                    {t('ss.fields.pool.add', locale)}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ====================================================================
   Interaction Rules Tab
   ==================================================================== */

function RulesTab() {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSessionSummaryRules()
  const deleteMutation = useDeleteSessionSummaryRule()
  const updateMutation = useUpdateSessionSummaryRule()
  const sortMutation = useSortSessionSummaryRules()

  const [sorting, setSorting] = useState(false)
  const [sortedRules, setSortedRules] = useState<CsSummaryInteractionRule[]>([])
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [drawerRule, setDrawerRule] = useState<CsSummaryInteractionRule | 'new' | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<CsSummaryInteractionRule | null>(null)

  const rules = data?.items ?? []

  const startSort = () => {
    setSortedRules([...rules])
    setSorting(true)
  }

  const cancelSort = () => {
    setSorting(false)
    setSortedRules([])
  }

  const confirmSort = async () => {
    const items = sortedRules.map((r, i) => ({ id: r.id, sort_order: i }))
    try {
      await sortMutation.mutateAsync(items)
      setSorting(false)
    } catch {
      /* */
    }
  }

  const handleDragStart = (idx: number) => setDragIdx(idx)
  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    if (dragIdx === null || dragIdx === idx) return
    const updated = [...sortedRules]
    const [moved] = updated.splice(dragIdx, 1)
    updated.splice(idx, 0, moved)
    setSortedRules(updated)
    setDragIdx(idx)
  }
  const handleDragEnd = () => setDragIdx(null)

  const toggleEnabled = (rule: CsSummaryInteractionRule) => {
    updateMutation.mutate({ id: rule.id, data: { is_enabled: !rule.is_enabled } })
  }

  const confirmDelete = async () => {
    if (!deleteConfirm) return
    try {
      await deleteMutation.mutateAsync(deleteConfirm.id)
    } catch {
      /* */
    }
    setDeleteConfirm(null)
  }

  const displayRules = sorting ? sortedRules : rules

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">{t('ss.rules.loading', locale)}</p>
  }

  return (
    <>
      {/* Toolbar */}
      {sorting ? (
        <div className="flex items-center justify-between rounded-lg bg-accent px-4 py-3">
          <span className="text-sm text-muted-foreground">{t('ss.rules.sortHint', locale)}</span>
          <div className="flex gap-2">
            <button
              onClick={cancelSort}
              className="rounded-lg border border-border bg-white px-4 py-1.5 text-sm"
            >
              {t('ss.rules.sortCancel', locale)}
            </button>
            <button
              onClick={confirmSort}
              className="rounded-lg bg-primary px-4 py-1.5 text-sm text-white"
            >
              {t('ss.rules.sortConfirm', locale)}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          {rules.length > 1 && (
            <button
              onClick={startSort}
              className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-1.5 text-sm hover:bg-accent"
            >
              <IconArrowsSort size={16} />
              {t('ss.rules.sort', locale)}
            </button>
          )}
          <button
            onClick={() => setDrawerRule('new')}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-1.5 text-sm text-white hover:bg-primary/80"
          >
            <IconPlus size={16} />
            {t('ss.rules.add', locale)}
          </button>
        </div>
      )}

      {/* Table */}
      {displayRules.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground">
          <p className="text-sm">{t('ss.rules.empty', locale)}</p>
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              {sorting && <th className="w-10 py-2" />}
              <th className="w-16 py-2">{t('ss.rules.col.index', locale)}</th>
              <th className="py-2">{t('ss.rules.col.summary', locale)}</th>
              <th className="w-20 py-2">{t('ss.rules.col.enabled', locale)}</th>
              {!sorting && <th className="w-28 py-2">{t('ss.rules.col.actions', locale)}</th>}
            </tr>
          </thead>
          <tbody>
            {displayRules.map((rule, idx) => (
              <tr
                key={rule.id}
                draggable={sorting}
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={handleDragEnd}
                className="border-b border-border transition-colors hover:bg-accent/50"
              >
                {sorting && (
                  <td className="py-3 text-center">
                    <IconGripVertical size={16} className="cursor-grab text-muted-foreground" />
                  </td>
                )}
                <td className="py-3 text-muted-foreground">{idx + 1}</td>
                <td className="py-3 text-foreground">
                  {buildRuleSummary(rule, locale)}
                </td>
                <td className="py-3">
                  <button
                    onClick={() => toggleEnabled(rule)}
                    className={cn(
                      'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                      rule.is_enabled ? 'bg-primary' : 'bg-input'
                    )}
                  >
                    <span
                      className={cn(
                        'inline-block h-4 w-4 rounded-full bg-white transition-transform',
                        rule.is_enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'
                      )}
                    />
                  </button>
                </td>
                {!sorting && (
                  <td className="py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => setDrawerRule(rule)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <IconEdit size={16} />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(rule)}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <IconTrash size={16} />
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Drawer */}
      {drawerRule && (
        <RuleDrawer
          rule={drawerRule === 'new' ? null : drawerRule}
          onClose={() => setDrawerRule(null)}
        />
      )}

      {/* Delete confirm */}
      {deleteConfirm && (
        <ConfirmDialog
          title={t('ss.rules.delete.title', locale)}
          message={t('ss.rules.delete.confirm', locale)}
          cancelLabel={t('ss.rules.delete.cancel', locale)}
          okLabel={t('ss.rules.delete.ok', locale)}
          onCancel={() => setDeleteConfirm(null)}
          onConfirm={confirmDelete}
        />
      )}
    </>
  )
}

/* ====================================================================
   Rule Edit Drawer
   ==================================================================== */

type RuleCondition = {
  field_key: string | null
  field_id: number | null
  operator: string
  value: unknown
}

type RuleAction = {
  target_field_key: string | null
  target_field_id: number | null
  state: string
}

type RuleDraft = {
  name: string
  is_enabled: boolean
  condition_logic: string
  conditions: RuleCondition[]
  actions: RuleAction[]
}

type RuleFieldOption = {
  value: string
  label: string
  field: UnifiedField | undefined
}

function parseFieldOption(val: string) {
  if (val.startsWith('key:')) return { field_key: val.slice(4), field_id: null }
  if (val.startsWith('def:')) return { field_key: null, field_id: Number(val.slice(4)) }
  return { field_key: null, field_id: null }
}

function fieldOptionValue(fk: string | null, fid: number | null) {
  if (fk) return `key:${fk}`
  if (fid) return `def:${fid}`
  return ''
}

function toUnifiedField(def: FdFieldDefinition): UnifiedField {
  return {
    key: def.key,
    id: def.id,
    domain: def.domain,
    source: def.source as UnifiedField['source'],
    name: def.name,
    description: def.description,
    help_text: def.help_text,
    field_type: def.field_type,
    type_config: def.type_config,
    applicable_modules: def.applicable_modules,
    slot_column: def.slot_column,
    show_in_workspace: def.show_in_workspace,
    sort_order: def.sort_order,
    status: def.status,
    options: def.options,
    tree_nodes: def.tree_nodes,
    created_at: def.created_at,
    updated_at: def.updated_at,
  }
}

function RuleDrawer({
  rule,
  onClose,
}: {
  rule: CsSummaryInteractionRule | null
  onClose: () => void
}) {
  const { locale } = useLocaleStore()
  const createMutation = useCreateSessionSummaryRule()
  const updateMutation = useUpdateSessionSummaryRule()

  const { data: fieldsData } = useSessionSummaryFields()
  const { data: poolData } = useFieldDefinitions({
    domain: 'shared_pool',
    status: 'active',
    per_page: 200,
  })

  const availableFields = useMemo(() => {
    const configFields = fieldsData?.items ?? []
    const defs = poolData?.items ?? []
    return configFields.map((cf) => {
      const def = defs.find((d) => d.id === cf.field_definition_id)
      return {
        value: cf.field_definition_id ? `def:${cf.field_definition_id}` : `key:${cf.field_key}`,
        label: def?.name ?? cf.field_key ?? `#${cf.id}`,
        field: def ? toUnifiedField(def) : undefined,
      }
    })
  }, [fieldsData, poolData])

  const fieldByValue = useMemo(() => {
    const map = new Map<string, RuleFieldOption>()
    for (const field of availableFields) {
      map.set(field.value, field)
    }
    return map
  }, [availableFields])

  const [draft, setDraft] = useState<RuleDraft>(() => {
    if (rule) {
      return {
        name: rule.name ?? '',
        is_enabled: rule.is_enabled,
        condition_logic: rule.condition_logic,
        conditions: (rule.conditions as unknown as RuleCondition[]) ?? [],
        actions: (rule.actions as unknown as RuleAction[]) ?? [],
      }
    }
    return {
      name: '',
      is_enabled: true,
      condition_logic: 'and',
      conditions: [{ field_key: null, field_id: null, operator: '', value: null }],
      actions: [{ target_field_key: null, target_field_id: null, state: '' }],
    }
  })

  const [saving, setSaving] = useState(false)

  const updateDraft = useCallback((fn: (prev: RuleDraft) => RuleDraft) => {
    setDraft((prev) => fn(prev))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    const payload = {
      name: draft.name || null,
      is_enabled: draft.is_enabled,
      condition_logic: draft.condition_logic,
      conditions: draft.conditions as unknown as Record<string, unknown>[],
      actions: draft.actions as unknown as Record<string, unknown>[],
    }
    try {
      if (rule) {
        await updateMutation.mutateAsync({ id: rule.id, data: payload })
      } else {
        await createMutation.mutateAsync(payload)
      }
      onClose()
    } catch {
      /* */
    } finally {
      setSaving(false)
    }
  }

  const stateOptions = [
    { value: 'hidden', label: t('ss.rules.state.hidden', locale) },
    { value: 'required', label: t('ss.rules.state.required', locale) },
    { value: 'optional', label: t('ss.rules.state.optional', locale) },
    { value: 'readonly', label: t('ss.rules.state.readonly', locale) },
  ]

  const selectCls = 'h-9 rounded-lg border border-border bg-white px-2 text-sm outline-none focus:border-ring'
  const inputCls = 'h-9 rounded-lg border border-border bg-white px-3 text-sm outline-none focus:border-ring'

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      <div className="relative z-10 flex h-full w-[520px] flex-col bg-white shadow-xl">
        {/* Header */}
        <div className="flex h-14 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="text-foreground/80 transition-colors hover:text-foreground">
              <IconArrowLeft size={18} />
            </button>
            <span className="text-sm font-semibold text-foreground">
              {t(rule ? 'ss.rules.drawer.editTitle' : 'ss.rules.drawer.newTitle', locale)}
            </span>
          </div>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex h-8 items-center rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {saving ? t('ss.rules.drawer.saving', locale) : t('ss.rules.drawer.save', locale)}
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          <div className="flex flex-col gap-5">
            {/* Rule name */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground/80">
                {t('ss.rules.form.name', locale)}
              </label>
              <input
                type="text"
                value={draft.name}
                onChange={(e) => updateDraft((d) => ({ ...d, name: e.target.value }))}
                placeholder={t('ss.rules.form.name.placeholder', locale)}
                className={cn(inputCls, 'w-full')}
              />
            </div>

            {/* Enabled */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-foreground/80">
                {t('ss.rules.form.enabled', locale)}
              </label>
              <button
                onClick={() => updateDraft((d) => ({ ...d, is_enabled: !d.is_enabled }))}
                className={cn(
                  'relative h-5 w-9 rounded-full transition-colors',
                  draft.is_enabled ? 'bg-primary' : 'bg-input'
                )}
              >
                <div
                  className={cn(
                    'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform',
                    draft.is_enabled ? 'translate-x-[18px]' : 'translate-x-0.5'
                  )}
                />
              </button>
            </div>

            {/* Condition section */}
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground/80">
                {t('ss.rules.form.conditionLogic', locale)}
              </label>

              {/* Condition Logic pill buttons */}
              <div className="mb-4 flex gap-2">
                {(['and', 'or'] as const).map((logic) => (
                  <button
                    key={logic}
                    onClick={() => updateDraft((d) => ({ ...d, condition_logic: logic }))}
                    className={cn(
                      'rounded-md border px-3 py-1 text-sm transition-colors',
                      draft.condition_logic === logic
                        ? 'border-foreground bg-primary font-medium text-white'
                        : 'border-border bg-white text-muted-foreground hover:border-muted-foreground'
                    )}
                  >
                    {t(logic === 'and' ? 'ss.rules.form.conditionLogic.all' : 'ss.rules.form.conditionLogic.any', locale)}
                  </button>
                ))}
              </div>

              {/* Condition rows */}
              <div className="flex flex-col gap-3">
                {draft.conditions.map((cond, idx) => {
                  const selectedFieldValue = fieldOptionValue(cond.field_key, cond.field_id)
                  const selectedField = fieldByValue.get(selectedFieldValue)?.field
                  const operators = operatorsForFieldType(selectedField?.field_type)
                  const showValueEditor = !!cond.operator && !NO_VALUE_OPS.has(cond.operator)

                  return (
                    <div key={idx} className="flex items-center gap-2">
                      <select
                        value={selectedFieldValue}
                        onChange={(e) => {
                          const parsed = parseFieldOption(e.target.value)
                          const nextField = fieldByValue.get(e.target.value)?.field
                          const nextOperators = operatorsForFieldType(nextField?.field_type)
                          updateDraft((d) => ({
                            ...d,
                            conditions: d.conditions.map((c, i) =>
                              i === idx
                                ? {
                                    ...c,
                                    ...parsed,
                                    operator: nextOperators.includes(c.operator) ? c.operator : (nextOperators[0] ?? ''),
                                    value: null,
                                  }
                                : c
                            ),
                          }))
                        }}
                        className={cn(selectCls, 'min-w-0 flex-1')}
                      >
                        <option value="">{t('ss.rules.form.field.placeholder', locale)}</option>
                        {availableFields.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                      <select
                        value={cond.operator}
                        onChange={(e) => {
                          const operator = e.target.value
                          updateDraft((d) => ({
                            ...d,
                            conditions: d.conditions.map((c, i) =>
                              i === idx
                                ? {
                                    ...c,
                                    operator,
                                    value:
                                      valueShape(operator) === valueShape(c.operator) && !NO_VALUE_OPS.has(operator)
                                        ? c.value
                                        : null,
                                  }
                                : c
                            ),
                          }))
                        }}
                        disabled={!selectedField}
                        className={cn(selectCls, 'w-[110px] shrink-0 disabled:bg-accent disabled:text-muted-foreground')}
                      >
                        <option value="">{t('ss.rules.form.operator.placeholder', locale)}</option>
                        {operators.map((operator) => (
                          <option key={operator} value={operator}>{t(`ss.rules.op.${operator}`, locale)}</option>
                        ))}
                      </select>
                      {showValueEditor && (
                        <div className="min-w-[140px] flex-1">
                          <FilterValueEditor
                            field={selectedField}
                            operator={cond.operator}
                            value={cond.value}
                            onChange={(value) =>
                              updateDraft((d) => ({
                                ...d,
                                conditions: d.conditions.map((c, i) =>
                                  i === idx ? { ...c, value } : c
                                ),
                              }))
                            }
                            placeholder={t('ss.rules.form.value.placeholder', locale)}
                          />
                        </div>
                      )}
                      <button
                        onClick={() =>
                          updateDraft((d) => ({
                            ...d,
                            conditions: d.conditions.filter((_, i) => i !== idx),
                          }))
                        }
                        className="shrink-0 text-border transition-colors hover:text-muted-foreground"
                      >
                        <IconTrash size={16} />
                      </button>
                    </div>
                  )
                })}
              </div>

              <button
                onClick={() =>
                  updateDraft((d) => ({
                    ...d,
                    conditions: [...d.conditions, { field_key: null, field_id: null, operator: '', value: null }],
                  }))
                }
                className="mt-3 flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-foreground/80 transition-colors hover:border-muted-foreground hover:bg-accent/50"
              >
                <IconPlus size={14} />
                {t('ss.rules.form.addCondition', locale)}
              </button>
            </div>

            {/* Actions section */}
            <div>
              <label className="mb-3 block text-sm font-semibold text-foreground">
                {t('ss.rules.form.actions', locale)}
              </label>
              <div className="flex flex-col gap-4">
                {draft.actions.map((act, idx) => (
                  <div key={idx} className="flex flex-col gap-3">
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground/80">
                        {t('ss.rules.form.targetField', locale)}
                      </label>
                      <div className="flex items-center gap-2">
                        <select
                          value={fieldOptionValue(act.target_field_key, act.target_field_id)}
                          onChange={(e) => {
                            const parsed = parseFieldOption(e.target.value)
                            updateDraft((d) => ({
                              ...d,
                              actions: d.actions.map((a, i) =>
                                i === idx ? { ...a, target_field_key: parsed.field_key, target_field_id: parsed.field_id } : a
                              ),
                            }))
                          }}
                          className={cn(selectCls, 'min-w-0 flex-1')}
                        >
                          <option value="">{t('ss.rules.form.targetField.placeholder', locale)}</option>
                          {availableFields.map((o) => (
                            <option key={o.value} value={o.value}>{o.label}</option>
                          ))}
                        </select>
                        <button
                          onClick={() =>
                            updateDraft((d) => ({
                              ...d,
                              actions: d.actions.filter((_, i) => i !== idx),
                            }))
                          }
                          className="shrink-0 text-border transition-colors hover:text-muted-foreground"
                        >
                          <IconTrash size={16} />
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground/80">
                        {t('ss.rules.form.targetState', locale)}
                      </label>
                      <select
                        value={act.state}
                        onChange={(e) =>
                          updateDraft((d) => ({
                            ...d,
                            actions: d.actions.map((a, i) =>
                              i === idx ? { ...a, state: e.target.value } : a
                            ),
                          }))
                        }
                        className={cn(selectCls, 'w-full')}
                      >
                        <option value="">{t('ss.rules.form.targetState.placeholder', locale)}</option>
                        {stateOptions.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </div>
                    {idx < draft.actions.length - 1 && <hr className="border-border" />}
                  </div>
                ))}
              </div>

              <button
                onClick={() =>
                  updateDraft((d) => ({
                    ...d,
                    actions: [...d.actions, { target_field_key: null, target_field_id: null, state: '' }],
                  }))
                }
                className="mt-3 flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-foreground/80 transition-colors hover:border-muted-foreground hover:bg-accent/50"
              >
                <IconPlus size={14} />
                {t('ss.rules.form.addAction', locale)}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ====================================================================
   Shared Components
   ==================================================================== */

function ConfirmDialog({
  title,
  message,
  cancelLabel,
  okLabel,
  onCancel,
  onConfirm,
}: {
  title: string
  message: string
  cancelLabel: string
  okLabel: string
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-[400px] rounded-xl bg-white p-6 shadow-xl">
        <h3 className="mb-3 text-lg font-semibold">{title}</h3>
        <p className="mb-6 text-sm text-muted-foreground">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="rounded-lg border border-border px-4 py-1.5 text-sm"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg bg-red-500 px-4 py-1.5 text-sm text-white hover:bg-red-600"
          >
            {okLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ====================================================================
   Helpers
   ==================================================================== */

function buildRuleSummary(rule: CsSummaryInteractionRule, locale: string): string {
  if (rule.name) return rule.name

  const lang = locale as 'zh' | 'en'
  const conds = (rule.conditions as unknown as RuleCondition[]) ?? []
  const acts = (rule.actions as unknown as RuleAction[]) ?? []

  if (conds.length === 0 && acts.length === 0) return '—'

  const condPart = conds
    .slice(0, 2)
    .map((c) => {
      const field = c.field_key ?? c.field_id ?? '?'
      const op = t(`ss.rules.op.${c.operator}`, lang) || c.operator
      return `${field} ${op} ${c.value}`
    })
    .join(rule.condition_logic === 'and' ? ' & ' : ' | ')
  const actPart = acts
    .slice(0, 2)
    .map((a) => {
      const target = a.target_field_key ?? a.target_field_id ?? '?'
      const state = t(`ss.rules.state.${a.state}`, lang) || a.state
      return `${target} → ${state}`
    })
    .join(', ')

  const prefix = lang === 'zh' ? '当' : 'If'
  return `${prefix} ${condPart} → ${actPart}`
}
