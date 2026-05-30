'use client'

import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { IconChevronDown, IconChevronRight } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { useFormLayoutByScene, useInteractionRules, useCreateTicket } from '@/service/use-tickets'
import { useUnifiedFields } from '@/service/use-field-definitions'
import type { FdFormLayoutTab, FdFormLayoutSection, FdFormLayoutField } from '@/models/form-layout'
import type { FdInteractionRule, InteractionRuleCondition } from '@/models/interaction-rule'
import type { UnifiedField } from '@/models/field-definition'
import type { CustomFieldValue, Ticket } from '@/models/ticket'
import { FieldType } from '@/types/field-enums'
import {
  FieldValueEditor,
  UnifiedFieldValueEditor,
} from '@/app/components/features/field-system/field-value-editor'
import {
  coalescePillOptions,
} from '@/app/components/features/field-system/field-select-pill-editors'
import { collectLayoutFieldDefaults, mergeCustomFieldDefaultsIntoForm } from '@/lib/ticket-field-defaults'

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

type FieldState = 'hidden' | 'required' | 'optional' | 'readonly'

type Props = {
  onClose: () => void
  onSuccess: (ticket: Ticket) => void
}

type TicketCreateFormProps = {
  initialValues?: Record<string, unknown>
  resetKey?: string | number
  columnsPerRowOverride?: number
  labelPositionOverride?: string
  className?: string
  bodyClassName?: string
  footerClassName?: string
  submitLabel?: string
  submittingLabel?: string
  cancelLabel?: string
  onCancel: () => void
  onSuccess: (ticket: Ticket) => void
  onError?: () => void
  onValuesChange?: (values: Record<string, unknown>) => void
}

const DEFAULT_CREATE_VALUES: Record<string, unknown> = {
  status: 'open',
  priority: 'medium',
}

export function TicketFormModal({ onClose, onSuccess }: Props) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="sm:max-w-[720px] max-h-[85vh] flex flex-col gap-0 p-0"
      >
        <DialogHeader className="px-6 py-4 border-b">
          <DialogTitle>{isZh ? '新建工单' : 'Create Ticket'}</DialogTitle>
        </DialogHeader>
        <TicketCreateForm
          onCancel={onClose}
          onSuccess={(ticket) => {
            onSuccess(ticket)
            onClose()
          }}
          bodyClassName="px-6 py-4"
          footerClassName="px-6 py-4"
        />
      </DialogContent>
    </Dialog>
  )
}

