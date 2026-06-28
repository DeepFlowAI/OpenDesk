import type { UnifiedField } from '@/models/field-definition'
import { FieldType } from '@/types/field-enums'

const LINKED_ASSIGNEE_DOMAINS = new Set(['user', 'ticket'])

export function getLinkedSelectTypeConfig(
  field: UnifiedField,
  fields: UnifiedField[],
  resolveValue: (field: UnifiedField) => unknown,
): Record<string, unknown> {
  const base = { ...((field.type_config ?? {}) as Record<string, unknown>) }

  if (!isSystemAssigneeField(field)) return base

  if (field.field_type === FieldType.EMPLOYEE_SELECT && field.key === 'assignee') {
    const groupField = findLinkedSelectField(field, fields, FieldType.GROUP_SELECT, 'assignee_group')
    const groupId = groupField ? toNullableNumber(resolveValue(groupField)) : null
    if (groupId != null) base.group_id = groupId
  }

  if (field.field_type === FieldType.GROUP_SELECT && field.key === 'assignee_group') {
    const employeeField = findLinkedSelectField(field, fields, FieldType.EMPLOYEE_SELECT, 'assignee')
    const memberId = employeeField ? toNullableNumber(resolveValue(employeeField)) : null
    if (memberId != null) base.member_id = memberId
  }

  return base
}

function findLinkedSelectField(
  field: UnifiedField,
  fields: UnifiedField[],
  fieldType: FieldType,
  key: string,
): UnifiedField | null {
  return fields.find((item) => item !== field && isSystemAssigneeField(item) && item.field_type === fieldType && item.key === key) ?? null
}

function isSystemAssigneeField(field: UnifiedField): boolean {
  return (
    field.source === 'system' &&
    LINKED_ASSIGNEE_DOMAINS.has(field.domain) &&
    (field.key === 'assignee' || field.key === 'assignee_group')
  )
}

function toNullableNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}
