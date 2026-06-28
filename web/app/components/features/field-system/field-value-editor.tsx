'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { IconChevronDown, IconSearch, IconX } from '@tabler/icons-react'
import { DateInput, DateTimeInput, TimeInput } from '@/components/ui/time-input'
import { cn } from '@/lib/utils'
import { FieldType } from '@/types/field-enums'
import type { FdFieldOption, FdTreeNode, UnifiedField } from '@/models/field-definition'
import type { Organization } from '@/models/organization'
import { FieldFileEditor } from '@/app/components/features/field-system/field-file-editor'
import { TreeSelectEditor } from '@/app/components/features/field-system/tree-select-editor'
import { RichTextFieldEditor } from '@/app/components/features/field-system/rich-text-field-editor'
import { UserSelect } from '@/app/components/features/ticket/user-select'
import { EmployeeSelect } from '@/app/components/features/ticket/employee-select'
import { EmployeeGroupSelect } from '@/app/components/features/ticket/employee-group-select'
import { useOrganization, useQueryOrganizations } from '@/service/use-organizations'
import {
  coalescePillOptions,
  type FieldSelectOption,
  PillMultiSelectField,
  PillSelectCombobox,
} from '@/app/components/features/field-system/field-select-pill-editors'

type FieldValueEditorProps = {
  fieldType: FieldType
  value: unknown
  onChange: (value: unknown) => void
  typeConfig?: Record<string, unknown>
  options?: FdFieldOption[] | FieldSelectOption[]
  treeNodes?: FdTreeNode[]
  placeholder?: string
  disabled?: boolean
  className?: string
  autoFocus?: boolean
  dropdownPlacement?: 'top' | 'bottom'
}

const inputClass =
  'h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50'

const DEFAULT_PLACEHOLDERS: Record<string, string> = {
  single_line_text: '请输入',
  multi_line_text: '请输入',
  number: '请输入',
  date: '请选择',
  time: '请选择',
  datetime: '请选择',
  single_select: '请选择',
  multi_select: '请选择',
  single_select_tree: '请选择',
  multi_select_tree: '请选择',
  email: '请输入',
  phone: '请输入',
  url: '请输入',
  file: '请上传',
  rich_text: '请输入',
  user_select: '请选择用户',
  organization_select: '请选择组织',
  employee_select: '请选择员工',
  group_select: '请选择负责组',
}

type UnifiedFieldValueEditorProps = Omit<FieldValueEditorProps, 'fieldType' | 'options' | 'treeNodes'> & {
  field: UnifiedField
}

export function UnifiedFieldValueEditor({
  field,
  value,
  onChange,
  typeConfig,
  ...props
}: UnifiedFieldValueEditorProps) {
  const mergedTypeConfig = typeConfig ?? ((field.type_config ?? {}) as Record<string, unknown>)

  return (
    <FieldValueEditor
      {...props}
      fieldType={field.field_type}
      value={normalizeFieldEditorValue(field.field_type, value)}
      onChange={(next) => onChange(normalizeFieldEditorOutput(field.field_type, next))}
      typeConfig={mergedTypeConfig}
      options={field.options ?? []}
      treeNodes={field.tree_nodes ?? []}
    />
  )
}


function toStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item)).filter(Boolean)
  if (typeof value === 'string') return value.split(',').map((item) => item.trim()).filter(Boolean)
  return []
}

function toNullableNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function normalizeFieldEditorValue(fieldType: FieldType, value: unknown): unknown {
  if (fieldType === FieldType.MULTI_SELECT || fieldType === FieldType.MULTI_SELECT_TREE) {
    return toStringArray(value)
  }
  if (
    fieldType === FieldType.USER_SELECT ||
    fieldType === FieldType.ORGANIZATION_SELECT ||
    fieldType === FieldType.EMPLOYEE_SELECT ||
    fieldType === FieldType.GROUP_SELECT
  ) {
    return toNullableNumber(value)
  }
  return value
}

