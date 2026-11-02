'use client'

import { useState, type FormEvent } from 'react'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useConsoleTenantOptions, useSipTrunkOptions } from '@/service/use-tenant-console'
import type {
  OutboundTimeSlot,
  PhoneCallType,
  PhoneNumber,
  PhoneNumberCreatePayload,
} from '@/models/tenant-console'
import { FIELD_CLASS, Field, FormSection } from '@/app/tenant/_components/console-ui'

export const PHONE_NUMBER_FORM_ID = 'tenant-console-phone-number-form'

export const CALL_TYPES: PhoneCallType[] = ['inbound', 'outbound']
const MAX_TIME_SLOTS = 10

type FormStatus = 'available' | 'disabled'

function toMinutes(value: string): number {
  const [h, m] = value.split(':').map(Number)
  return h * 60 + m
}

export function PhoneNumberForm({
  phone,
  onSubmit,
  onDirty,
}: {
  phone?: PhoneNumber
  onSubmit: (data: PhoneNumberCreatePayload) => void | Promise<void>
  onDirty?: () => void
}) {
  const { locale } = useLocaleStore()
  const { data: trunkOptions = [] } = useSipTrunkOptions()
  const { data: tenantOptions = [] } = useConsoleTenantOptions()
  const [form, setForm] = useState({
    phone_number: phone?.phone_number ?? '',
    trunk_id: phone?.trunk_id ?? '',
    tenant_id: phone?.tenant_id ?? '',
    status: (phone?.status === 'disabled' ? 'disabled' : 'available') as FormStatus,
    remark: phone?.remark ?? '',
    concurrency: phone?.concurrency != null ? String(phone.concurrency) : '',
    called_number_prefix: phone?.called_number_prefix ?? '',
  })
  const [callTypes, setCallTypes] = useState<PhoneCallType[]>(phone?.call_types ?? ['inbound', 'outbound'])
  const [slots, setSlots] = useState<OutboundTimeSlot[]>(phone?.outbound_time_slots ?? [])
  const [errors, setErrors] = useState<Record<string, string>>({})

  const touch = () => onDirty?.()

  const updateField = (key: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: '' }))
    touch()
  }

  const toggleCallType = (type: PhoneCallType) => {
    setCallTypes((prev) => (prev.includes(type) ? prev.filter((v) => v !== type) : [...prev, type]))
    setErrors((prev) => ({ ...prev, call_types: '' }))
    touch()
  }

  const updateSlot = (index: number, key: keyof OutboundTimeSlot, value: string) => {
    setSlots((prev) => prev.map((slot, i) => (i === index ? { ...slot, [key]: value } : slot)))
    setErrors((prev) => ({ ...prev, slots: '' }))
    touch()
  }

  // Keep a bound trunk/tenant visible even if it is no longer offered (e.g. disabled).
  const trunkChoices: { id: string; trunk_name: string; supplier_name: string }[] =
    !form.trunk_id || trunkOptions.some((o) => o.id === form.trunk_id)
      ? trunkOptions
      : [
          ...trunkOptions,
          {
            id: form.trunk_id,
            trunk_name: phone?.trunk_name ?? form.trunk_id,
            supplier_name: phone?.supplier_name ?? '',
          },
        ]
  const tenantChoices: { id: string; name: string; status: string }[] =
    !form.tenant_id || tenantOptions.some((o) => o.id === form.tenant_id)
      ? tenantOptions
      : [
          ...tenantOptions,
          {
            id: form.tenant_id,
            name: phone?.tenant_name ?? form.tenant_id,
            status: phone?.tenant_status ?? 'disabled',
          },
        ]

  const validate = (): PhoneNumberCreatePayload | null => {
    const next: Record<string, string> = {}
    const number = form.phone_number.trim()
    if (!number) next.phone_number = t('tc.phone.err.number', locale)
    if (callTypes.length === 0) next.call_types = t('tc.phone.err.callTypes', locale)
    let concurrency: number | null = null
    if (form.concurrency.trim()) {
      concurrency = Number(form.concurrency)
      if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 1000) {
        next.concurrency = t('tc.phone.err.concurrency', locale)
      }
    }
    if (form.tenant_id && form.status === 'disabled') next.status = t('tc.phone.err.disabledWithTenant', locale)
    const useSlots = callTypes.includes('outbound') ? slots : []
    const ranges: [number, number][] = []
    for (const slot of useSlots) {
      if (!slot.start || !slot.end || toMinutes(slot.start) >= toMinutes(slot.end)) {
        next.slots = t('tc.phone.err.slotOrder', locale)
        break
      }
      const range: [number, number] = [toMinutes(slot.start), toMinutes(slot.end)]
      if (ranges.some(([s, e]) => range[0] < e && range[1] > s)) {
        next.slots = t('tc.phone.err.slotOverlap', locale)
        break
      }
      ranges.push(range)
    }
    setErrors(next)
    if (Object.keys(next).length > 0) return null
    return {
      phone_number: number,
      call_types: CALL_TYPES.filter((type) => callTypes.includes(type)),
      trunk_id: form.trunk_id || null,
      tenant_id: form.tenant_id || null,
      status: form.status,
      remark: form.remark.trim() || null,
      concurrency,
      called_number_prefix: form.called_number_prefix.trim() || null,
      outbound_time_slots: useSlots,
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const payload = validate()
    if (payload) void onSubmit(payload)
  }

  return (
    <form id={PHONE_NUMBER_FORM_ID} onSubmit={handleSubmit} className="mx-auto max-w-2xl space-y-8 px-6 py-8">
      <FormSection title={t('tc.phone.section.basic', locale)}>
        <Field label={t('tc.phone.col.number', locale)} htmlFor="phone-number" required error={errors.phone_number}>
          <input
            id="phone-number"
            value={form.phone_number}
            maxLength={64}
            disabled={!!phone}
            aria-invalid={!!errors.phone_number}
            onChange={(e) => updateField('phone_number', e.target.value)}
            className={`${FIELD_CLASS} font-mono`}
          />
        </Field>
        <Field label={t('tc.phone.col.callTypes', locale)} required error={errors.call_types}>
          <div className="flex gap-6">
            {CALL_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={callTypes.includes(type)}
                  onChange={() => toggleCallType(type)}
                  className="size-4 accent-primary"
                />
                {t(`tc.callType.${type}`, locale)}
              </label>
            ))}
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field
            label={t('tc.phone.col.concurrency', locale)}
            htmlFor="phone-concurrency"
            hint={t('tc.phone.hint.concurrency', locale)}
            error={errors.concurrency}
          >
            <input
              id="phone-concurrency"
              inputMode="numeric"
              value={form.concurrency}
              aria-invalid={!!errors.concurrency}
              onChange={(e) => updateField('concurrency', e.target.value.replace(/\D/g, ''))}
              className={FIELD_CLASS}
            />
          </Field>
          <Field
            label={t('tc.phone.col.prefix', locale)}
            htmlFor="phone-prefix"
            hint={t('tc.phone.hint.prefix', locale)}
          >
            <input
              id="phone-prefix"
              value={form.called_number_prefix}
              maxLength={32}
              onChange={(e) => updateField('called_number_prefix', e.target.value)}
              className={`${FIELD_CLASS} font-mono`}
            />
          </Field>
        </div>
      </FormSection>

      <FormSection title={t('tc.phone.section.binding', locale)}>
        <Field label={t('tc.phone.col.trunk', locale)} htmlFor="phone-trunk">
          <select
            id="phone-trunk"
            value={form.trunk_id}
            onChange={(e) => updateField('trunk_id', e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">{t('tc.phone.unbound', locale)}</option>
            {trunkChoices.map((o) => (
              <option key={o.id} value={o.id}>
                {o.supplier_name ? `${o.trunk_name} (${o.supplier_name})` : o.trunk_name}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label={t('tc.phone.col.tenant', locale)}
          htmlFor="phone-tenant"
          hint={t('tc.phone.hint.tenant', locale)}
        >
          <select
            id="phone-tenant"
            value={form.tenant_id}
            onChange={(e) => updateField('tenant_id', e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="">{t('tc.phone.unbound', locale)}</option>
            {tenantChoices.map((o) => (
              <option key={o.id} value={o.id} disabled={o.status !== 'enabled' && o.id !== form.tenant_id}>
                {o.status === 'enabled' ? o.name : `${o.name} (${t('tc.status.disabled', locale)})`}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('tc.common.status', locale)} htmlFor="phone-status" error={errors.status}>
          <select
            id="phone-status"
            value={form.status}
            onChange={(e) => updateField('status', e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="available">{t('tc.phone.status.inUse', locale)}</option>
            <option value="disabled">{t('tc.status.disabled', locale)}</option>
          </select>
        </Field>
        <Field label={t('tc.common.remark', locale)} htmlFor="phone-remark">
          <textarea
            id="phone-remark"
            value={form.remark}
            maxLength={256}
            rows={3}
            placeholder={t('tc.common.optional', locale)}
            onChange={(e) => updateField('remark', e.target.value)}
            className={`${FIELD_CLASS} h-auto py-2`}
          />
        </Field>
      </FormSection>

      {callTypes.includes('outbound') && (
        <FormSection title={t('tc.phone.section.slots', locale)}>
          <p className="-mt-2 text-xs text-muted-foreground">{t('tc.phone.hint.slots', locale)}</p>
          <div className="space-y-3">
            {slots.map((slot, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  type="time"
                  aria-label={t('tc.phone.slotStart', locale)}
                  value={slot.start}
                  onChange={(e) => updateSlot(index, 'start', e.target.value)}
                  className={`${FIELD_CLASS} w-36`}
                />
                <span className="text-sm text-muted-foreground">{t('tc.phone.slotTo', locale)}</span>
                <input
                  type="time"
                  aria-label={t('tc.phone.slotEnd', locale)}
                  value={slot.end}
                  onChange={(e) => updateSlot(index, 'end', e.target.value)}
                  className={`${FIELD_CLASS} w-36`}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  title={t('tc.phone.removeSlot', locale)}
                  aria-label={t('tc.phone.removeSlot', locale)}
                  onClick={() => {
                    setSlots((prev) => prev.filter((_, i) => i !== index))
                    touch()
                  }}
                >
                  <IconTrash size={16} />
                </Button>
              </div>
            ))}
            {errors.slots && <p className="text-xs text-destructive">{errors.slots}</p>}
            <Button
              type="button"
              variant="outline"
              disabled={slots.length >= MAX_TIME_SLOTS}
              onClick={() => {
                setSlots((prev) => [...prev, { start: '09:00', end: '18:00' }])
                touch()
              }}
            >
              <IconPlus size={16} />
              {t('tc.phone.addSlot', locale)}
            </Button>
          </div>
        </FormSection>
      )}
    </form>
  )
}
