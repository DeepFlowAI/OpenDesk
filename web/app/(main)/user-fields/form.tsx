'use client'

import { useState, useCallback, useEffect } from 'react'
import { IconChevronDown, IconLock } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  FieldType,
  FieldDomain,
  FieldSource,
  FIELD_TYPE_LABELS,
  SELECT_FIELD_TYPES,
  TREE_FIELD_TYPES,
} from '@/types/field-enums'
import { FieldTypeConfig } from '@/app/components/features/field-system'
import type { OptionItem } from '@/app/components/features/field-system'
import type { TreeNodeItem } from '@/app/components/features/field-system'
import type {
  FdFieldDefinition,
  CreateFdFieldDefinitionPayload,
  UpdateFdFieldDefinitionPayload,
  CreateFdFieldOptionPayload,
} from '@/models/field-definition'
import { flattenTreeForPayload } from '@/lib/flatten-tree-nodes-for-create'
import { generateFieldKey, isFieldKeyValid } from '@/lib/field-key'

type FormData = {
  name: string
  key: string
  description: string
  help_text: string
  field_type: string
  type_config: Record<string, unknown>
  options: OptionItem[]
  tree_nodes: TreeNodeItem[]
  show_in_workspace: boolean
  status: string
}

type UserFieldFormProps = {
  initialData?: FdFieldDefinition
  isEdit?: boolean
  onSubmit: (data: CreateFdFieldDefinitionPayload | UpdateFdFieldDefinitionPayload) => void
}

const inputClass =
  'h-10 w-[400px] max-w-full rounded-lg border border-border bg-transparent px-3 text-sm text-foreground/80 outline-none placeholder:text-muted-foreground focus:border-ring'

const textareaClass =
  'w-[400px] max-w-full rounded-lg border border-border bg-transparent px-3 py-2 text-sm text-foreground/80 outline-none placeholder:text-muted-foreground focus:border-ring resize-none'

const FIELD_TYPE_OPTIONS = Object.values(FieldType)

function buildInitialForm(data?: FdFieldDefinition): FormData {
  if (!data) {
    return {
      name: '',
      key: '',
      description: '',
      help_text: '',
      field_type: '',
      type_config: {},
      options: [],
      tree_nodes: [],
      show_in_workspace: true,
      status: 'active',
    }
  }
  return {
    name: data.name,
    key: data.key ?? '',
    description: data.description ?? '',
    help_text: data.help_text ?? '',
    field_type: data.field_type,
    type_config: { ...data.type_config },
    options: (data.options ?? []).map((o) => ({
      label: o.label,
      value: o.value,
      color: o.color ?? undefined,
    })),
    tree_nodes: buildTreeItems(data.tree_nodes ?? []),
    show_in_workspace: data.show_in_workspace ?? true,
    status: data.status,
  }
}

function buildTreeItems(
  flat: { id: number; parent_id: number | null; label: string; value: string; sort_order: number }[],
): TreeNodeItem[] {
  const map = new Map<number, TreeNodeItem>()
  const roots: TreeNodeItem[] = []

  for (const n of flat) {
    map.set(n.id, {
      _tempId: `server-${n.id}`,
      label: n.label,
      value: n.value,
      parent_temp_id: null,
      children: [],
    })
  }

  for (const n of flat) {
    const item = map.get(n.id)!
    if (n.parent_id && map.has(n.parent_id)) {
      item.parent_temp_id = map.get(n.parent_id)!._tempId
      map.get(n.parent_id)!.children.push(item)
    } else {
      roots.push(item)
    }
  }

  return roots
}

