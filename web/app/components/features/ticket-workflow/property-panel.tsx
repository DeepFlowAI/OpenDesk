'use client'

import { useEffect, useState } from 'react'
import { IconPlus, IconTrash, IconX } from '@tabler/icons-react'
import type { UnifiedField } from '@/models/field-definition'
import { FilterValueEditor } from '@/components/filter'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import {
  fieldRefFromUid,
  fieldUid,
  type BranchData,
  type BranchItem,
  type TicketWorkflowNode,
  type TriggerData,
  type UpdateRecordData,
  type WorkflowCondition,
} from '@/models/ticket-workflow-graph'

const NO_VALUE_OPERATORS = new Set(['is_empty', 'is_not_empty'])
const CHANGE_SCOPES = new Set(['changed', 'not_changed'])
const WRITABLE_SYSTEM_KEYS = new Set(['title', 'description', 'status', 'priority', 'assignee', 'assignee_group', 'user_id'])

// Comparison operators by field type. The "changed / not_changed" checks are
// surfaced as value-scope modes instead of operators (see ConditionRow).
const OPERATORS_BY_TYPE: Record<string, string[]> = {
  single_line_text: ['is_empty', 'is_not_empty', 'eq', 'ne', 'contains', 'not_contains', 'starts_with', 'ends_with'],
  multi_line_text: ['is_empty', 'is_not_empty', 'eq', 'ne', 'contains', 'not_contains', 'starts_with', 'ends_with'],
  email: ['is_empty', 'is_not_empty', 'eq', 'ne', 'contains', 'not_contains', 'starts_with', 'ends_with'],
  phone: ['is_empty', 'is_not_empty', 'eq', 'ne', 'contains', 'not_contains', 'starts_with', 'ends_with'],
  url: ['is_empty', 'is_not_empty', 'eq', 'ne', 'contains', 'not_contains', 'starts_with', 'ends_with'],
  rich_text: ['is_empty', 'is_not_empty', 'contains', 'not_contains'],
  number: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],
  date: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],
  time: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],
  datetime: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],
  single_select: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  single_select_tree: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  multi_select: ['is_empty', 'is_not_empty'],
  multi_select_tree: ['is_empty', 'is_not_empty'],
  file: ['is_empty', 'is_not_empty'],
  user_select: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  organization_select: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  employee_select: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  group_select: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
}

const OPERATOR_LABELS: Record<string, string> = {
  is_empty: '为空',
  is_not_empty: '非空',
  eq: '等于',
  ne: '不等于',
  contains: '包含',
  not_contains: '不包含',
  starts_with: '开头为',
  ends_with: '结尾为',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  between: '介于',
  in: '属于任一',
  not_in: '不属于任一',
  changed: '已变更',
  not_changed: '未变更',
}

export function TicketWorkflowPropertyPanel({
  node,
  selectedBranchId,
  fields,
  onChange,
  onClose,
}: {
  node: TicketWorkflowNode | null
  selectedBranchId?: string | null
  fields: UnifiedField[]
  onChange: (node: TicketWorkflowNode) => void
  onClose: () => void
}) {
  const [draft, setDraft] = useState<TicketWorkflowNode | null>(node)

  useEffect(() => {
    setDraft(node)
  }, [node])

  if (!draft) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button type="button" aria-label="关闭节点配置" className="absolute inset-0 bg-black/25" onClick={onClose} />
      <aside className="relative z-10 flex h-full w-[560px] flex-col bg-white shadow-2xl">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-[#e5e5e5] px-6">
          <h2 className="text-base font-semibold text-[#1a1a1a]">{nodeTitle(draft.type)}</h2>
          <button type="button" onClick={onClose} className="text-[#777] hover:text-[#1a1a1a]" aria-label="关闭">
            <IconX size={20} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {draft.type === 'trigger' && (
            <TriggerEditor
              data={draft.data}
              fields={fields}
              onChange={(data) => setDraft({ ...draft, data })}
            />
          )}
          {draft.type === 'branch' && (
            <BranchEditor
              data={draft.data}
              selectedBranchId={selectedBranchId}
              fields={fields}
              onChange={(data) => setDraft({ ...draft, data })}
            />
          )}
          {draft.type === 'update_record' && (
            <UpdateEditor
              data={draft.data}
              fields={fields}
              onChange={(data) => setDraft({ ...draft, data })}
            />
          )}
          {draft.type === 'end' && <p className="text-sm text-muted-foreground">结束节点没有可配置项。</p>}
        </div>
        <div className="flex h-16 shrink-0 items-center justify-end gap-3 border-t border-[#e5e5e5] px-6">
          <button type="button" onClick={onClose} className="h-10 rounded-md border border-[#d9d9d9] bg-white px-5 text-sm text-[#333] hover:bg-[#f7f7f7]">
            取消
          </button>
          <button
            type="button"
            onClick={() => {
              onChange(draft)
              onClose()
            }}
            className="h-10 rounded-md bg-[#1a1a1a] px-5 text-sm font-medium text-white hover:bg-black"
          >
            确定
          </button>
        </div>
      </aside>
    </div>
  )
}