export function TicketCreateForm({
  initialValues,
  resetKey = 'default',
  columnsPerRowOverride,
  labelPositionOverride,
  className,
  bodyClassName,
  footerClassName,
  submitLabel,
  submittingLabel,
  cancelLabel,
  onCancel,
  onSuccess,
  onError,
  onValuesChange,
}: TicketCreateFormProps) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'

  const { data: layout, isLoading: layoutLoading } = useFormLayoutByScene('new_ticket')
  const { data: rulesData } = useInteractionRules(layout?.id)
  const { data: ticketFieldsData } = useUnifiedFields({
    domain: 'ticket',
    include_metadata: false,
    locale: isZh ? 'zh' : 'en',
  })
  const { data: sharedFieldsData } = useUnifiedFields({
    domain: 'shared_pool',
    include_metadata: false,
    locale: isZh ? 'zh' : 'en',
  })

  const createTicket = useCreateTicket()

  const rules: FdInteractionRule[] = useMemo(
    () => (rulesData?.items ?? []).filter((r) => r.is_enabled).sort((a, b) => a.sort_order - b.sort_order),
    [rulesData],
  )

  const fieldDefMap = useMemo(() => {
    const m = new Map<string, UnifiedField>()
    const allFields = [...(ticketFieldsData?.items ?? []), ...(sharedFieldsData?.items ?? [])]
    for (const f of allFields) {
      if (f.id != null) m.set(String(f.id), f)
      if (f.key) m.set(f.key, f)
    }
    return m
  }, [ticketFieldsData, sharedFieldsData])

  const initialValuesRef = useRef(initialValues)
  initialValuesRef.current = initialValues

  const [formValues, setFormValues] = useState<Record<string, unknown>>(() => ({
    ...DEFAULT_CREATE_VALUES,
    ...(initialValues ?? {}),
  }))
  const [activeTab, setActiveTab] = useState(0)
  const [collapsedSections, setCollapsedSections] = useState<Set<number>>(new Set())
  const [submitting, setSubmitting] = useState(false)

  const tabs = useMemo(() => {
    if (!layout?.tabs) return []
    return [...layout.tabs].sort((a, b) => a.sort_order - b.sort_order)
  }, [layout])

  useEffect(() => {
    if (tabs.length > 0 && activeTab >= tabs.length) setActiveTab(0)
  }, [tabs, activeTab])

  useEffect(() => {
    setFormValues({
      ...DEFAULT_CREATE_VALUES,
      ...collectLayoutFieldDefaults(layout, fieldDefMap),
      ...(initialValues ?? {}),
    })
    setActiveTab(0)
    setCollapsedSections(new Set())
  }, [resetKey]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setFormValues((prev) =>
      mergeCustomFieldDefaultsIntoForm(prev, layout, fieldDefMap, initialValuesRef.current),
    )
  }, [layout, fieldDefMap])

  useEffect(() => {
    onValuesChange?.(formValues)
  }, [formValues, onValuesChange])

  const setFieldValue = useCallback((key: string, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [key]: value }))
  }, [])

  const toggleSection = useCallback((sectionId: number) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev)
      if (next.has(sectionId)) next.delete(sectionId)
      else next.add(sectionId)
      return next
    })
  }, [])

  const getFieldKey = useCallback((field: FdFormLayoutField): string => {
    if (field.field_key) return field.field_key
    if (field.field_definition_id) return String(field.field_definition_id)
    return `field_${field.id}`
  }, [])

  const getFieldDef = useCallback((field: FdFormLayoutField): UnifiedField | undefined => {
    if (field.field_key) return fieldDefMap.get(field.field_key)
    if (field.field_definition_id) return fieldDefMap.get(String(field.field_definition_id))
    return undefined
  }, [fieldDefMap])

  const computedFieldStates = useMemo(() => {
    const states = new Map<string, FieldState>()

    const allLayoutFields: FdFormLayoutField[] = []
    for (const tab of tabs) {
      for (const section of (tab.sections ?? [])) {
        for (const field of (section.fields ?? [])) {
          allLayoutFields.push(field)
          states.set(getFieldKey(field), field.default_state as FieldState)
        }
      }
    }

    for (const rule of rules) {
      const conditionsMet = evaluateConditions(rule.conditions, rule.condition_logic, formValues, getFieldKey, allLayoutFields)
      if (conditionsMet) {
        for (const action of rule.actions) {
          const targetKey = action.target_field_key ?? (action.target_field_id ? String(action.target_field_id) : null)
          if (targetKey) {
            states.set(targetKey, action.state)
          }
        }
      }
    }

    return states
  }, [tabs, rules, formValues, getFieldKey])

  const allowedFormKeys = useMemo(() => {
    const keys = new Set(['title', 'description', 'status', 'priority', 'conversation_id', 'call_record_id', 'user_id', 'agent_id', 'assignee_group_id'])
    for (const tab of tabs) {
      for (const section of (tab.sections ?? [])) {
        for (const field of (section.fields ?? [])) {
          keys.add(getFieldKey(field))
        }
      }
    }
    return keys
  }, [tabs, getFieldKey])

  const handleSubmit = useCallback(async () => {
    if (submitting) return
    setSubmitting(true)

    try {
      const systemFields = ['title', 'description', 'status', 'priority', 'conversation_id', 'call_record_id', 'user_id', 'agent_id', 'assignee_group_id']
      const payload: Record<string, unknown> = {}
      const customFields: Record<string, unknown> = {}

      for (const [key, value] of Object.entries(formValues)) {
        if (!allowedFormKeys.has(key)) continue
        if (Array.isArray(value) && value.length === 0) continue
        if (value === '' || value === null || value === undefined) continue
        const payloadKey = key === 'assignee' ? 'agent_id' : key === 'assignee_group' ? 'assignee_group_id' : key
        if (systemFields.includes(payloadKey)) {
          payload[payloadKey] = value
        } else {
          customFields[payloadKey] = value
        }
      }

      if (!payload.title) {
        setSubmitting(false)
        return
      }

      if (layout?.id) {
        payload.layout_id = layout.id
      }

      const ticket = await createTicket.mutateAsync({
        title: String(payload.title),
        description: payload.description as string | undefined,
        status: (payload.status as string) || 'open',
        priority: (payload.priority as string) || 'medium',
        layout_id: payload.layout_id as number | undefined,
        conversation_id: payload.conversation_id as number | undefined,
        call_record_id: payload.call_record_id as number | undefined,
        user_id: payload.user_id as number | undefined,
        agent_id: payload.agent_id as number | undefined,
        assignee_group_id: payload.assignee_group_id as number | undefined,
        custom_fields: customFields as Record<string, CustomFieldValue>,
      })
      onSuccess(ticket)
    } catch {
      onError?.()
    } finally {
      setSubmitting(false)
    }
  }, [submitting, formValues, allowedFormKeys, layout, createTicket, onSuccess, onError])

  const columnsPerRow = columnsPerRowOverride ?? layout?.columns_per_row ?? 1
  const labelPosition = labelPositionOverride ?? layout?.label_position ?? 'left'

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col gap-0', className)}>
        {/* Tab bar */}
        {tabs.length > 1 && (
          <div className="flex shrink-0 gap-1 border-b px-4">
            {tabs.map((tab, idx) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(idx)}
                className={cn(
                  'border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                  activeTab === idx
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                {tab.name}
              </button>
            ))}
          </div>
        )}

        {/* Body */}
        <div className={cn('min-h-0 flex-1 overflow-y-auto', bodyClassName)}>
          {layoutLoading ? (
            <div className="flex items-center justify-center py-10">
              <p className="text-sm text-muted-foreground">Loading...</p>
            </div>
          ) : !layout ? (
            <NoLayoutFallback
              isZh={isZh}
              formValues={formValues}
              setFieldValue={setFieldValue}
              statusFieldDef={fieldDefMap.get('status')}
              priorityFieldDef={fieldDefMap.get('priority')}
              descriptionFieldDef={fieldDefMap.get('description')}
            />
          ) : tabs[activeTab] ? (
            <TabContent
              tab={tabs[activeTab]}
              columnsPerRow={columnsPerRow}
              labelPosition={labelPosition}
              formValues={formValues}
              setFieldValue={setFieldValue}
              fieldStates={computedFieldStates}
              getFieldKey={getFieldKey}
              getFieldDef={getFieldDef}
              collapsedSections={collapsedSections}
              toggleSection={toggleSection}
              isZh={isZh}
            />
          ) : null}
        </div>

        <DialogFooter className={cn('shrink-0', footerClassName)}>
          <Button variant="outline" onClick={onCancel}>
            {cancelLabel ?? (isZh ? '取消' : 'Cancel')}
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting
              ? (submittingLabel ?? (isZh ? '创建中...' : 'Creating...'))
              : (submitLabel ?? (isZh ? '创建' : 'Create'))}
          </Button>
        </DialogFooter>
    </div>
  )
}

