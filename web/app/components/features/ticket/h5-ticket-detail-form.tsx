'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { cn } from '@/lib/utils'
import type { FdFormLayout, FdFormLayoutField } from '@/models/form-layout'
import type { UnifiedField } from '@/models/field-definition'
import type { FdInteractionRule, InteractionRuleCondition } from '@/models/interaction-rule'
import type { CustomFieldValue, Ticket } from '@/models/ticket'
import { useUpdateTicket } from '@/service/use-tickets'
import { FieldType } from '@/types/field-enums'

type FieldState = 'hidden' | 'required' | 'optional' | 'readonly'

type RelatedEntity = Record<string, unknown> & {
  custom_fields?: Record<string, unknown>
}

type Props = {
  ticket: Ticket
  layout?: FdFormLayout
  rules: FdInteractionRule[]
  fields: UnifiedField[]
  relatedUser?: RelatedEntity
  relatedOrganization?: RelatedEntity
  canEdit: boolean
  isZh: boolean
  onDirtyChange: (dirty: boolean) => void
  onSavingChange: (saving: boolean) => void
  onEditableChange: (editable: boolean) => void
}

export function H5TicketDetailForm({
  ticket,
  layout,
  rules,
  fields,
  relatedUser,
  relatedOrganization,
  canEdit,
  isZh,
  onDirtyChange,
  onSavingChange,
  onEditableChange,
}: Props) {
  const updateTicket = useUpdateTicket()
  const tabs = useMemo(
    () => [...(layout?.tabs ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [layout],
  )
  const [activeTabId, setActiveTabId] = useState<number | null>(null)
  const [editValues, setEditValues] = useState<Record<string, unknown>>({})
  const [baseline, setBaseline] = useState('{}')
  const [errors, setErrors] = useState<Record<string, string>>({})

  const fieldDefMap = useMemo(() => {
    const map = new Map<string, UnifiedField>()
    for (const field of fields) {
      const domains = new Set([field.domain])
      if (field.domain === 'shared_pool' && field.applicable_modules?.includes('ticket')) domains.add('ticket')
      for (const domain of domains) {
        if (field.key) map.set(`${domain}:${field.key}`, field)
        if (field.id != null) map.set(`${domain}:${field.id}`, field)
      }
    }
    return map
  }, [fields])

  const allLayoutFields = useMemo(
    () => tabs.flatMap((tab) => (tab.sections ?? []).flatMap((section) => section.fields ?? [])),
    [tabs],
  )

  const getFieldDef = useCallback((field: FdFormLayoutField) => {
    const domain = field.field_source === 'user'
      ? 'user'
      : field.field_source === 'organization'
        ? 'organization'
        : 'ticket'
    const reference = field.field_key ?? (field.field_definition_id != null ? String(field.field_definition_id) : '')
    return fieldDefMap.get(`${domain}:${reference}`)
  }, [fieldDefMap])

  const getKey = useCallback((field: FdFormLayoutField) => (
    field.field_key ?? (field.field_definition_id != null ? String(field.field_definition_id) : `field_${field.id}`)
  ), [])

  const valueForField = useCallback((field: FdFormLayoutField): unknown => {
    const key = getKey(field)
    const definition = getFieldDef(field)
    if (field.field_source === 'user') return entityValue(relatedUser, key, definition)
    if (field.field_source === 'organization') return entityValue(relatedOrganization, key, definition)
    if (field.field_source === 'ticket_metadata') return (ticket as Record<string, unknown>)[key]
    if (key === 'assignee') return ticket.agent_id
    if (key === 'assignee_group') return ticket.assignee_group_id
    if (SYSTEM_FIELD_KEYS.has(key)) return (ticket as Record<string, unknown>)[key]
    return customValue(ticket.custom_fields, key, definition)
  }, [getFieldDef, getKey, relatedOrganization, relatedUser, ticket])

  const initialTicketValues = useMemo(() => {
    const values: Record<string, unknown> = {}
    for (const field of allLayoutFields) {
      if (field.field_source !== 'ticket') continue
      const key = getKey(field)
      const definition = getFieldDef(field)
      if (key === 'assignee') values[key] = ticket.agent_id
      else if (key === 'assignee_group') values[key] = ticket.assignee_group_id
      else if (SYSTEM_FIELD_KEYS.has(key)) values[key] = (ticket as Record<string, unknown>)[key] ?? null
      else values[key] = customValue(ticket.custom_fields, key, definition)
    }
    return values
  }, [allLayoutFields, getFieldDef, getKey, ticket])

  useEffect(() => {
    const values = initialTicketValues
    const serialized = stableSerialize(values)
    setEditValues(values)
    setBaseline(serialized)
    setErrors({})
    onDirtyChange(false)
  }, [initialTicketValues, onDirtyChange])

  useEffect(() => {
    if (tabs.length && !tabs.some((tab) => tab.id === activeTabId)) setActiveTabId(tabs[0].id)
  }, [activeTabId, tabs])

  const states = useMemo(() => {
    const result = new Map<string, FieldState>()
    for (const field of allLayoutFields) result.set(getKey(field), field.default_state as FieldState)
    for (const rule of rules) {
      if (!evaluateConditions(rule.conditions, rule.condition_logic, editValues)) continue
      for (const action of rule.actions) {
        const key = action.target_field_key ?? (action.target_field_id != null ? String(action.target_field_id) : null)
        if (key) result.set(key, action.state)
      }
    }
    return result
  }, [allLayoutFields, editValues, getKey, rules])

  const isEditable = useCallback((field: FdFormLayoutField) => {
    const state = states.get(getKey(field)) ?? field.default_state as FieldState
    const definition = getFieldDef(field)
    return canEdit
      && field.field_source === 'ticket'
      && field.field_key !== 'conversation_id'
      && (state === 'required' || state === 'optional')
      && definition?.type_config?.readonly !== true
  }, [canEdit, getFieldDef, getKey, states])

  const hasEditable = useMemo(() => allLayoutFields.some(isEditable), [allLayoutFields, isEditable])
  useEffect(() => onEditableChange(hasEditable), [hasEditable, onEditableChange])

  const setValue = (key: string, value: unknown) => {
    setEditValues((previous) => {
      const next = { ...previous, [key]: value }
      onDirtyChange(stableSerialize(next) !== baseline)
      return next
    })
    setErrors((previous) => {
      if (!previous[key]) return previous
      const next = { ...previous }
      delete next[key]
      return next
    })
  }

  const save = async () => {
    const nextErrors: Record<string, string> = {}
    let firstInvalid: FdFormLayoutField | undefined
    for (const field of allLayoutFields) {
      const key = getKey(field)
      if (!isEditable(field) || states.get(key) !== 'required') continue
      const value = editValues[key]
      if (value == null || value === '' || (Array.isArray(value) && value.length === 0)) {
        nextErrors[key] = isZh ? '此字段为必填项' : 'This field is required'
        firstInvalid ??= field
      }
    }
    if (firstInvalid) {
      const parentTab = tabs.find((tab) => tab.sections?.some((section) => section.fields?.some((field) => field.id === firstInvalid?.id)))
      if (parentTab) setActiveTabId(parentTab.id)
      setErrors(nextErrors)
      window.requestAnimationFrame(() => document.getElementById(`h5-ticket-field-${getKey(firstInvalid!)}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
      return
    }

    const payload: Record<string, unknown> = {}
    const customFields: Record<string, CustomFieldValue> = {}
    for (const field of allLayoutFields) {
      if (!isEditable(field)) continue
      const key = getKey(field)
      const payloadKey = key === 'assignee' ? 'agent_id' : key === 'assignee_group' ? 'assignee_group_id' : key
      const value = editValues[key]
      if (SYSTEM_PAYLOAD_KEYS.has(payloadKey)) payload[payloadKey] = value
      else {
        const definition = getFieldDef(field)
        const customKey = definition?.key ?? (definition?.id != null ? String(definition.id) : payloadKey)
        customFields[customKey] = value as CustomFieldValue
      }
    }

    onSavingChange(true)
    try {
      await updateTicket.mutateAsync({
        id: ticket.id,
        data: {
          title: payload.title as string | undefined,
          description: payload.description as string | undefined,
          status: payload.status as string | undefined,
          priority: payload.priority as string | undefined,
          conversation_id: payload.conversation_id as number | undefined,
          call_record_id: payload.call_record_id as number | undefined,
          user_id: payload.user_id as number | undefined,
          agent_id: payload.agent_id as number | undefined,
          assignee_group_id: payload.assignee_group_id as number | undefined,
          custom_fields: customFields,
        },
      })
      const serialized = stableSerialize(editValues)
      setBaseline(serialized)
      onDirtyChange(false)
      toast.success(isZh ? '保存成功' : 'Saved successfully')
    } catch {
      toast.error(isZh ? '操作失败，请重试' : 'Operation failed. Please try again')
    } finally {
      onSavingChange(false)
    }
  }

  if (!layout || tabs.length === 0) {
    return <div className="p-4 text-sm text-muted-foreground">{isZh ? '未配置工单详情布局' : 'No ticket detail layout configured'}</div>
  }

  const activeTab = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0]

  return (
    <form id="h5-ticket-detail-form" onSubmit={(event) => { event.preventDefault(); void save() }} className="flex flex-col">
      {tabs.length > 1 && (
        <div className="flex shrink-0 overflow-x-auto border-b border-border px-4">
          {tabs.map((tab) => (
            <button key={tab.id} type="button" onClick={() => setActiveTabId(tab.id)} className={cn('h-12 shrink-0 border-b-2 px-4 text-sm', activeTab.id === tab.id ? 'border-primary font-semibold' : 'border-transparent text-muted-foreground')}>
              {tab.name}
            </button>
          ))}
        </div>
      )}
      <div className="flex flex-col gap-5 p-4 pb-6">
        {[...(activeTab.sections ?? [])].sort((a, b) => a.sort_order - b.sort_order).map((section) => {
          const visibleFields = [...(section.fields ?? [])]
            .sort((a, b) => a.sort_order - b.sort_order)
            .filter((field) => states.get(getKey(field)) !== 'hidden')
          if (!visibleFields.length) return null
          return (
            <section key={section.id} className="flex flex-col gap-3">
              {section.name && <h3 className="text-xs font-semibold text-muted-foreground">{section.name}</h3>}
              {visibleFields.map((field) => {
                const key = getKey(field)
                const definition = getFieldDef(field)
                const value = field.field_source === 'ticket' ? editValues[key] : valueForField(field)
                const state = states.get(key) ?? field.default_state as FieldState
                const editable = isEditable(field)
                const fieldType = (definition?.field_type ?? inferFieldType(key)) as FieldType
                return (
                  <div id={`h5-ticket-field-${key}`} key={field.id} className="flex flex-col gap-1.5">
                    <label className="text-[13px] font-medium">
                      {definition?.name ?? key}
                      {state === 'required' && <span className="ml-0.5 text-destructive">*</span>}
                    </label>
                    {editable ? (
                      <UnifiedFieldValueEditor
                        field={definition ?? fallbackField(key, fieldType)}
                        value={value}
                        onChange={(next) => setValue(key, next)}
                        typeConfig={dependentTypeConfig(definition, key, editValues)}
                        placeholder={isZh ? '请选择或输入' : 'Select or enter'}
                      />
                    ) : (
                      <div className="min-h-10 rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                        <FieldValueDisplay fieldType={fieldType} value={value} typeConfig={definition?.type_config} options={definition?.options} treeNodes={definition?.tree_nodes} />
                      </div>
                    )}
                    {errors[key] && <p className="text-xs text-destructive">{errors[key]}</p>}
                  </div>
                )
              })}
            </section>
          )
        })}
      </div>
    </form>
  )
}

const SYSTEM_FIELD_KEYS = new Set(['title', 'description', 'status', 'priority', 'ticket_number', 'conversation_id', 'call_record_id', 'user_id', 'agent_id', 'assignee_group_id', 'created_by', 'updated_by', 'created_at', 'updated_at'])
const SYSTEM_PAYLOAD_KEYS = new Set(['title', 'description', 'status', 'priority', 'conversation_id', 'call_record_id', 'user_id', 'agent_id', 'assignee_group_id'])

function entityValue(entity: RelatedEntity | undefined, key: string, field?: UnifiedField): unknown {
  if (!entity) return null
  if (key in entity) return entity[key]
  return customValue(entity.custom_fields, key, field)
}

function customValue(values: Record<string, unknown> | undefined, key: string, field?: UnifiedField): unknown {
  if (!values) return null
  for (const candidate of [key, field?.key, field?.id != null ? String(field.id) : undefined, field?.slot_column]) {
    if (candidate && candidate in values) return values[candidate]
  }
  return null
}

function inferFieldType(key: string): FieldType {
  if (key === 'assignee' || key === 'agent_id') return FieldType.EMPLOYEE_SELECT
  if (key === 'assignee_group' || key === 'assignee_group_id') return FieldType.GROUP_SELECT
  if (key === 'user_id') return FieldType.USER_SELECT
  if (key === 'created_at' || key === 'updated_at') return FieldType.DATETIME
  return FieldType.SINGLE_LINE_TEXT
}

function fallbackField(key: string, fieldType: FieldType): UnifiedField {
  return { key, id: null, domain: 'ticket', source: 'system', name: key, description: null, help_text: null, field_type: fieldType, type_config: {}, applicable_modules: null, slot_column: null, show_in_workspace: null, sort_order: 0, status: 'active', options: [], tree_nodes: [], created_at: null, updated_at: null }
}

function dependentTypeConfig(field: UnifiedField | undefined, key: string, values: Record<string, unknown>): Record<string, unknown> {
  const result = { ...(field?.type_config ?? {}) }
  if (key === 'assignee') {
    const groupId = values.assignee_group ?? values.assignee_group_id
    if (typeof groupId === 'number') result.group_id = groupId
  }
  if (key === 'assignee_group') {
    const memberId = values.assignee ?? values.agent_id
    if (typeof memberId === 'number') result.member_id = memberId
  }
  return result
}

function evaluateConditions(conditions: InteractionRuleCondition[], logic: 'and' | 'or', values: Record<string, unknown>): boolean {
  if (!conditions.length) return false
  const results = conditions.map((condition) => {
    const key = condition.field_key ?? (condition.field_id != null ? String(condition.field_id) : '')
    return evaluateOperator(values[key], condition.operator, condition.value)
  })
  return logic === 'and' ? results.every(Boolean) : results.some(Boolean)
}

function evaluateOperator(current: unknown, operator: string, expected: unknown): boolean {
  const left = current == null ? '' : String(current)
  const right = expected == null ? '' : String(expected)
  switch (operator) {
    case 'eq': case 'equals': case '=': return left === right
    case 'ne': case 'not_equals': case '!=': return left !== right
    case 'contains': case 'like': return left.toLowerCase().includes(right.toLowerCase())
    case 'not_contains': return !left.toLowerCase().includes(right.toLowerCase())
    case 'starts_with': return left.toLowerCase().startsWith(right.toLowerCase())
    case 'ends_with': return left.toLowerCase().endsWith(right.toLowerCase())
    case 'is_empty': case 'is_null': return Array.isArray(current) ? current.length === 0 : left === ''
    case 'is_not_empty': case 'is_not_null': return Array.isArray(current) ? current.length > 0 : left !== ''
    case 'in': return Array.isArray(expected) && expected.map(String).includes(left)
    case 'not_in': return Array.isArray(expected) && !expected.map(String).includes(left)
    case 'gt': return Number(left) > Number(right)
    case 'gte': return Number(left) >= Number(right)
    case 'lt': return Number(left) < Number(right)
    case 'lte': return Number(left) <= Number(right)
    default: return false
  }
}

function stableSerialize(value: Record<string, unknown>): string {
  return JSON.stringify(Object.fromEntries(Object.entries(value).sort(([left], [right]) => left.localeCompare(right))))
}
