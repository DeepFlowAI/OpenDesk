'use client'

import { useState, type FormEvent } from 'react'
import { IconEye, IconEyeOff } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type {
  ConsoleTenant,
  ConsoleTenantCreatePayload,
  ConsoleTenantUpdatePayload,
} from '@/models/tenant-console'
import { FIELD_CLASS, Field, FormSection } from '@/app/tenant/_components/console-ui'

export const TENANT_FORM_ID = 'tenant-console-tenant-form'

const SLUG_RE = /^[a-z0-9][a-z0-9._/-]{1,127}$/
const USERNAME_RE = /^[a-zA-Z0-9_]{3,64}$/
const PASSWORD_CHARS = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^&*'

function generatePassword(length = 16): string {
  const values = new Uint32Array(length)
  crypto.getRandomValues(values)
  return Array.from(values, (v) => PASSWORD_CHARS[v % PASSWORD_CHARS.length]).join('')
}

type TenantFormProps =
  | {
      tenant?: undefined
      onSubmit: (data: ConsoleTenantCreatePayload) => void | Promise<void>
      onDirty?: () => void
    }
  | {
      tenant: ConsoleTenant
      onSubmit: (data: ConsoleTenantUpdatePayload) => void | Promise<void>
      onDirty?: () => void
    }

export function TenantForm(props: TenantFormProps) {
  const { tenant, onDirty } = props
  const isEdit = !!tenant
  const { locale } = useLocaleStore()
  const [form, setForm] = useState({
    name: tenant?.name ?? '',
    slug: tenant?.slug ?? '',
    remark: tenant?.remark ?? '',
    admin_username: tenant?.admin_username ?? '',
    admin_password: '',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const update = (key: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: '' }))
    onDirty?.()
  }

  const validate = (): boolean => {
    const next: Record<string, string> = {}
    const name = form.name.trim()
    const slug = form.slug.trim().toLowerCase()
    const username = form.admin_username.trim()
    if (!name) next.name = t('tc.tenant.err.nameRequired', locale)
    else if (name.length > 64) next.name = t('tc.tenant.err.nameLength', locale)
    if (slug && !SLUG_RE.test(slug)) next.slug = t('tc.tenant.err.slug', locale)
    if (form.remark.length > 256) next.remark = t('tc.tenant.err.remark', locale)
    if (!USERNAME_RE.test(username)) next.admin_username = t('tc.tenant.err.username', locale)
    const pwd = form.admin_password
    if (!isEdit && !pwd) next.admin_password = t('tc.tenant.err.passwordRequired', locale)
    else if (pwd && (pwd.length < 8 || pwd.length > 64)) {
      next.admin_password = t('tc.tenant.err.passwordLength', locale)
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!validate()) return
    const slug = form.slug.trim().toLowerCase()
    const remark = form.remark.trim()
    if (props.tenant) {
      const payload: ConsoleTenantUpdatePayload = {
        name: form.name.trim(),
        slug: slug || null,
        remark: remark || null,
        admin_username: form.admin_username.trim(),
      }
      if (form.admin_password) payload.admin_password = form.admin_password
      void props.onSubmit(payload)
    } else {
      void props.onSubmit({
        name: form.name.trim(),
        slug: slug || null,
        remark: remark || null,
        admin_username: form.admin_username.trim(),
        admin_password: form.admin_password,
      })
    }
  }

  return (
    <form id={TENANT_FORM_ID} onSubmit={handleSubmit} className="mx-auto max-w-2xl space-y-8 px-6 py-8">
      <FormSection title={t('tc.tenant.section.basic', locale)}>
        {isEdit && (
          <Field label={t('tc.tenant.col.id', locale)} htmlFor="tenant-id">
            <input id="tenant-id" value={tenant.id} disabled className={`${FIELD_CLASS} font-mono`} />
          </Field>
        )}
        <Field label={t('tc.tenant.col.name', locale)} htmlFor="tenant-name" required error={errors.name}>
          <input
            id="tenant-name"
            value={form.name}
            maxLength={64}
            aria-invalid={!!errors.name}
            placeholder={t('tc.tenant.ph.name', locale)}
            onChange={(e) => update('name', e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field
          label={t('tc.tenant.col.slug', locale)}
          htmlFor="tenant-slug"
          hint={t('tc.tenant.hint.slug', locale)}
          error={errors.slug}
        >
          <input
            id="tenant-slug"
            value={form.slug}
            maxLength={128}
            aria-invalid={!!errors.slug}
            placeholder={t('tc.tenant.ph.slug', locale)}
            onChange={(e) => update('slug', e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field label={t('tc.tenant.col.remark', locale)} htmlFor="tenant-remark" error={errors.remark}>
          <textarea
            id="tenant-remark"
            value={form.remark}
            maxLength={256}
            rows={3}
            placeholder={t('tc.common.optional', locale)}
            onChange={(e) => update('remark', e.target.value)}
            className={`${FIELD_CLASS} h-auto py-2`}
          />
        </Field>
      </FormSection>

      <FormSection title={t('tc.tenant.section.admin', locale)}>
        <Field
          label={t('tc.tenant.col.admin', locale)}
          htmlFor="tenant-admin-username"
          required
          hint={t('tc.tenant.hint.username', locale)}
          error={errors.admin_username}
        >
          <input
            id="tenant-admin-username"
            value={form.admin_username}
            maxLength={64}
            autoComplete="off"
            aria-invalid={!!errors.admin_username}
            onChange={(e) => update('admin_username', e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field
          label={t('tc.tenant.adminPassword', locale)}
          htmlFor="tenant-admin-password"
          required={!isEdit}
          hint={t(isEdit ? 'tc.tenant.hint.passwordKeep' : 'tc.tenant.hint.password', locale)}
          error={errors.admin_password}
        >
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                id="tenant-admin-password"
                type={showPassword ? 'text' : 'password'}
                value={form.admin_password}
                maxLength={64}
                autoComplete="new-password"
                aria-invalid={!!errors.admin_password}
                onChange={(e) => update('admin_password', e.target.value)}
                className={`${FIELD_CLASS} pr-10`}
              />
              <button
                type="button"
                aria-label={t('tc.tenant.togglePassword', locale)}
                onClick={() => setShowPassword((v) => !v)}
                className="absolute top-1/2 right-3 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <IconEyeOff size={16} /> : <IconEye size={16} />}
              </button>
            </div>
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() => {
                update('admin_password', generatePassword())
                setShowPassword(true)
              }}
            >
              {t('tc.tenant.generatePassword', locale)}
            </Button>
          </div>
        </Field>
      </FormSection>
    </form>
  )
}
