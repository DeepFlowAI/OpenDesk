'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  IconArrowDown,
  IconArrowLeft,
  IconArrowUp,
  IconDeviceFloppy,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react'
import { FieldTypeConfig, type OptionItem, type TreeNodeItem } from '@/app/components/features/field-system'
import { OutboundScriptEditor } from '@/app/components/features/engagement/outbound-script-editor'
import { validateOutboundScript } from '@/app/components/features/engagement/outbound-script-utils'
import { useLocaleStore } from '@/context/locale-store'
import { findDuplicateFieldNames } from '@/lib/outbound-field-variables'
import type { OutboundScript, OutboundTaskField, OutboundTaskTemplate } from '@/models/outbound-task'
import { FIELD_TYPE_LABELS, FieldType, SELECT_FIELD_TYPES, TREE_FIELD_TYPES } from '@/types/field-enums'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

type TemplateDraft = {
  name: string
  description: string
  fields: OutboundTaskField[]
  script: OutboundScript | null
  expectedUpdatedAt: string | null
}

type OutboundTaskTemplateFormProps = {
  title: string
  submitLabel: string
  template?: OutboundTaskTemplate
  loading?: boolean
  saving?: boolean
  onSubmit: (draft: TemplateDraft) => Promise<boolean>
}

const supportedFieldTypes: FieldType[] = [
  FieldType.SINGLE_LINE_TEXT,
  FieldType.MULTI_LINE_TEXT,
  FieldType.NUMBER,
  FieldType.DATE,
  FieldType.TIME,
  FieldType.DATETIME,
  FieldType.SINGLE_SELECT,
  FieldType.MULTI_SELECT,
  FieldType.SINGLE_SELECT_TREE,
  FieldType.MULTI_SELECT_TREE,
  FieldType.EMAIL,
  FieldType.PHONE,
  FieldType.URL,
  FieldType.FILE,
  FieldType.RICH_TEXT,
]

function newFieldKey(fields: OutboundTaskField[]): string {
  const keys = new Set(fields.map((field) => field.key))
  let index = fields.length + 1
  while (keys.has(`field_${index}`)) index += 1
  return `field_${index}`
}

function createField(fields: OutboundTaskField[]): OutboundTaskField {
  return {
    key: newFieldKey(fields),
    name: '',
    field_type: FieldType.SINGLE_LINE_TEXT,
    required: false,
    agent_editable: false,
    show_in_list: true,
    enabled: true,
    type_config: {},
    sort_order: fields.length,
  }
}

function normalizeFields(fields: OutboundTaskField[]): OutboundTaskField[] {
  return fields.map((field, index) => ({ ...field, sort_order: index }))
}

function optionItems(field: OutboundTaskField): OptionItem[] {
  const raw = field.type_config.options
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is OptionItem => {
    if (!item || typeof item !== 'object') return false
    const option = item as Partial<OptionItem>
    return typeof option.label === 'string' && typeof option.value === 'string'
  })
}

function treeNodes(field: OutboundTaskField): TreeNodeItem[] {
  const raw = field.type_config.tree_nodes
  return Array.isArray(raw) ? (raw as TreeNodeItem[]) : []
}