export default function UserFieldForm({ initialData, isEdit, onSubmit }: UserFieldFormProps) {
  const { locale } = useLocaleStore()
  const [form, setForm] = useState<FormData>(() => buildInitialForm(initialData))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [typeOpen, setTypeOpen] = useState(false)
  const [keyTouched, setKeyTouched] = useState(false)

  useEffect(() => {
    if (initialData) {
      setForm(buildInitialForm(initialData))
      setKeyTouched(true)
    }
  }, [initialData])

  const set = useCallback(
    <K extends keyof FormData>(key: K, value: FormData[K]) => {
      setForm((prev) => ({ ...prev, [key]: value }))
      setErrors((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    },
    [],
  )

  const handleNameChange = useCallback(
    (value: string) => {
      setForm((prev) => ({
        ...prev,
        name: value,
        key: !isEdit && !keyTouched ? generateFieldKey(value) : prev.key,
      }))
      setErrors((prev) => {
        const next = { ...prev }
        delete next.name
        if (!isEdit && !keyTouched) delete next.key
        return next
      })
    },
    [isEdit, keyTouched],
  )

  const handleKeyChange = useCallback(
    (value: string) => {
      setKeyTouched(true)
      set('key', value)
    },
    [set],
  )

  const validate = useCallback((): boolean => {
    const errs: Record<string, string> = {}
    if (!form.name.trim()) {
      errs.name = t('uf.form.name.required', locale)
    }
    const key = form.key.trim()
    if (!key) {
      errs.key = t('uf.form.key.required', locale)
    } else if (key.length < 2 || key.length > 64) {
      errs.key = t('uf.form.key.length', locale)
    } else if (!isFieldKeyValid(key)) {
      errs.key = t('uf.form.key.format', locale)
    }
    if (!form.field_type) {
      errs.field_type = t('uf.form.fieldType.required', locale)
    }
    const isSelect = (SELECT_FIELD_TYPES as readonly string[]).includes(form.field_type)
    if (isSelect && form.options.length === 0) {
      errs.options = t('uf.form.optionsRequired', locale)
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }, [form, locale])

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      if (!validate()) return

      if (isEdit) {
        const payload: UpdateFdFieldDefinitionPayload = {
          name: form.name.trim(),
          description: form.description.trim() || null,
          help_text: form.help_text.trim() || null,
          type_config: form.type_config,
          show_in_workspace: form.show_in_workspace,
          status: form.status,
        }
        onSubmit(payload)
      } else {
        const optionPayloads: CreateFdFieldOptionPayload[] = form.options.map((o, i) => ({
          label: o.label,
          value: o.value,
          color: o.color ?? null,
          sort_order: i + 1,
        }))

        const treePayloads = flattenTreeForPayload(form.tree_nodes)

        const payload: CreateFdFieldDefinitionPayload = {
          domain: FieldDomain.USER,
          key: form.key.trim(),
          name: form.name.trim(),
          description: form.description.trim() || null,
          help_text: form.help_text.trim() || null,
          field_type: form.field_type as FieldType,
          type_config: form.type_config,
          source: FieldSource.CUSTOM,
          show_in_workspace: form.show_in_workspace,
          options: optionPayloads.length > 0 ? optionPayloads : undefined,
          tree_nodes: treePayloads.length > 0 ? treePayloads : undefined,
        }
        onSubmit(payload)
      }
    },
    [form, isEdit, validate, onSubmit],
  )

  const selectedTypeLabel = form.field_type
    ? FIELD_TYPE_LABELS[form.field_type as FieldType]?.[locale] ?? form.field_type
    : ''

  const isSelect = (SELECT_FIELD_TYPES as readonly string[]).includes(form.field_type)
  const isTree = (TREE_FIELD_TYPES as readonly string[]).includes(form.field_type)
  const hasTypeConfig = !!form.field_type

  return (
    <form id="user-field-form" onSubmit={handleSubmit} className="flex flex-col gap-5 p-8">
      {/* Field name */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">
          {t('uf.form.name', locale)} <span className="text-destructive">*</span>
        </label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => handleNameChange(e.target.value)}
          placeholder={t('uf.form.name.placeholder', locale)}
          maxLength={64}
          className={cn(inputClass, errors.name && 'border-destructive')}
        />
        {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
      </div>

      {/* Field key */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">
          {t('uf.form.key', locale)} <span className="text-destructive">*</span>
        </label>
        <input
          type="text"
          value={form.key}
          onChange={(e) => handleKeyChange(e.target.value)}
          placeholder={t('uf.form.key.placeholder', locale)}
          maxLength={64}
          disabled={isEdit}
          className={cn(inputClass, isEdit && 'bg-accent text-muted-foreground', errors.key && 'border-destructive')}
        />
        <p className="text-xs text-muted-foreground">
          {isEdit ? t('uf.form.key.locked', locale) : t('uf.form.key.help', locale)}
        </p>
        {errors.key && <p className="text-xs text-destructive">{errors.key}</p>}
      </div>

      {/* Description */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">{t('uf.form.description', locale)}</label>
        <textarea
          value={form.description}
          onChange={(e) => set('description', e.target.value)}
          placeholder={t('uf.form.description.placeholder', locale)}
          rows={3}
          maxLength={500}
          className={cn(textareaClass, 'align-top')}
        />
      </div>

      {/* Help text */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">{t('uf.form.helpText', locale)}</label>
        <textarea
          value={form.help_text}
          onChange={(e) => set('help_text', e.target.value)}
          placeholder={t('uf.form.helpText.placeholder', locale)}
          rows={2}
          maxLength={200}
          className={cn(textareaClass, 'align-top')}
        />
      </div>

      {/* Field type */}
      <div className="flex flex-col gap-2">
        <label className="text-sm font-medium text-foreground/80">
          {t('uf.form.fieldType', locale)} <span className="text-destructive">*</span>
        </label>
        {isEdit ? (
          <div className="flex items-center gap-2">
            <div className={cn(inputClass, 'flex w-[240px] items-center bg-accent text-muted-foreground')}>
              {selectedTypeLabel}
            </div>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <IconLock size={12} />
              {t('uf.form.fieldType.locked', locale)}
            </span>
          </div>
        ) : (
          <div className="relative w-[240px]">
            <button
              type="button"
              onClick={() => setTypeOpen(!typeOpen)}
              className={cn(
                'h-10 w-full rounded-lg border border-border bg-transparent px-3 text-sm outline-none',
                'flex items-center justify-between',
                form.field_type ? 'text-foreground/80' : 'text-muted-foreground',
                errors.field_type && 'border-destructive',
              )}
            >
              <span>{selectedTypeLabel || t('uf.form.fieldType.placeholder', locale)}</span>
              <IconChevronDown size={16} className="text-muted-foreground" />
            </button>
            {typeOpen && (
              <div className="absolute top-11 left-0 z-20 max-h-64 w-full overflow-y-auto rounded-lg border border-border bg-white py-1 shadow-lg">
                {FIELD_TYPE_OPTIONS.map((ft) => (
                  <button
                    key={ft}
                    type="button"
                    onClick={() => {
                      set('field_type', ft)
                      set('type_config', {})
                      set('options', [])
                      set('tree_nodes', [])
                      setTypeOpen(false)
                    }}
                    className={cn(
                      'block w-full px-3 py-1.5 text-left text-sm transition-colors hover:bg-accent',
                      ft === form.field_type ? 'font-medium text-foreground' : 'text-foreground/80',
                    )}
                  >
                    {FIELD_TYPE_LABELS[ft]?.[locale] ?? ft}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {errors.field_type && <p className="text-xs text-destructive">{errors.field_type}</p>}
      </div>

      {/* Type-specific configuration */}
      {hasTypeConfig && (
        <div className="pl-7">
          <FieldTypeConfig
            fieldType={form.field_type as FieldType}
            config={form.type_config}
            onConfigChange={(cfg) => set('type_config', cfg)}
            options={isSelect ? form.options : undefined}
            onOptionsChange={isSelect ? (opts) => set('options', opts) : undefined}
            treeNodes={isTree ? form.tree_nodes : undefined}
            onTreeNodesChange={isTree ? (nodes) => set('tree_nodes', nodes) : undefined}
          />
          {errors.options && <p className="mt-2 text-xs text-destructive">{errors.options}</p>}
        </div>
      )}

      {/* Show in workspace */}
      <div className="flex items-center gap-4">
        <label className="text-sm font-medium text-foreground/80">{t('uf.form.showInWorkspace', locale)}</label>
        <button
          type="button"
          role="switch"
          aria-checked={form.show_in_workspace}
          onClick={() => set('show_in_workspace', !form.show_in_workspace)}
          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors ${
            form.show_in_workspace ? 'bg-primary' : 'bg-input'
          }`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
              form.show_in_workspace ? 'translate-x-[18px]' : 'translate-x-[3px]'
            }`}
          />
        </button>
      </div>

      {/* Status */}
      <div className="flex items-center gap-4">
        <label className="text-sm font-medium text-foreground/80">{t('uf.form.status', locale)}</label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => set('status', 'active')}
            className={cn(
              'flex h-8 items-center rounded-lg px-3 text-sm transition-colors',
              form.status === 'active'
                ? 'bg-primary text-white'
                : 'border border-border text-foreground/80 hover:bg-accent',
            )}
          >
            {t('uf.status.active', locale)}
          </button>
          <button
            type="button"
            onClick={() => set('status', 'inactive')}
            className={cn(
              'flex h-8 items-center rounded-lg px-3 text-sm transition-colors',
              form.status === 'inactive'
                ? 'bg-primary text-white'
                : 'border border-border text-foreground/80 hover:bg-accent',
            )}
          >
            {t('uf.status.inactive', locale)}
          </button>
        </div>
      </div>
    </form>
  )
}