function normalizeFieldEditorOutput(fieldType: FieldType, value: unknown): unknown {
  if (fieldType === FieldType.MULTI_SELECT || fieldType === FieldType.MULTI_SELECT_TREE) {
    const values = toStringArray(value)
    return values.length > 0 ? values : null
  }
  if (
    fieldType === FieldType.USER_SELECT ||
    fieldType === FieldType.ORGANIZATION_SELECT ||
    fieldType === FieldType.EMPLOYEE_SELECT ||
    fieldType === FieldType.GROUP_SELECT
  ) {
    return toNullableNumber(value)
  }
  return value
}

function getDropdownPlacement(root: HTMLElement | null, expectedHeight = 256): 'top' | 'bottom' {
  if (!root || typeof window === 'undefined') return 'bottom'
  const rect = root.getBoundingClientRect()
  let boundaryTop = 0
  let boundaryBottom = window.innerHeight

  let parent = root.parentElement
  while (parent) {
    const style = window.getComputedStyle(parent)
    if (/(auto|scroll|hidden)/.test(style.overflowY)) {
      const parentRect = parent.getBoundingClientRect()
      boundaryTop = Math.max(boundaryTop, parentRect.top)
      boundaryBottom = Math.min(boundaryBottom, parentRect.bottom)
      break
    }
    parent = parent.parentElement
  }

  const spaceBelow = boundaryBottom - rect.bottom
  const spaceAbove = rect.top - boundaryTop
  return spaceBelow < expectedHeight && spaceAbove > spaceBelow ? 'top' : 'bottom'
}

/**
 * Input control for editing a field value.
 * Used in forms where end users fill in custom field data.
 */