export function OutboundTaskTemplateForm({
  title,
  submitLabel,
  template,
  loading,
  saving,
  onSubmit,
}: OutboundTaskTemplateFormProps) {
  const initialDraft = useMemo<TemplateDraft>(
    () => ({
      name: template?.name ?? '',
      description: template?.description ?? '',
      fields: normalizeFields(template?.fields ?? []),
      script: template?.script ?? null,
      expectedUpdatedAt: template?.updated_at ?? null,
    }),
    [template],
  )
  const [draft, setDraft] = useState(initialDraft)
  const [savedDraft, setSavedDraft] = useState(initialDraft)
  const [activeTab, setActiveTab] = useState<'basic' | 'fields' | 'script'>('basic')
  const [editingKey, setEditingKey] = useState<string | null>(initialDraft.fields[0]?.key ?? null)
  const dirty = JSON.stringify(draft) !== JSON.stringify(savedDraft)
  const { locale } = useLocaleStore()
  const duplicateNames = useMemo(() => findDuplicateFieldNames(draft.fields), [draft.fields])

  useEffect(() => {
    if (dirty) return
    setDraft(initialDraft)
    setSavedDraft(initialDraft)
    setEditingKey(initialDraft.fields[0]?.key ?? null)
  }, [dirty, initialDraft])

  useEffect(() => {
    const tab = new URLSearchParams(window.location.search).get('tab')
    if (tab === 'fields' || tab === 'script') setActiveTab(tab)
  }, [])

  useEffect(() => {
    if (!dirty) return
    const beforeUnload = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  const switchTab = (tab: 'basic' | 'fields' | 'script') => {
    setActiveTab(tab)
    const url = new URL(window.location.href)
    url.searchParams.set('tab', tab)
    window.history.replaceState(window.history.state, '', url)
  }

  const submit = async () => {
    const firstDuplicate = draft.fields.find((field) => duplicateNames.has(field.key))
    if (firstDuplicate) {
      switchTab('fields')
      setEditingKey(firstDuplicate.key)
      toast.error(t('ws.outboundTemplate.field.nameDuplicate', locale, { name: duplicateNames.get(firstDuplicate.key) ?? '' }))
      return
    }
    if (draft.script) {
      const issues = validateOutboundScript(draft.script)
      if (issues.length > 0) {
        switchTab('script')
        toast.error(issues[0].message)
        return
      }
    }
    const normalized = { ...draft, fields: normalizeFields(draft.fields) }
    if (await onSubmit(normalized)) setSavedDraft(normalized)
  }

  const setField = (key: string, updater: (field: OutboundTaskField) => OutboundTaskField) => {
    setDraft((current) => ({
      ...current,
      fields: normalizeFields(current.fields.map((field) => (field.key === key ? updater(field) : field))),
    }))
  }

  const addField = () => {
    setDraft((current) => {
      const field = createField(current.fields)
      setEditingKey(field.key)
      return { ...current, fields: [...current.fields, field] }
    })
  }

  const removeField = (key: string) => {
    setDraft((current) => ({
      ...current,
      fields: normalizeFields(current.fields.filter((field) => field.key !== key)),
    }))
    if (editingKey === key) setEditingKey(null)
  }

  const moveField = (key: string, direction: -1 | 1) => {
    setDraft((current) => {
      const index = current.fields.findIndex((field) => field.key === key)
      const target = index + direction
      if (index < 0 || target < 0 || target >= current.fields.length) return current
      const fields = [...current.fields]
      const [field] = fields.splice(index, 1)
      fields.splice(target, 0, field)
      return { ...current, fields: normalizeFields(fields) }
    })
  }

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">加载中...</div>
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Link href="/workspace/engagement/outbound-task-templates" onClick={(event) => { if (dirty && !window.confirm('当前任务模板有未保存的修改，确定放弃并离开？')) event.preventDefault() }} className="rounded-md p-2 hover:bg-muted">
            <IconArrowLeft size={18} />
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-foreground">{title}</h1>
            <p className="mt-1 text-sm text-muted-foreground">维护模板基础信息和创建任务时复制的字段结构</p>
          </div>
          {dirty && <span className="rounded-full bg-warning/10 px-2 py-1 text-xs font-medium text-warning">未保存</span>}
        </div>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!dirty || saving}
          className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          <IconDeviceFloppy size={16} />
          {submitLabel}
        </button>
      </header>

      <nav className="flex h-12 shrink-0 items-end gap-5 border-b border-border px-6" aria-label="模板配置">
        {([['basic', '基本信息'], ['fields', '任务字段'], ['script', '外呼话术']] as const).map(([tab, label]) => (
          <button key={tab} type="button" onClick={() => switchTab(tab)} className={cn('h-12 border-b-2 px-1 text-sm', activeTab === tab ? 'border-foreground font-medium text-foreground' : 'border-transparent text-muted-foreground')}>{label}</button>
        ))}
      </nav>

      <main className={cn('min-h-0 flex-1', activeTab === 'script' ? 'overflow-hidden' : 'overflow-auto p-6')}>
        {activeTab === 'script' ? (
          <OutboundScriptEditor value={draft.script} templateName={draft.name} existingTemplate={Boolean(template)} onChange={(script) => setDraft((current) => ({ ...current, script }))} />
        ) : (
        <div className="mx-auto max-w-5xl space-y-6">
          {activeTab === 'basic' && <section>
            <h2 className="mb-4 text-base font-semibold">基础信息</h2>
            <div className="grid gap-4">
              <label className="grid gap-1.5 text-sm">
                <span className="font-medium">模板名称</span>
                <input
                  value={draft.name}
                  onChange={(e) => setDraft((current) => ({ ...current, name: e.target.value }))}
                  className="h-10 rounded-md border border-border bg-background px-3 outline-none"
                />
              </label>
              <label className="grid gap-1.5 text-sm">
                <span className="font-medium">模板说明</span>
                <textarea
                  value={draft.description}
                  onChange={(e) => setDraft((current) => ({ ...current, description: e.target.value }))}
                  rows={3}
                  className="rounded-md border border-border bg-background px-3 py-2 outline-none"
                />
              </label>
            </div>
          </section>}

          {activeTab === 'fields' && <section>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold">字段结构</h2>
                <p className="mt-1 text-sm text-muted-foreground">固定字段无需配置，这里只维护外呼对象业务字段。</p>
              </div>
              <button
                type="button"
                onClick={addField}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-sm"
              >
                <IconPlus size={16} />
                添加字段
              </button>
            </div>

            {draft.fields.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
                暂无模板字段
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                {draft.fields.map((field, index) => {
                  const editing = editingKey === field.key
                  const duplicateOf = duplicateNames.get(field.key)
                  const duplicateMessage = duplicateOf === undefined
                    ? null
                    : t('ws.outboundTemplate.field.nameDuplicate', locale, { name: duplicateOf })
                  return (
                    <div key={field.key} className="border-t border-border first:border-t-0">
                      <div className="flex items-center justify-between gap-3 px-4 py-3">
                        <button
                          type="button"
                          onClick={() => setEditingKey(editing ? null : field.key)}
                          className="min-w-0 flex-1 text-left"
                        >
                          <span className={cn('font-medium', !field.name.trim() && 'text-muted-foreground')}>
                            {field.name.trim() || '未命名字段'}
                          </span>
                          <span className="ml-3 text-sm text-muted-foreground">
                            {FIELD_TYPE_LABELS[field.field_type]?.zh ?? field.field_type}
                            {field.agent_editable ? ' · 客服可编辑' : ''}
                            {!field.enabled ? ' · 已停用' : ''}
                          </span>
                          {duplicateMessage && (
                            <span className="ml-3 text-sm text-destructive">{duplicateMessage}</span>
                          )}
                        </button>
                        <div className="flex shrink-0 items-center gap-1">
                          <IconButton title="上移" disabled={index === 0} onClick={() => moveField(field.key, -1)}>
                            <IconArrowUp size={16} />
                          </IconButton>
                          <IconButton title="下移" disabled={index === draft.fields.length - 1} onClick={() => moveField(field.key, 1)}>
                            <IconArrowDown size={16} />
                          </IconButton>
                          <IconButton title="删除" onClick={() => removeField(field.key)}>
                            <IconTrash size={16} />
                          </IconButton>
                        </div>
                      </div>
                      {editing && (
                        <FieldEditor
                          field={field}
                          nameHint={t('ws.outboundTemplate.field.nameVariableHint', locale)}
                          nameError={duplicateMessage}
                          onChange={(next) => setField(field.key, () => next)}
                        />
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>}
        </div>
        )}
      </main>
    </div>
  )
}

function FieldEditor({
  field,
  nameHint,
  nameError,
  onChange,
}: {
  field: OutboundTaskField
  nameHint: string
  nameError: string | null
  onChange: (field: OutboundTaskField) => void
}) {
  const update = <K extends keyof OutboundTaskField>(key: K, value: OutboundTaskField[K]) => {
    onChange({ ...field, [key]: value })
  }
  const isSelect = (SELECT_FIELD_TYPES as readonly string[]).includes(field.field_type)
  const isTree = (TREE_FIELD_TYPES as readonly string[]).includes(field.field_type)

  return (
    <div className="border-t border-border bg-muted/20 px-4 py-4">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="grid gap-1.5 text-sm">
          <span className="font-medium">字段名称</span>
          <input
            value={field.name}
            onChange={(e) => update('name', e.target.value)}
            aria-invalid={nameError ? true : undefined}
            className={cn(
              'h-10 rounded-md border bg-background px-3 outline-none',
              nameError ? 'border-destructive' : 'border-border',
            )}
          />
          {nameError && <span className="text-xs text-destructive">{nameError}</span>}
          <span className="text-xs text-muted-foreground">{nameHint}</span>
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="font-medium">字段类型</span>
          <select
            value={field.field_type}
            onChange={(e) => onChange({ ...field, field_type: e.target.value as FieldType, type_config: {} })}
            className="h-10 rounded-md border border-border bg-background px-3"
          >
            {supportedFieldTypes.map((type) => (
              <option key={type} value={type}>{FIELD_TYPE_LABELS[type].zh}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-4">
        <Toggle label="必填" checked={field.required} onChange={(checked) => update('required', checked)} />
        <Toggle label="允许客服编辑" checked={field.agent_editable} onChange={(checked) => update('agent_editable', checked)} />
        <Toggle label="列表展示" checked={field.show_in_list} onChange={(checked) => update('show_in_list', checked)} />
        <Toggle label="启用" checked={field.enabled} onChange={(checked) => update('enabled', checked)} />
      </div>

      <FieldTypeConfig
        fieldType={field.field_type}
        config={field.type_config}
        onConfigChange={(config) => update('type_config', config)}
        options={isSelect ? optionItems(field) : undefined}
        onOptionsChange={isSelect ? (options) => update('type_config', { ...field.type_config, options }) : undefined}
        treeNodes={isTree ? treeNodes(field) : undefined}
        onTreeNodesChange={isTree ? (nodes) => update('type_config', { ...field.type_config, tree_nodes: nodes }) : undefined}
        className="mt-4"
      />
    </div>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-border"
      />
      {label}
    </label>
  )
}

function IconButton({
  title,
  disabled,
  onClick,
  children,
}: {
  title: string
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
    >
      {children}
    </button>
  )
}
