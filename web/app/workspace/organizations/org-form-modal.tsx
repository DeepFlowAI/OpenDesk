'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { useCreateOrganization, useUpdateOrganization } from '@/service/use-organizations'
import { useUnifiedFields } from '@/service/use-field-definitions'
import type {
  Organization,
  CreateOrganizationPayload,
  UpdateOrganizationPayload,
  CustomFieldValue,
} from '@/models/organization'
import type { UnifiedField } from '@/models/field-definition'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { defaultCfValuesFromFieldDefinitions } from '@/lib/ticket-field-defaults'

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

type OrgFormModalProps = {
  mode: 'create' | 'edit'
  organization?: Organization | null
  onClose: () => void
  onSuccess: () => void
}

type SystemFormData = {
  name: string
  description: string
}

function customFieldKey(field: UnifiedField): string {
  return field.key ?? (field.id != null ? String(field.id) : '')
}

export function OrgFormModal({ mode, organization, onClose, onSuccess }: OrgFormModalProps) {
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const isEdit = mode === 'edit'

  const createMutation = useCreateOrganization()
  const updateMutation = useUpdateOrganization()
  const isPending = createMutation.isPending || updateMutation.isPending

  const { data: fieldsData } = useUnifiedFields({ domain: 'organization' })

  const customFields = useMemo<UnifiedField[]>(
    () => (fieldsData?.items ?? []).filter((f) => f.source === 'custom' && f.status === 'active'),
    [fieldsData],
  )

  const [form, setForm] = useState<SystemFormData>({ name: '', description: '' })
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
    if (isEdit && organization) {
      setForm({
        name: organization.name ?? '',
        description: organization.description ?? '',
      })
      if (organization.custom_fields) {
        setCfValues({ ...organization.custom_fields })
      }
    }
  }, [isEdit, organization])

  const setField = useCallback((key: keyof SystemFormData, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => {
      if (!prev[key]) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }, [])

  const setCfField = useCallback((fieldId: string, value: CustomFieldValue) => {
    setCfValues((prev) => ({ ...prev, [fieldId]: value }))
  }, [])

  const validate = useCallback((): boolean => {
    const errs: Record<string, string> = {}
    if (!form.name.trim()) {
      errs.name = isZh ? '请输入组织名称' : 'Organization name is required'
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }, [form, isZh])

  const buildCfPayload = useCallback((): Record<string, CustomFieldValue> => {
    const cf: Record<string, CustomFieldValue> = {}
    for (const [key, val] of Object.entries(cfValues)) {
      if (Array.isArray(val) && val.length === 0) continue
      if (val !== null && val !== undefined && val !== '') cf[key] = val
    }
    return cf
  }, [cfValues])

  const handleSubmit = useCallback(async () => {
    if (!validate()) return
    try {
      const cfPayload = buildCfPayload()
      if (isEdit && organization) {
        const payload: UpdateOrganizationPayload = {}
        if (form.name !== (organization.name ?? '')) payload.name = form.name
        if (form.description !== (organization.description ?? ''))
          payload.description = form.description || null

        const origCf = organization.custom_fields ?? {}
        const changedCf: Record<string, CustomFieldValue> = {}
        for (const field of customFields) {
          const key = customFieldKey(field)
          const legacyKey = field.id != null ? String(field.id) : null
          const newVal = cfValues[key] ?? null
          const oldVal = origCf[key] ?? (legacyKey ? origCf[legacyKey] : null) ?? null
          if (newVal !== oldVal) changedCf[key] = newVal
        }
        if (Object.keys(changedCf).length > 0) payload.custom_fields = changedCf

        await updateMutation.mutateAsync({ id: organization.id, data: payload })
      } else {
        const payload: CreateOrganizationPayload = {
          name: form.name.trim(),
          ...(form.description ? { description: form.description } : {}),
          ...(Object.keys(cfPayload).length > 0 ? { custom_fields: cfPayload } : {}),
        }
        await createMutation.mutateAsync(payload)
      }
      onSuccess()
    } catch {
      // handled by mutation
    }
  }, [
    form,
    isEdit,
    organization,
    validate,
    createMutation,
    updateMutation,
    onSuccess,
    buildCfPayload,
    cfValues,
    customFields,
  ])

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
              ? (isZh ? '编辑组织' : 'Edit Organization')
              : (isZh ? '新建组织' : 'Create Organization')}
          </DialogTitle>
        </DialogHeader>

        {isEdit && organization && (
          <div className="px-6 pt-3">
            <p className="text-xs text-muted-foreground">
              {isZh ? '组织 ID' : 'Organization ID'}: {organization.id}
            </p>
          </div>
        )}

        {/* Form body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <h3 className="mb-4 text-sm font-semibold">
            {isZh ? '基本信息' : 'Basic Info'}
          </h3>

          <div className="flex flex-col gap-4">
            <FieldRow label={isZh ? '名称' : 'Name'} required error={errors.name}>
              <Input
                value={form.name}
                onChange={(e) => setField('name', e.target.value)}
                placeholder={isZh ? '请输入组织名称' : 'Enter organization name'}
              />
            </FieldRow>

            <FieldRow label={isZh ? '描述' : 'Description'}>
              <Textarea
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
                placeholder={isZh ? '请输入组织描述' : 'Enter description'}
                rows={3}
              />
            </FieldRow>
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
                  return (
                    <CustomFieldInput
                      key={field.id ?? key}
                      field={field}
                      value={cfValues[key] ?? null}
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

// ── Custom field renderer ──

function CustomFieldInput({
  field,
  value,
  onChange,
  isZh,
}: {
  field: UnifiedField
  value: CustomFieldValue
  onChange: (v: CustomFieldValue) => void
  isZh: boolean
}) {
  const placeholder = isZh ? `请输入${field.name}` : `Enter ${field.name}`

  return (
    <FieldRow label={field.name} helpText={field.help_text}>
      <UnifiedFieldValueEditor
        field={field}
        value={value}
        onChange={(v) => onChange(v as CustomFieldValue)}
        placeholder={placeholder}
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
