'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { useCreateUser, useUpdateUser } from '@/service/use-users'
import { useOrganization, useQueryOrganizations } from '@/service/use-organizations'
import { useSystemSettings } from '@/service/use-system-settings'
import { useUnifiedFields } from '@/service/use-field-definitions'
import type { User, CreateUserPayload, UpdateUserPayload, CustomFieldValue } from '@/models/user'
import type { Organization } from '@/models/organization'
import type { UnifiedField } from '@/models/field-definition'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { cn } from '@/lib/utils'
import { getLinkedSelectTypeConfig } from '@/lib/field-linked-select-config'
import { defaultCfValuesFromFieldDefinitions } from '@/lib/ticket-field-defaults'
import { IconChevronDown, IconSearch, IconX } from '@tabler/icons-react'

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

type UserFormModalProps = {
  mode: 'create' | 'edit'
  user?: User | null
  onClose: () => void
  onSuccess: () => void
}

type SystemFormData = {
  name: string
  phone: string
  email: string
  gender: string
  level: string
  address: string
  remark: string
  blacklist: string
  organization_id: number | null
  agent_id: number | null
  assignee_group_id: number | null
}

type SystemTextFieldKey = Exclude<keyof SystemFormData, 'organization_id' | 'agent_id' | 'assignee_group_id'>

const GENDER_OPTIONS = [
  { value: '', zh: '请选择', en: 'Select' },
  { value: 'male', zh: '男', en: 'Male' },
  { value: 'female', zh: '女', en: 'Female' },
  { value: 'other', zh: '其他', en: 'Other' },
]

const LEVEL_OPTIONS = [
  { value: 'normal', zh: '普通', en: 'Normal' },
  { value: 'vip', zh: 'VIP', en: 'VIP' },
]

const BLACKLIST_OPTIONS = [
  { value: '', zh: '未拉黑', en: 'Not blocked' },
  { value: 'blocked', zh: '已拉黑', en: 'Blocked' },
]

function customFieldKey(field: UnifiedField): string {
  return field.key ?? (field.id != null ? String(field.id) : '')
}

function toNullableNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
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