const controlClass = 'h-9 rounded-md border border-[#d9d9d9] bg-white px-3 text-sm text-[#333] outline-none transition-colors hover:bg-[#fafafa] focus:border-[#1a1a1a]'

function DrawerSection({ title, children, help }: { title: string; children: React.ReactNode; help?: string }) {
  return (
    <section className="space-y-3">
      <div>
        <Label>{title}</Label>
        {help && <p className="mt-1 text-xs leading-5 text-[#8a8a8a]">{help}</p>}
      </div>
      {children}
    </section>
  )
}

function TriggerEditor({
  data,
  fields,
  onChange,
}: {
  data: TriggerData
  fields: UnifiedField[]
  onChange: (data: TriggerData) => void
}) {
  const toggleEvent = (eventType: 'create' | 'update') => {
    const next = data.event_types.includes(eventType)
      ? data.event_types.filter((item) => item !== eventType)
      : [...data.event_types, eventType]
    onChange({ ...data, event_types: next.length ? next : [eventType] })
  }
  return (
    <div className="space-y-6">
      <DrawerSection
        title="生效时机"
        help="至少选择一项；仅「创建」时不支持变更前 / 已变更类条件。"
      >
        <div className="flex gap-5">
          {(['create', 'update'] as const).map((eventType) => (
            <button
              key={eventType}
              type="button"
              onClick={() => toggleEvent(eventType)}
              className="flex items-center gap-2 text-sm text-[#333]"
            >
              <span className={`flex h-4 w-4 items-center justify-center rounded-[4px] border ${data.event_types.includes(eventType) ? 'border-[#1a1a1a] bg-[#1a1a1a]' : 'border-[#cfcfcf] bg-white'}`}>
                {data.event_types.includes(eventType) && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
              </span>
              {eventType === 'create' ? '创建' : '编辑'}
            </button>
          ))}
        </div>
      </DrawerSection>
      <ConditionList
        conditions={data.conditions}
        logic={data.condition_logic}
        fields={fields}
        onLogicChange={(condition_logic) => onChange({ ...data, condition_logic })}
        onChange={(conditions) => onChange({ ...data, conditions })}
      />
    </div>
  )
}

function BranchEditor({
  data,
  selectedBranchId,
  fields,
  onChange,
}: {
  data: BranchData
  selectedBranchId?: string | null
  fields: UnifiedField[]
  onChange: (data: BranchData) => void
}) {
  const visibleBranches = selectedBranchId
    ? data.branches.filter((branch) => branch.id === selectedBranchId)
    : data.branches
  const branches = visibleBranches.length ? visibleBranches : data.branches

  const updateBranch = (id: string, patch: Partial<BranchItem>) => {
    onChange({ ...data, branches: data.branches.map((branch) => branch.id === id ? { ...branch, ...patch } : branch) })
  }
  const removeBranch = (id: string) => {
    const branch = data.branches.find((item) => item.id === id)
    if (!branch || branch.is_default || data.branches.filter((item) => !item.is_default).length <= 1) return
    onChange({ ...data, branches: data.branches.filter((item) => item.id !== id) })
  }
  return (
    <div className="space-y-6">
      {branches.map((branch) => (
        <section key={branch.id} className="space-y-4">
          {!branch.is_default && (
            <DrawerSection title="分支名称">
              <div className="flex items-center gap-2">
                <input
                  value={branch.name}
                  disabled={branch.is_default}
                  onChange={(event) => updateBranch(branch.id, { name: event.target.value })}
                  className={`${controlClass} min-w-0 flex-1`}
                />
                <button type="button" onClick={() => removeBranch(branch.id)} className="text-[#777] hover:text-destructive" aria-label="删除分支">
                  <IconTrash size={17} />
                </button>
              </div>
            </DrawerSection>
          )}
          {!branch.is_default ? (
            <ConditionList
              conditions={branch.conditions}
              logic={branch.condition_logic}
              fields={fields}
              title="判定条件"
              help="生效时机含「编辑」时，可使用变更前、发生变更、未发生变更等值作用域。"
              onLogicChange={(condition_logic) => updateBranch(branch.id, { condition_logic })}
              onChange={(conditions) => updateBranch(branch.id, { conditions })}
            />
          ) : (
            <p className="rounded-md bg-[#fff8d7] px-3 py-2 text-xs text-[#8a6200]">默认分支在其它条件均不命中时执行。</p>
          )}
        </section>
      ))}
    </div>
  )
}

function UpdateEditor({
  data,
  fields,
  onChange,
}: {
  data: UpdateRecordData
  fields: UnifiedField[]
  onChange: (data: UpdateRecordData) => void
}) {
  const writable = fields.filter(isWritableField)
  const first = writable[0]
  const updateOperation = (index: number, patch: Partial<UpdateRecordData['operations'][number]>) => {
    onChange({ ...data, operations: data.operations.map((operation, idx) => idx === index ? { ...operation, ...patch } : operation) })
  }
  const addOperation = () => {
    onChange({
      ...data,
      operations: [...data.operations, { ...fieldRefFromUid(first ? unifiedFieldUid(first) : ''), action: 'set', value: null }],
    })
  }
  return (
    <DrawerSection title="字段变更">
      <div className="space-y-2 rounded-md border border-[#e5e5e5] p-3">
        {data.operations.map((operation, index) => {
          const selectedField = findOperationField(fields, operation)
          return (
          <div key={index} className="flex items-start gap-2">
            <FieldSelect
              fields={writable}
              value={fieldUid({ field_id: operation.target_field_id, field_key: operation.target_field_key })}
              onChange={(uid) => {
                const ref = fieldRefFromUid(uid)
                updateOperation(index, {
                  target_field_id: ref.field_id ?? null,
                  target_field_key: ref.field_key ?? null,
                  value: null,
                })
              }}
            />
            <select
              value={operation.action}
              onChange={(event) => updateOperation(index, { action: event.target.value as 'set' | 'clear' })}
              className={`${controlClass} w-[120px] shrink-0`}
            >
              <option value="set">设置值</option>
              <option value="clear">清空字段</option>
            </select>
            {operation.action === 'set' && (
              <div className="min-w-0 flex-1">
                {selectedField ? (
                  <UnifiedFieldValueEditor
                    field={selectedField}
                    value={operation.value}
                    onChange={(value) => updateOperation(index, { value })}
                    placeholder="写入值"
                  />
                ) : (
                  <input
                    disabled
                    value=""
                    placeholder="请先选择字段"
                    className={`${controlClass} w-full opacity-60`}
                  />
                )}
              </div>
            )}
            {data.operations.length > 1 && (
              <button
                type="button"
                onClick={() => onChange({ ...data, operations: data.operations.filter((_, idx) => idx !== index) })}
                className="mt-2 shrink-0 text-[#777] hover:text-destructive"
                aria-label="删除字段变更"
              >
                <IconTrash size={17} />
              </button>
            )}
          </div>
          )
        })}
      </div>
      <button type="button" onClick={addOperation} className="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-md border border-[#d9d9d9] text-sm text-[#333] hover:bg-[#f7f7f7]">
        <IconPlus size={16} />
        添加条件
      </button>
      <p className="mt-4 text-xs leading-5 text-[#8a8a8a]">目标字段须为工单可写字段；清空后持久化为空值。</p>
    </DrawerSection>
  )
}

function ConditionList({
  conditions,
  logic,
  fields,
  onLogicChange,
  onChange,
  title = '入口判定条件',
  help,
}: {
  conditions: WorkflowCondition[]
  logic: 'AND' | 'OR'
  fields: UnifiedField[]
  onLogicChange: (logic: 'AND' | 'OR') => void
  onChange: (conditions: WorkflowCondition[]) => void
  title?: string
  help?: string
}) {
  const first = fields[0]
  const update = (index: number, patch: Partial<WorkflowCondition>) => {
    onChange(conditions.map((condition, idx) => idx === index ? { ...condition, ...patch } : condition))
  }
  const add = () => {
    onChange([
      ...conditions,
      { ...fieldRefFromUid(first ? unifiedFieldUid(first) : ''), value_scope: 'current', operator: 'eq', value: '' },
    ])
  }
  return (
    <DrawerSection title={title} help={help}>
      <div className="mb-2 flex w-fit rounded-md bg-[#f2f2f2] p-0.5">
        {(['AND', 'OR'] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onLogicChange(item)}
            className={`rounded px-3 py-1.5 text-[13px] ${logic === item ? 'bg-white text-[#1a1a1a] shadow-sm' : 'text-[#8a8a8a]'}`}
          >
            {item === 'AND' ? '全部满足' : '任意满足'}
          </button>
        ))}
      </div>
      {conditions.length > 0 && (
      <div className="overflow-visible rounded-md border border-[#e5e5e5]">
      {conditions.map((condition, index) => {
        const selectedField = findField(fields, condition)
        const operators = OPERATORS_BY_TYPE[selectedField?.field_type ?? 'single_line_text'] ?? ['eq']
        const isChangeScope = CHANGE_SCOPES.has(condition.operator)
        const mode = isChangeScope ? condition.operator : (condition.value_scope ?? 'current')
        const showOperator = !isChangeScope
        const showValueEditor = !isChangeScope && !NO_VALUE_OPERATORS.has(condition.operator)
        const onModeChange = (next: string) => {
          if (CHANGE_SCOPES.has(next)) {
            update(index, { operator: next, value: null })
            return
          }
          const operator = isChangeScope ? (operators[0] ?? 'eq') : condition.operator
          update(index, { value_scope: next as 'current' | 'before', operator })
        }
        return (
          <div key={index} className="flex items-center gap-2 border-b border-[#e5e5e5] px-3 py-2 last:border-b-0">
            <FieldSelect
              fields={fields}
              value={fieldUid(condition)}
              onChange={(uid) => {
                const ref = fieldRefFromUid(uid)
                update(index, { field_id: ref.field_id ?? null, field_key: ref.field_key ?? null, operator: 'eq', value: '' })
              }}
            />
            <select
              value={mode}
              onChange={(event) => onModeChange(event.target.value)}
              className={`${controlClass} w-[104px] shrink-0`}
            >
              <option value="current">当前值</option>
              <option value="before">变更前</option>
              <option value="changed">发生变更</option>
              <option value="not_changed">未发生变更</option>
            </select>
            {showOperator && (
              <select
                value={condition.operator}
                onChange={(event) => update(index, { operator: event.target.value, value: NO_VALUE_OPERATORS.has(event.target.value) ? null : '' })}
                className={`${controlClass} w-[96px] shrink-0`}
              >
                {operators.map((operator) => (
                  <option key={operator} value={operator}>{OPERATOR_LABELS[operator] ?? operator}</option>
                ))}
              </select>
            )}
            {showValueEditor && (
              <div className="min-w-0 flex-1">
                <FilterValueEditor
                  field={selectedField}
                  operator={condition.operator}
                  value={condition.value}
                  onChange={(value) => update(index, { value })}
                  placeholder="比较值"
                />
              </div>
            )}
            <button type="button" onClick={() => onChange(conditions.filter((_, idx) => idx !== index))} className="shrink-0 text-[#777] hover:text-destructive" aria-label="删除条件">
              <IconTrash size={16} />
            </button>
          </div>
        )
      })}
      </div>
      )}
      <button type="button" onClick={add} className="mt-2 flex h-9 w-fit items-center gap-1.5 rounded-md border border-[#d9d9d9] px-3.5 text-sm text-[#333] hover:bg-[#f7f7f7]">
        <IconPlus size={16} />
        添加条件
      </button>
    </DrawerSection>
  )
}