// ── Tab content renderer ──

function TabContent({
  tab,
  columnsPerRow,
  labelPosition,
  formValues,
  setFieldValue,
  fieldStates,
  getFieldKey,
  getFieldDef,
  collapsedSections,
  toggleSection,
  isZh,
}: {
  tab: FdFormLayoutTab
  columnsPerRow: number
  labelPosition: string
  formValues: Record<string, unknown>
  setFieldValue: (key: string, value: unknown) => void
  fieldStates: Map<string, FieldState>
  getFieldKey: (f: FdFormLayoutField) => string
  getFieldDef: (f: FdFormLayoutField) => UnifiedField | undefined
  collapsedSections: Set<number>
  toggleSection: (id: number) => void
  isZh: boolean
}) {
  const sections = useMemo(
    () => [...(tab.sections ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [tab.sections],
  )

  return (
    <div className="flex flex-col gap-4">
      {sections.map((section) => (
        <SectionContent
          key={section.id}
          section={section}
          columnsPerRow={columnsPerRow}
          labelPosition={labelPosition}
          formValues={formValues}
          setFieldValue={setFieldValue}
          fieldStates={fieldStates}
          getFieldKey={getFieldKey}
          getFieldDef={getFieldDef}
          collapsed={collapsedSections.has(section.id)}
          onToggle={() => toggleSection(section.id)}
          isZh={isZh}
        />
      ))}
    </div>
  )
}

// ── Section content renderer ──

function SectionContent({
  section,
  columnsPerRow,
  labelPosition,
  formValues,
  setFieldValue,
  fieldStates,
  getFieldKey,
  getFieldDef,
  collapsed,
  onToggle,
  isZh,
}: {
  section: FdFormLayoutSection
  columnsPerRow: number
  labelPosition: string
  formValues: Record<string, unknown>
  setFieldValue: (key: string, value: unknown) => void
  fieldStates: Map<string, FieldState>
  getFieldKey: (f: FdFormLayoutField) => string
  getFieldDef: (f: FdFormLayoutField) => UnifiedField | undefined
  collapsed: boolean
  onToggle: () => void
  isZh: boolean
}) {
  const fields = useMemo(
    () => [...(section.fields ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [section.fields],
  )

  const visibleFields = useMemo(
    () => fields.filter((f) => fieldStates.get(getFieldKey(f)) !== 'hidden'),
    [fields, fieldStates, getFieldKey],
  )

  if (visibleFields.length === 0) return null

  return (
    <div className="flex flex-col gap-3">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 py-1.5 text-left"
      >
        {collapsed
          ? <IconChevronRight size={16} className="shrink-0 text-muted-foreground" />
          : <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />}
        <span className="text-sm font-medium">{section.name}</span>
      </button>

      {!collapsed && (
        <div>
          <div
            className="grid gap-x-6 gap-y-4"
            style={{ gridTemplateColumns: `repeat(${columnsPerRow}, minmax(0, 1fr))` }}
          >
            {visibleFields.map((field) => {
              const key = getFieldKey(field)
              const def = getFieldDef(field)
              const state = fieldStates.get(key) ?? field.default_state as FieldState
              const span = Math.min(field.column_span, columnsPerRow)

              return (
                <div
                  key={field.id}
                  style={{ gridColumn: `span ${span} / span ${span}` }}
                >
                  <FieldInput
                    field={field}
                    fieldDef={def}
                    fieldKey={key}
                    state={state}
                    value={formValues[key]}
                    onChange={(val) => setFieldValue(key, val)}
                    formValues={formValues}
                    labelPosition={labelPosition}
                    isZh={isZh}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Field input renderer ──

function FieldInput({
  field,
  fieldDef,
  fieldKey,
  state,
  value,
  onChange,
  formValues,
  labelPosition,
  isZh,
}: {
  field: FdFormLayoutField
  fieldDef: UnifiedField | undefined
  fieldKey: string
  state: FieldState
  value: unknown
  onChange: (val: unknown) => void
  formValues: Record<string, unknown>
  labelPosition: string
  isZh: boolean
}) {
  const label = fieldDef?.name ?? field.field_key ?? `Field ${field.id}`
  const isRequired = state === 'required'
  const isReadonly = state === 'readonly' || fieldKey === 'conversation_id' || fieldDef?.type_config?.readonly === true

  const fieldType = fieldDef?.field_type ?? FieldType.SINGLE_LINE_TEXT

  const isLabelLeft = labelPosition === 'left'

  const editorField = useMemo<UnifiedField>(() => (
    fieldDef ?? {
      key: fieldKey,
      id: null,
      domain: 'ticket',
      source: 'system',
      name: label,
      description: null,
      help_text: null,
      field_type: FieldType.SINGLE_LINE_TEXT,
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
  ), [fieldDef, fieldKey, label])

  const editorTypeConfig = useMemo(() => {
    const base = { ...((fieldDef?.type_config ?? {}) as Record<string, unknown>) }

    if (fieldType === FieldType.EMPLOYEE_SELECT) {
      const groupValue = formValues.assignee_group ?? formValues.assignee_group_id
      if (typeof groupValue === 'number') base.group_id = groupValue
    }

    if (fieldType === FieldType.GROUP_SELECT) {
      const assigneeValue = formValues.assignee ?? formValues.agent_id
      if (typeof assigneeValue === 'number') base.member_id = assigneeValue
    }

    return base
  }, [fieldDef, fieldType, formValues.assignee_group, formValues.assignee_group_id, formValues.assignee, formValues.agent_id])

  const placeholder = fieldPlaceholder(editorField, isZh)

  const isTallControl =
    fieldType === 'multi_line_text' ||
    fieldType === 'rich_text' ||
    fieldType === 'single_select_tree' ||
    fieldType === 'multi_select_tree' ||
    fieldType === FieldType.FILE

  return (
    <div className={cn(isLabelLeft ? 'flex items-start gap-3' : 'flex flex-col gap-1.5')}>
      <Label
        className={cn(
          'whitespace-nowrap text-muted-foreground',
          isLabelLeft && 'w-[80px] shrink-0 text-right',
          isLabelLeft && !isTallControl && 'leading-8',
          isLabelLeft && isTallControl && 'pt-2',
        )}
      >
        {label}
        {isRequired && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      <div className={cn(isLabelLeft && 'min-w-0 flex-1')}>
        <UnifiedFieldValueEditor
          field={editorField}
          value={value}
          onChange={onChange}
          typeConfig={editorTypeConfig}
          placeholder={placeholder}
          disabled={isReadonly}
          dropdownPlacement="top"
        />
      </div>
    </div>
  )
}

function fieldPlaceholder(field: UnifiedField, isZh: boolean): string {
  const config = field.type_config ?? {}
  const localizedSearch = isZh ? config.search_placeholder_zh : config.search_placeholder_en
  if (typeof localizedSearch === 'string' && localizedSearch) return localizedSearch
  if (typeof config.placeholder === 'string' && config.placeholder) return config.placeholder

  switch (field.field_type) {
    case FieldType.SINGLE_SELECT:
    case FieldType.SINGLE_SELECT_TREE:
    case FieldType.MULTI_SELECT:
    case FieldType.MULTI_SELECT_TREE:
    case FieldType.DATE:
    case FieldType.TIME:
    case FieldType.DATETIME:
    case FieldType.USER_SELECT:
    case FieldType.ORGANIZATION_SELECT:
    case FieldType.EMPLOYEE_SELECT:
    case FieldType.GROUP_SELECT:
      return isZh ? '请选择' : 'Select...'
    case FieldType.FILE:
      return isZh ? '选择文件上传' : 'Upload files'
    default:
      return isZh ? '请输入' : 'Enter...'
  }
}

// ── Interaction rule evaluation ──

function evaluateConditions(
  conditions: InteractionRuleCondition[],
  logic: 'and' | 'or',
  formValues: Record<string, unknown>,
  getFieldKey: (f: FdFormLayoutField) => string,
  _allFields: FdFormLayoutField[],
): boolean {
  if (!conditions || conditions.length === 0) return false

  const results = conditions.map((cond) => {
    const key = cond.field_key ?? (cond.field_id ? String(cond.field_id) : null)
    if (!key) return false
    const current = formValues[key]
    return evaluateOperator(current, cond.operator, cond.value)
  })

  return logic === 'and' ? results.every(Boolean) : results.some(Boolean)
}

function evaluateOperator(current: unknown, operator: string, expected: unknown): boolean {
  const strCurrent = current != null ? String(current) : ''
  const strExpected = expected != null ? String(expected) : ''
  const numCurrent = Number(strCurrent)
  const numExpected = Number(strExpected)
  const canCompareAsNumber = Number.isFinite(numCurrent) && Number.isFinite(numExpected)
  const compare = canCompareAsNumber ? numCurrent - numExpected : strCurrent.localeCompare(strExpected)

  switch (operator) {
    case 'eq':
    case 'equals':
    case '=':
      return strCurrent === strExpected
    case 'ne':
    case 'not_equals':
    case '!=':
      return strCurrent !== strExpected
    case 'contains':
    case 'like':
      return strCurrent.toLowerCase().includes(strExpected.toLowerCase())
    case 'not_contains':
      return !strCurrent.toLowerCase().includes(strExpected.toLowerCase())
    case 'starts_with':
      return strCurrent.toLowerCase().startsWith(strExpected.toLowerCase())
    case 'ends_with':
      return strCurrent.toLowerCase().endsWith(strExpected.toLowerCase())
    case 'gt':
      return compare > 0
    case 'gte':
      return compare >= 0
    case 'lt':
      return compare < 0
    case 'lte':
      return compare <= 0
    case 'is_empty':
    case 'is_null':
      return Array.isArray(current) ? current.length === 0 : strCurrent === ''
    case 'is_not_empty':
    case 'is_not_null':
      return Array.isArray(current) ? current.length > 0 : strCurrent !== ''
    case 'in':
      if (Array.isArray(expected)) return expected.map(String).includes(strCurrent)
      return false
    case 'not_in':
      if (Array.isArray(expected)) return !expected.map(String).includes(strCurrent)
      return false
    default:
      return false
  }
}

// ── Fallback when no layout configured ──

function NoLayoutFallback({
  isZh,
  formValues,
  setFieldValue,
  statusFieldDef,
  priorityFieldDef,
  descriptionFieldDef,
}: {
  isZh: boolean
  formValues: Record<string, unknown>
  setFieldValue: (key: string, value: unknown) => void
  statusFieldDef: UnifiedField | undefined
  priorityFieldDef: UnifiedField | undefined
  descriptionFieldDef: UnifiedField | undefined
}) {
  const statusOpts = useMemo(
    () => coalescePillOptions(statusFieldDef?.options ?? [], statusFieldDef?.type_config ?? {}),
    [statusFieldDef],
  )
  const priorityOpts = useMemo(
    () => coalescePillOptions(priorityFieldDef?.options ?? [], priorityFieldDef?.type_config ?? {}),
    [priorityFieldDef],
  )
  const descFieldType = descriptionFieldDef?.field_type ?? FieldType.RICH_TEXT
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        {isZh ? '未配置新建工单表单布局，使用默认字段' : 'No form layout configured for new ticket, using default fields'}
      </p>
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>
            {isZh ? '标题' : 'Title'}<span className="ml-0.5 text-destructive">*</span>
          </Label>
          <Input
            value={String(formValues.title ?? '')}
            onChange={(e) => setFieldValue('title', e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label>{isZh ? '描述' : 'Description'}</Label>
          {descFieldType === FieldType.RICH_TEXT ? (
            <FieldValueEditor
              fieldType={FieldType.RICH_TEXT}
              value={formValues.description}
              onChange={(v) => setFieldValue('description', v)}
              typeConfig={(descriptionFieldDef?.type_config ?? {}) as Record<string, unknown>}
              placeholder={isZh ? '请输入' : 'Enter...'}
            />
          ) : descFieldType === FieldType.MULTI_LINE_TEXT ? (
            <Textarea
              value={String(formValues.description ?? '')}
              onChange={(e) => setFieldValue('description', e.target.value)}
              rows={4}
              placeholder={isZh ? '请输入' : 'Enter...'}
            />
          ) : (
            <Input
              value={String(formValues.description ?? '')}
              onChange={(e) => setFieldValue('description', e.target.value)}
              placeholder={isZh ? '请输入' : 'Enter...'}
            />
          )}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>{isZh ? '状态' : 'Status'}</Label>
            <select
              value={String(formValues.status ?? 'open')}
              onChange={(e) => setFieldValue('status', e.target.value)}
              className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {statusOpts.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>{isZh ? '优先级' : 'Priority'}</Label>
            <select
              value={String(formValues.priority ?? 'medium')}
              onChange={(e) => setFieldValue('priority', e.target.value)}
              className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {priorityOpts.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  )
}