export function UserFormModal({ mode, user, onClose, onSuccess }: UserFormModalProps) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const isEdit = mode === 'edit'

  const createMutation = useCreateUser()
  const updateMutation = useUpdateUser()
  const isPending = createMutation.isPending || updateMutation.isPending

  const { data: systemSettings } = useSystemSettings()
  const organizationEnabled = systemSettings?.organization_enabled === true
  const { data: fieldsData } = useUnifiedFields({ domain: 'user' })

  const systemFields = useMemo<UnifiedField[]>(
    () => (fieldsData?.items ?? []).filter((f) => f.source === 'system' && f.status === 'active'),
    [fieldsData],
  )
  const customFields = useMemo<UnifiedField[]>(
    () => (fieldsData?.items ?? []).filter((f) => f.source === 'custom' && f.status === 'active'),
    [fieldsData],
  )
  const assigneeGroupField = useMemo(
    () => systemFields.find((f) => f.key === 'assignee_group') ?? null,
    [systemFields],
  )
  const assigneeField = useMemo(
    () => systemFields.find((f) => f.key === 'assignee') ?? null,
    [systemFields],
  )

  const [form, setForm] = useState<SystemFormData>({
    name: '',
    phone: '',
    email: '',
    gender: '',
    level: 'normal',
    address: '',
    remark: '',
    blacklist: '',
    organization_id: null,
    agent_id: null,
    assignee_group_id: null,
  })
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({})
  const [cfValues, setCfValues] = useState<Record<string, CustomFieldValue>>({})

  useEffect(() => {
    if (isEdit) return
    setCfValues((prev) => {
      const defaults = defaultCfValuesFromFieldDefinitions(customFields)
      let changed = false
      const next = { ...prev }
      for (const [k, v] of Object.entries(defaults)) {
        const cur = next[k]
        if (cur !== undefined && cur !== null && cur !== '') continue
        next[k] = v
        changed = true
      }
      return changed ? next : prev
    })
  }, [isEdit, customFields])

  useEffect(() => {
    if (isEdit && user) {
      setForm({
        name: user.name ?? '',
        phone: user.phone ?? '',
        email: user.email ?? '',
        gender: user.gender ?? '',
        level: user.level ?? 'normal',
        address: user.address ?? '',
        remark: user.remark ?? '',
        blacklist: user.blacklist ?? '',
        organization_id: user.organization_id ?? null,
        agent_id: user.agent_id ?? null,
        assignee_group_id: user.assignee_group_id ?? null,
      })
      if (user.custom_fields) {
        setCfValues({ ...user.custom_fields })
      }
    }
  }, [isEdit, user])

  const setField = useCallback((key: SystemTextFieldKey, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }, [])

  const setOrganization = useCallback((organizationId: number | null) => {
    setForm((prev) => ({ ...prev, organization_id: organizationId }))
  }, [])

  const setAssigneeGroup = useCallback((groupId: number | null) => {
    setForm((prev) => ({ ...prev, assignee_group_id: groupId }))
  }, [])

  const setAssignee = useCallback((agentId: number | null) => {
    setForm((prev) => ({ ...prev, agent_id: agentId }))
  }, [])

  const resolveSystemFieldValue = useCallback(
    (field: UnifiedField) => {
      if (field.key === 'assignee') return form.agent_id
      if (field.key === 'assignee_group') return form.assignee_group_id
      return null
    },
    [form.agent_id, form.assignee_group_id],
  )

  const setCfField = useCallback((fieldId: string, value: CustomFieldValue) => {
    setCfValues((prev) => ({ ...prev, [fieldId]: value }))
  }, [])

  const validate = useCallback((): boolean => {
    const errs: Record<string, string> = {}
    if (!form.name.trim()) {
      errs.name = isZh ? '请输入昵称' : 'Nickname is required'
    }
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      errs.email = isZh ? '邮箱格式不正确' : 'Invalid email format'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }, [form, isZh])

  const buildCustomFieldsPayload = useCallback((): Record<string, CustomFieldValue> => {
    const cf: Record<string, CustomFieldValue> = {}
    for (const [key, val] of Object.entries(cfValues)) {
      if (Array.isArray(val) && val.length === 0) continue
      if (val !== null && val !== undefined && val !== '') {
        cf[key] = val
      }
    }
    return cf
  }, [cfValues])

  const handleSubmit = useCallback(async () => {
    if (!validate()) return
    try {
      const cfPayload = buildCustomFieldsPayload()
      if (isEdit && user) {
        const payload: UpdateUserPayload = {}
        if (form.name !== (user.name ?? '')) payload.name = form.name
        if (form.phone !== (user.phone ?? '')) payload.phone = form.phone || null
        if (form.email !== (user.email ?? '')) payload.email = form.email || null
        if (form.gender !== (user.gender ?? '')) payload.gender = form.gender || null
        if (form.level !== (user.level ?? 'normal')) payload.level = form.level || 'normal'
        if (form.address !== (user.address ?? '')) payload.address = form.address || null
        if (form.remark !== (user.remark ?? '')) payload.remark = form.remark || null
        if (form.blacklist !== (user.blacklist ?? '')) payload.blacklist = form.blacklist || null
        if (form.organization_id !== (user.organization_id ?? null)) {
          payload.organization_id = form.organization_id
        }
        if (form.assignee_group_id !== (user.assignee_group_id ?? null)) {
          payload.assignee_group_id = form.assignee_group_id
        }
        if (form.agent_id !== (user.agent_id ?? null)) {
          payload.agent_id = form.agent_id
        }

        const origCf = user.custom_fields ?? {}
        const changedCf: Record<string, CustomFieldValue> = {}
        for (const field of customFields) {
          const key = customFieldKey(field)
          const legacyKey = field.id != null ? String(field.id) : null
          const newVal = cfValues[key] ?? null
          const oldVal = origCf[key] ?? (legacyKey ? origCf[legacyKey] : null) ?? null
          if (newVal !== oldVal) changedCf[key] = newVal
        }
        if (Object.keys(changedCf).length > 0) payload.custom_fields = changedCf

        await updateMutation.mutateAsync({ id: user.id, data: payload })
      } else {
        const payload: CreateUserPayload = {
          name: form.name.trim(),
          ...(form.phone ? { phone: form.phone } : {}),
          ...(form.email ? { email: form.email } : {}),
          ...(form.gender ? { gender: form.gender } : {}),
          level: form.level || 'normal',
          ...(form.address ? { address: form.address } : {}),
          ...(form.remark ? { remark: form.remark } : {}),
          ...(form.blacklist ? { blacklist: form.blacklist } : {}),
          ...(form.organization_id != null ? { organization_id: form.organization_id } : {}),
          ...(form.assignee_group_id != null ? { assignee_group_id: form.assignee_group_id } : {}),
          ...(form.agent_id != null ? { agent_id: form.agent_id } : {}),
          ...(Object.keys(cfPayload).length > 0 ? { custom_fields: cfPayload } : {}),
        }
        await createMutation.mutateAsync(payload)
      }
      onSuccess()
    } catch {
      // error handled by mutation
    }
  }, [form, isEdit, user, validate, createMutation, updateMutation, onSuccess, buildCustomFieldsPayload, cfValues, customFields])

  const handleOpenChange = useCallback((open: boolean) => {
    if (!open) {
      onClose()
    }
  }, [onClose])

  return (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        className="sm:max-w-[520px] max-h-[85vh] flex flex-col gap-0 p-0"
      >
        <DialogHeader className="px-6 py-4 border-b">
          <DialogTitle>
            {isEdit
              ? (isZh ? '编辑用户' : 'Edit User')
              : (isZh ? '新建用户' : 'Create User')}
          </DialogTitle>
        </DialogHeader>

        {isEdit && user && (
          <div className="px-6 pt-3">
            <p className="truncate text-xs text-muted-foreground">
              {isZh ? '终端用户 ID' : 'User ID'}:{' '}
              <span className="font-mono">{user.public_id || '—'}</span>
            </p>
          </div>
        )}

        {/* Form body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <h3 className="mb-4 text-sm font-semibold">
            {isZh ? '基本信息' : 'Basic Info'}
          </h3>

          <div className="flex flex-col gap-4">
            <FieldRow label={isZh ? '昵称' : 'Nickname'} required error={errors.name}>
              <Input
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
                placeholder={isZh ? '请输入昵称' : 'Enter nickname'}
              />
            </FieldRow>

            <FieldRow label={isZh ? '手机' : 'Phone'} error={errors.phone}>
              <Input
                value={form.phone}
                onChange={(e) => setField('phone', e.target.value)}
                placeholder={isZh ? '请输入手机号' : 'Enter phone number'}
              />
            </FieldRow>

            <FieldRow label={isZh ? '邮箱' : 'Email'} error={errors.email}>
              <Input
                type="email"
                value={form.email}
                onChange={(e) => setField('email', e.target.value)}
                placeholder={isZh ? '请输入邮箱' : 'Enter email'}
              />
            </FieldRow>

            <FieldRow label={isZh ? '性别' : 'Gender'}>
              <select
                value={form.gender}
                onChange={(e) => setField('gender', e.target.value)}
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {GENDER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {isZh ? opt.zh : opt.en}
                  </option>
                ))}
              </select>
            </FieldRow>

            <FieldRow label={isZh ? '等级' : 'Level'}>
              <select
                value={form.level}
                onChange={(e) => setField('level', e.target.value)}
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {LEVEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {isZh ? opt.zh : opt.en}
                  </option>
                ))}
              </select>
            </FieldRow>

            <FieldRow label={isZh ? '地址' : 'Address'}>
              <Input
                value={form.address}
                onChange={(e) => setField('address', e.target.value)}
                placeholder={isZh ? '请输入地址' : 'Enter address'}
              />
            </FieldRow>

            <FieldRow label={isZh ? '备注' : 'Remark'}>
              <Textarea
                value={form.remark}
                onChange={(e) => setField('remark', e.target.value)}
                placeholder={isZh ? '请输入备注' : 'Enter remark'}
                rows={3}
              />
            </FieldRow>

            <FieldRow label={isZh ? '黑名单' : 'Blacklist'}>
              <select
                value={form.blacklist}
                onChange={(e) => setField('blacklist', e.target.value)}
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {BLACKLIST_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {isZh ? opt.zh : opt.en}
                  </option>
                ))}
              </select>
            </FieldRow>

            {organizationEnabled && (
              <FieldRow label={isZh ? '组织' : 'Organization'}>
                <OrganizationSelect
                  value={form.organization_id}
                  onChange={setOrganization}
                  isZh={isZh}
                />
              </FieldRow>
            )}

            {assigneeGroupField && (
              <FieldRow label={isZh ? '负责组' : 'Assignee Group'} helpText={assigneeGroupField.help_text}>
                <UnifiedFieldValueEditor
                  field={assigneeGroupField}
                  value={form.assignee_group_id}
                  typeConfig={getLinkedSelectTypeConfig(assigneeGroupField, systemFields, resolveSystemFieldValue)}
                  onChange={(value) => setAssigneeGroup(toNullableNumber(value))}
                  placeholder={isZh ? '搜索负责组…' : 'Search groups...'}
                  dropdownPlacement="top"
                />
              </FieldRow>
            )}

            {assigneeField && (
              <FieldRow label={isZh ? '负责人' : 'Assignee'} helpText={assigneeField.help_text}>
                <UnifiedFieldValueEditor
                  field={assigneeField}
                  value={form.agent_id}
                  typeConfig={getLinkedSelectTypeConfig(assigneeField, systemFields, resolveSystemFieldValue)}
                  onChange={(value) => setAssignee(toNullableNumber(value))}
                  placeholder={isZh ? '搜索员工…' : 'Search employees...'}
                  dropdownPlacement="top"
                />
              </FieldRow>
            )}
          </div>

          {/* Custom fields */}
          {customFields.length > 0 && (
            <>
              <h3 className="mb-4 mt-6 text-sm font-semibold">
                {isZh ? '自定义字段' : 'Custom Fields'}
              </h3>
              <div className="flex flex-col gap-4">
                {customFields.map((field) => {
                  const key = customFieldKey(field)
                  const resolveFieldValue = (targetField: UnifiedField) => cfValues[customFieldKey(targetField)] ?? null
                  return (
                    <CustomFieldInput
                      key={field.id ?? key}
                      field={field}
                      value={cfValues[key] ?? null}
                      typeConfig={getLinkedSelectTypeConfig(field, customFields, resolveFieldValue)}
                      onChange={(v) => setCfField(key, v)}
                      isZh={isZh}
                    />
                  )
                })}
              </div>
            </>
          )}
        </div>

        <DialogFooter className="px-6 py-4">
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            {isZh ? '取消' : 'Cancel'}
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending
              ? (isZh ? '提交中...' : 'Submitting...')
              : isEdit
                ? (isZh ? '保存' : 'Save')
                : (isZh ? '创建' : 'Create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function OrganizationSelect({
  value,
  onChange,
  isZh,
}: {
  value: number | null
  onChange: (value: number | null) => void
  isZh: boolean
}) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<'top' | 'bottom'>('bottom')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)

  const { data: selectedOrganization } = useOrganization(value ?? 0)
  const { data: organizationsData, isLoading } = useQueryOrganizations({
    search: debouncedSearch || undefined,
    page: 1,
    per_page: 20,
  })

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
    const updatePlacement = () => setPlacement(getDropdownPlacement(rootRef.current))
    updatePlacement()
    window.addEventListener('resize', updatePlacement)
    window.addEventListener('scroll', updatePlacement, true)
    return () => {
      window.removeEventListener('resize', updatePlacement)
      window.removeEventListener('scroll', updatePlacement, true)
    }
  }, [open])

  const options = useMemo<Organization[]>(() => {
    const items = organizationsData?.items ?? []
    if (!selectedOrganization || items.some((item) => item.id === selectedOrganization.id)) {
      return items
    }
    return [selectedOrganization, ...items]
  }, [organizationsData, selectedOrganization])

  const placeholder = isZh ? '搜索组织名称或描述…' : 'Search by name or description…'
  const emptyText = isZh ? '未找到组织' : 'No organizations found'
  const selectedName = selectedOrganization?.name

  const pick = useCallback(
    (organizationId: number | null) => {
      onChange(organizationId)
      setOpen(false)
      setSearch('')
    },
    [onChange],
  )

  return (
    <div ref={rootRef} className="relative w-full">
      <div
        className={cn(
          'flex min-h-8 w-full items-center gap-1.5 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-[box-shadow]',
          open && 'ring-1 ring-ring',
        )}
      >
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center text-left"
          onClick={() => {
            if (!open) setPlacement(getDropdownPlacement(rootRef.current))
            setOpen((prev) => !prev)
          }}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          {selectedName ? (
            <span className="truncate text-foreground">{selectedName}</span>
          ) : (
            <span className="truncate text-muted-foreground">{placeholder}</span>
          )}
        </button>
        {value != null && (
          <button
            type="button"
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={(event) => {
              event.stopPropagation()
              pick(null)
            }}
            aria-label={isZh ? '清空组织' : 'Clear organization'}
          >
            <IconX size={14} stroke={1.5} />
          </button>
        )}
        <button
          type="button"
          className="flex h-6 w-6 shrink-0 items-center justify-center text-muted-foreground"
          onClick={() => {
            if (!open) setPlacement(getDropdownPlacement(rootRef.current))
            setOpen((prev) => !prev)
          }}
          aria-label={isZh ? '展开组织列表' : 'Open organization list'}
        >
          <IconChevronDown size={16} stroke={1.5} />
        </button>
      </div>

      {open && (
        <div
          className={cn(
            'absolute left-0 right-0 z-50 rounded-lg border border-border bg-popover p-1.5 text-popover-foreground shadow-md ring-1 ring-foreground/10',
            placement === 'top' ? 'bottom-full mb-1' : 'top-full mt-1',
          )}
        >
          <div className="flex h-8 items-center gap-1.5 rounded-md border border-input px-2">
            <IconSearch size={14} stroke={1.5} className="shrink-0 text-muted-foreground" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={placeholder}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              autoFocus
            />
          </div>

          <ul role="listbox" className="mt-1 max-h-60 overflow-y-auto py-1">
            <li>
              <button
                type="button"
                role="option"
                aria-selected={value == null}
                className="w-full rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-muted/80"
                onClick={() => pick(null)}
              >
                {isZh ? '无组织' : 'No organization'}
              </button>
            </li>
            {isLoading ? (
              <li className="px-2 py-3 text-center text-xs text-muted-foreground">
                {isZh ? '加载中...' : 'Loading...'}
              </li>
            ) : options.length === 0 ? (
              <li className="px-2 py-3 text-center text-xs text-muted-foreground">{emptyText}</li>
            ) : (
              options.map((organization) => (
                <li key={organization.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={value === organization.id}
                    className={cn(
                      'flex w-full flex-col rounded-md px-2 py-1.5 text-left transition-colors',
                      value === organization.id ? 'bg-primary/10' : 'hover:bg-muted/80',
                    )}
                    onClick={() => pick(organization.id)}
                  >
                    <span className="truncate text-sm text-foreground">{organization.name}</span>
                    {organization.description && (
                      <span className="truncate text-xs text-muted-foreground">
                        {organization.description}
                      </span>
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

// ── Custom field renderer ──

function CustomFieldInput({
  field,
  value,
  typeConfig,
  onChange,
  isZh,
}: {
  field: UnifiedField
  value: CustomFieldValue
  typeConfig: Record<string, unknown>
  onChange: (v: CustomFieldValue) => void
  isZh: boolean
}) {
  const placeholder = isZh ? `请输入${field.name}` : `Enter ${field.name}`

  return (
    <FieldRow label={field.name} helpText={field.help_text}>
      <UnifiedFieldValueEditor
        field={field}
        value={value}
        typeConfig={typeConfig}
        onChange={(v) => onChange(v as CustomFieldValue)}
        placeholder={placeholder}
        dropdownPlacement="top"
      />
    </FieldRow>
  )
}

function FieldRow({
  label,
  required,
  error,
  helpText,
  children,
}: {
  label: string
  required?: boolean
  error?: string
  helpText?: string | null
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-muted-foreground">
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      {children}
      {helpText && <p className="text-xs text-muted-foreground">{helpText}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