function FieldSelect({
  fields,
  value,
  onChange,
}: {
  fields: UnifiedField[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} className={`${controlClass} min-w-0 flex-1`}>
      <option value="">选择字段</option>
      {fields.map((field) => (
        <option key={unifiedFieldUid(field)} value={unifiedFieldUid(field)}>
          {field.name}
        </option>
      ))}
    </select>
  )
}

function findOperationField(
  fields: UnifiedField[],
  operation: Pick<UpdateRecordData['operations'][number], 'target_field_id' | 'target_field_key'>,
): UnifiedField | undefined {
  return fields.find((field) => {
    if (operation.target_field_id) return field.id === operation.target_field_id
    if (operation.target_field_key) return field.key === operation.target_field_key
    return false
  })
}

function findField(fields: UnifiedField[], condition: WorkflowCondition): UnifiedField | undefined {
  return fields.find((field) => {
    if (condition.field_id) return field.id === condition.field_id
    if (condition.field_key) return field.key === condition.field_key
    return false
  })
}

function isWritableField(field: UnifiedField): boolean {
  if (field.source === 'metadata') return false
  if ((field.type_config as { readonly?: boolean }).readonly) return false
  if (field.source === 'custom') return field.id != null
  if (field.key) return WRITABLE_SYSTEM_KEYS.has(field.key)
  return false
}

function unifiedFieldUid(field: UnifiedField): string {
  if (field.id != null) return `id:${field.id}`
  if (field.key) return `key:${field.key}`
  return ''
}

function nodeTitle(type: TicketWorkflowNode['type']): string {
  if (type === 'trigger') return '编辑触发节点'
  if (type === 'branch') return '编辑分支条件'
  if (type === 'update_record') return '编辑更新记录'
  return '流程结束'
}

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-sm font-semibold text-[#333]">{children}</p>
}