export function FieldValueEditor({
  fieldType,
  value,
  onChange,
  typeConfig = {},
  options = [],
  treeNodes = [],
  placeholder,
  disabled = false,
  className,
  autoFocus = false,
  dropdownPlacement,
}: FieldValueEditorProps) {
  const ph = placeholder ?? (typeConfig.placeholder as string) ?? DEFAULT_PLACEHOLDERS[fieldType] ?? ''

  switch (fieldType) {
    case FieldType.SINGLE_LINE_TEXT:
    case FieldType.EMAIL:
    case FieldType.PHONE:
    case FieldType.URL:
      return (
        <input
          type={fieldType === FieldType.EMAIL ? 'email' : fieldType === FieldType.URL ? 'url' : 'text'}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={ph}
          maxLength={(typeConfig.max_length as number) ?? undefined}
          disabled={disabled}
          autoFocus={autoFocus}
          className={cn(inputClass, className)}
        />
      )

    case FieldType.MULTI_LINE_TEXT:
      return (
        <textarea
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={ph}
          maxLength={(typeConfig.max_length as number) ?? undefined}
          disabled={disabled}
          rows={4}
          autoFocus={autoFocus}
          className={cn(
            'w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
            className,
          )}
        />
      )

    case FieldType.NUMBER:
      return (
        <NumberEditor
          value={value}
          onChange={onChange}
          typeConfig={typeConfig}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
        />
      )

    case FieldType.DATE:
      return (
        <DateInput
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder={ph}
          disabled={disabled}
          autoFocus={autoFocus}
          className={cn(inputClass, className)}
        />
      )

    case FieldType.TIME: {
      const granularity = (typeConfig.time_granularity as string) ?? 'minute'
      return (
        <TimeInput
          step={granularity === 'second' ? 1 : 60}
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder={ph}
          disabled={disabled}
          autoFocus={autoFocus}
          className={cn(inputClass, className)}
        />
      )
    }

    case FieldType.DATETIME:
      return (
        <DateTimeInput
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder={ph}
          disabled={disabled}
          autoFocus={autoFocus}
          className={cn(inputClass, className)}
        />
      )

    case FieldType.SINGLE_SELECT:
      return (
        <SingleSelectEditor
          value={value}
          onChange={onChange}
          options={options as FdFieldOption[] | FieldSelectOption[] | undefined}
          typeConfig={typeConfig}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
        />
      )

    case FieldType.MULTI_SELECT:
      return (
        <MultiSelectEditor
          value={value}
          onChange={onChange}
          options={options as FdFieldOption[] | FieldSelectOption[] | undefined}
          typeConfig={typeConfig}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
        />
      )

    case FieldType.SINGLE_SELECT_TREE:
      return (
        <TreeSelectEditor
          value={value}
          onChange={onChange}
          treeNodes={treeNodes}
          multi={false}
          leafOnly={(typeConfig.leaf_only as boolean) ?? false}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
        />
      )

    case FieldType.MULTI_SELECT_TREE:
      return (
        <TreeSelectEditor
          value={value}
          onChange={onChange}
          treeNodes={treeNodes}
          multi
          leafOnly={(typeConfig.leaf_only as boolean) ?? false}
          maxSelections={(typeConfig.max_selections as number) ?? undefined}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
        />
      )

    case FieldType.FILE:
      return (
        <FieldFileEditor
          value={value}
          onChange={onChange}
          typeConfig={typeConfig}
          placeholder={ph}
          disabled={disabled}
          className={className}
        />
      )

    case FieldType.USER_SELECT:
      return (
        <UserSelect
          value={toNullableNumber(value)}
          onChange={onChange}
          placeholder={ph}
          disabled={disabled}
          className={className}
          dropdownPlacement={dropdownPlacement}
        />
      )

    case FieldType.ORGANIZATION_SELECT:
      return (
        <OrganizationSelectEditor
          value={toNullableNumber(value)}
          onChange={onChange}
          typeConfig={typeConfig}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
          dropdownPlacement={dropdownPlacement}
        />
      )

    case FieldType.EMPLOYEE_SELECT:
      return (
        <EmployeeSelect
          value={toNullableNumber(value)}
          onChange={onChange}
          groupId={toNullableNumber(typeConfig.group_id)}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
          dropdownPlacement={dropdownPlacement}
        />
      )

    case FieldType.GROUP_SELECT:
      return (
        <EmployeeGroupSelect
          value={toNullableNumber(value)}
          onChange={onChange}
          memberId={toNullableNumber(typeConfig.member_id)}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
          dropdownPlacement={dropdownPlacement}
        />
      )

    case FieldType.RICH_TEXT:
      return (
        <RichTextFieldEditor
          value={value}
          onChange={onChange}
          typeConfig={typeConfig}
          placeholder={ph}
          disabled={disabled}
          className={className}
          autoFocus={autoFocus}
        />
      )

    default:
      return (
        <input
          type="text"
          value={(value as string) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={ph}
          disabled={disabled}
          autoFocus={autoFocus}
          className={cn(inputClass, className)}
        />
      )
  }
}

export function OrganizationSelectEditor({
  value,
  onChange,
  typeConfig,
  placeholder,
  disabled,
  className,
  autoFocus,
  multi = false,
  dropdownPlacement,
}: {
  value: number | number[] | null
  onChange: (value: number | number[] | null) => void
  typeConfig: Record<string, unknown>
  placeholder: string
  disabled: boolean
  className?: string
  autoFocus?: boolean
  multi?: boolean
  dropdownPlacement?: 'top' | 'bottom'
}) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<'top' | 'bottom'>('bottom')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)

  const selectedIds = useMemo(() => {
    if (multi) return Array.isArray(value) ? value : []
    return typeof value === 'number' ? [value] : []
  }, [multi, value])

  const { data: selectedOrganization } = useOrganization(!multi && selectedIds[0] ? selectedIds[0] : 0)
  const { data: organizationsData, isLoading } = useQueryOrganizations({
    search: debouncedSearch || undefined,
    page: 1,
    per_page: 20,
  })

  useEffect(() => {
    if (!autoFocus || disabled) return
    setPlacement(dropdownPlacement ?? getDropdownPlacement(rootRef.current))
    setOpen(true)
  }, [autoFocus, disabled, dropdownPlacement])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (!open) return
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  useEffect(() => {
    if (!open) return
    const updatePlacement = () => setPlacement(dropdownPlacement ?? getDropdownPlacement(rootRef.current))
    updatePlacement()
    window.addEventListener('resize', updatePlacement)
    window.addEventListener('scroll', updatePlacement, true)
    return () => {
      window.removeEventListener('resize', updatePlacement)
      window.removeEventListener('scroll', updatePlacement, true)
    }
  }, [open, dropdownPlacement])

  const options = useMemo<Organization[]>(() => {
    const items = organizationsData?.items ?? []
    if (!selectedOrganization || items.some((item) => item.id === selectedOrganization.id)) return items
    return [selectedOrganization, ...items]
  }, [organizationsData, selectedOrganization])

  const searchPlaceholder =
    (typeConfig.search_placeholder_zh as string | undefined) ??
    (typeConfig.search_placeholder as string | undefined) ??
    placeholder
  const selectedName = useMemo(() => {
    if (selectedIds.length === 0) return ''
    return selectedIds
      .map((id) => options.find((organization) => organization.id === id)?.name ?? `Organization #${id}`)
      .join(', ')
  }, [options, selectedIds])

  const pick = useCallback(
    (organizationId: number | null) => {
      if (multi) {
        if (organizationId == null) {
          onChange([])
          return
        }
        const next = selectedIds.includes(organizationId)
          ? selectedIds.filter((id) => id !== organizationId)
          : [...selectedIds, organizationId]
        onChange(next)
        return
      }
      onChange(organizationId)
      setOpen(false)
      setSearch('')
    },
    [multi, onChange, selectedIds],
  )

  return (
    <div ref={rootRef} className={cn('relative w-full', className)}>
      <div
        className={cn(
          'flex min-h-8 w-full items-center gap-1.5 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-[box-shadow]',
          open && 'ring-1 ring-ring',
          disabled && 'cursor-not-allowed opacity-50',
        )}
      >
        <button
          type="button"
          disabled={disabled}
          className="flex min-w-0 flex-1 items-center text-left disabled:cursor-not-allowed"
          onClick={() => {
            if (!open) setPlacement(dropdownPlacement ?? getDropdownPlacement(rootRef.current))
            setOpen((prev) => !prev)
          }}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          {selectedName ? (
            <span className="truncate text-foreground">{selectedName}</span>
          ) : (
            <span className="truncate text-muted-foreground">{searchPlaceholder}</span>
          )}
        </button>
        {selectedIds.length > 0 && !disabled && (
          <button
            type="button"
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={(event) => {
              event.stopPropagation()
              pick(null)
            }}
            aria-label="Clear organization"
          >
            <IconX size={14} stroke={1.5} />
          </button>
        )}
        <button
          type="button"
          disabled={disabled}
          className="flex h-6 w-6 shrink-0 items-center justify-center text-muted-foreground disabled:cursor-not-allowed"
          onClick={() => {
            if (!open) setPlacement(dropdownPlacement ?? getDropdownPlacement(rootRef.current))
            setOpen((prev) => !prev)
          }}
          aria-label="Open organization list"
        >
          <IconChevronDown size={16} stroke={1.5} />
        </button>
      </div>

      {open && !disabled && (
        <div
          className={cn(
            'absolute left-0 right-0 z-50 rounded-lg border border-border bg-popover p-1.5 text-popover-foreground shadow-md ring-1 ring-foreground/10',
            placement === 'top' ? 'bottom-full mb-1' : 'top-full mt-1',
          )}
          onMouseDown={(event) => event.preventDefault()}
        >
          <div className="flex h-8 items-center gap-1.5 rounded-md border border-input px-2">
            <IconSearch size={14} stroke={1.5} className="shrink-0 text-muted-foreground" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={searchPlaceholder}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              autoFocus
            />
          </div>

          <ul role="listbox" className="mt-1 max-h-60 overflow-y-auto py-1">
            {!multi && (
              <li>
                <button
                  type="button"
                  role="option"
                  aria-selected={selectedIds.length === 0}
                  className="w-full rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-muted/80"
                  onClick={() => pick(null)}
                >
                  无组织
                </button>
              </li>
            )}
            {isLoading ? (
              <li className="px-2 py-3 text-center text-xs text-muted-foreground">加载中...</li>
            ) : options.length === 0 ? (
              <li className="px-2 py-3 text-center text-xs text-muted-foreground">未找到组织</li>
            ) : (
              options.map((organization) => (
                <li key={organization.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selectedIds.includes(organization.id)}
                    className={cn(
                      'flex w-full flex-col rounded-md px-2 py-1.5 text-left transition-colors',
                      selectedIds.includes(organization.id) ? 'bg-primary/10' : 'hover:bg-muted/80',
                    )}
                    onClick={() => pick(organization.id)}
                  >
                    <span className="truncate text-sm text-foreground">{organization.name}</span>
                    {organization.description && (
                      <span className="truncate text-xs text-muted-foreground">{organization.description}</span>
                    )}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  )
}

// ── Number editor with suffix display ──

function NumberEditor({
  value,
  onChange,
  typeConfig,
  placeholder,
  disabled,
  className,
  autoFocus,
}: {
  value: unknown
  onChange: (v: unknown) => void
  typeConfig: Record<string, unknown>
  placeholder: string
  disabled: boolean
  className?: string
  autoFocus?: boolean
}) {
  const suffix = (typeConfig.unit_suffix as string) ?? ''
  const decimals = (typeConfig.decimal_places as number) ?? 0
  const step = decimals > 0 ? 1 / Math.pow(10, decimals) : 1

  return (
    <div className={cn('relative', className)}>
      <input
        type="number"
        value={value != null ? String(value) : ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        step={step}
        min={(typeConfig.min_value as number) ?? undefined}
        max={(typeConfig.max_value as number) ?? undefined}
        placeholder={placeholder}
        disabled={disabled}
        autoFocus={autoFocus}
        className={cn(inputClass, suffix && 'pr-12')}
      />
      {suffix && (
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
          {suffix}
        </span>
      )}
    </div>
  )
}

// ── Single select (dropdown) ──

function SingleSelectEditor({
  value,
  onChange,
  options,
  typeConfig,
  placeholder,
  disabled,
  className,
  autoFocus,
}: {
  value: unknown
  onChange: (v: unknown) => void
  options: (FdFieldOption | FieldSelectOption)[] | undefined
  typeConfig: Record<string, unknown>
  placeholder: string
  disabled: boolean
  className?: string
  autoFocus?: boolean
}) {
  const pillOptions = coalescePillOptions(options, typeConfig)

  return (
    <PillSelectCombobox
      value={value != null && value !== '' ? String(value) : null}
      onChange={(v) => onChange(v)}
      options={pillOptions}
      placeholder={placeholder}
      disabled={disabled}
      className={className}
      autoFocus={autoFocus}
    />
  )
}

// ── Multi select (checkbox list) ──

function MultiSelectEditor({
  value,
  onChange,
  options,
  typeConfig,
  placeholder,
  disabled,
  className,
  autoFocus,
}: {
  value: unknown
  onChange: (v: unknown) => void
  options: (FdFieldOption | FieldSelectOption)[] | undefined
  typeConfig: Record<string, unknown>
  placeholder: string
  disabled: boolean
  className?: string
  autoFocus?: boolean
}) {
  const selected = toStringArray(value)
  const pillOptions = coalescePillOptions(options, typeConfig)

  return (
    <PillMultiSelectField
      value={selected}
      onChange={onChange}
      options={pillOptions}
      placeholder={placeholder}
      disabled={disabled}
      className={className}
      autoFocus={autoFocus}
    />
  )
}
