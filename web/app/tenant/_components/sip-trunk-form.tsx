'use client'

import { useState, type FormEvent } from 'react'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { SipTrunk, SipTrunkPayload, TrunkStatus, TrunkType } from '@/models/tenant-console'
import { FIELD_CLASS, Field, FormSection } from '@/app/tenant/_components/console-ui'

export const SIP_TRUNK_FORM_ID = 'tenant-console-sip-trunk-form'

const TRUNK_TYPES: TrunkType[] = ['inbound', 'outbound']
const IPV4_RE = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/

type EndpointRow = { ip: string; port: string }

function isValidIpOrCidr(value: string): boolean {
  const [addr, prefix, extra] = value.split('/')
  if (extra !== undefined || !addr) return false
  const isV4 = IPV4_RE.test(addr)
  const isV6 = !isV4 && addr.includes(':') && /^[0-9a-fA-F:.]+$/.test(addr)
  if (!isV4 && !isV6) return false
  if (prefix === undefined) return true
  if (!/^\d+$/.test(prefix)) return false
  return Number(prefix) <= (isV4 ? 32 : 128)
}

export function SipTrunkForm({
  trunk,
  onSubmit,
  onDirty,
}: {
  trunk?: SipTrunk
  onSubmit: (data: SipTrunkPayload) => void | Promise<void>
  onDirty?: () => void
}) {
  const { locale } = useLocaleStore()
  const [form, setForm] = useState({
    supplier_name: trunk?.supplier_name ?? '',
    trunk_name: trunk?.trunk_name ?? '',
    remark: trunk?.remark ?? '',
    status: (trunk?.status ?? 'enabled') as TrunkStatus,
  })
  const [types, setTypes] = useState<TrunkType[]>(trunk?.trunk_types ?? ['inbound', 'outbound'])
  const [endpoints, setEndpoints] = useState<EndpointRow[]>(
    trunk?.peer_endpoints.length
      ? trunk.peer_endpoints.map((ep) => ({ ip: ep.ip, port: String(ep.port) }))
      : [{ ip: '', port: '5060' }],
  )
  const [errors, setErrors] = useState<Record<string, string>>({})

  const touch = () => onDirty?.()

  const updateField = (key: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: '' }))
    touch()
  }

  const toggleType = (type: TrunkType) => {
    setTypes((prev) => (prev.includes(type) ? prev.filter((v) => v !== type) : [...prev, type]))
    setErrors((prev) => ({ ...prev, trunk_types: '' }))
    touch()
  }

  const updateEndpoint = (index: number, key: keyof EndpointRow, value: string) => {
    setEndpoints((prev) => prev.map((row, i) => (i === index ? { ...row, [key]: value } : row)))
    setErrors((prev) => ({ ...prev, [`ep${index}`]: '', endpoints: '' }))
    touch()
  }

  const validate = (): SipTrunkPayload | null => {
    const next: Record<string, string> = {}
    if (!form.supplier_name.trim()) next.supplier_name = t('tc.trunk.err.supplier', locale)
    if (!form.trunk_name.trim()) next.trunk_name = t('tc.trunk.err.name', locale)
    if (types.length === 0) next.trunk_types = t('tc.trunk.err.types', locale)
    const seen = new Set<string>()
    const peers = endpoints.map((row, index) => {
      const ip = row.ip.trim()
      const port = Number(row.port)
      if (!isValidIpOrCidr(ip)) next[`ep${index}`] = t('tc.trunk.err.ip', locale)
      else if (!Number.isInteger(port) || port < 1 || port > 65535) {
        next[`ep${index}`] = t('tc.trunk.err.port', locale)
      } else if (seen.has(`${ip}:${port}`)) {
        next[`ep${index}`] = t('tc.trunk.err.duplicate', locale)
      }
      seen.add(`${ip}:${port}`)
      return { ip, port }
    })
    if (peers.length === 0) next.endpoints = t('tc.trunk.err.endpoints', locale)
    setErrors(next)
    if (Object.keys(next).length > 0) return null
    return {
      supplier_name: form.supplier_name.trim(),
      trunk_name: form.trunk_name.trim(),
      trunk_types: TRUNK_TYPES.filter((type) => types.includes(type)),
      remark: form.remark.trim() || null,
      status: form.status,
      peer_endpoints: peers,
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const payload = validate()
    if (payload) void onSubmit(payload)
  }

  return (
    <form id={SIP_TRUNK_FORM_ID} onSubmit={handleSubmit} className="mx-auto max-w-2xl space-y-8 px-6 py-8">
      <FormSection title={t('tc.trunk.section.basic', locale)}>
        <Field label={t('tc.trunk.col.supplier', locale)} htmlFor="trunk-supplier" required error={errors.supplier_name}>
          <input
            id="trunk-supplier"
            value={form.supplier_name}
            maxLength={128}
            aria-invalid={!!errors.supplier_name}
            onChange={(e) => updateField('supplier_name', e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field label={t('tc.trunk.col.name', locale)} htmlFor="trunk-name" required error={errors.trunk_name}>
          <input
            id="trunk-name"
            value={form.trunk_name}
            maxLength={128}
            aria-invalid={!!errors.trunk_name}
            onChange={(e) => updateField('trunk_name', e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>
        <Field label={t('tc.trunk.col.types', locale)} required error={errors.trunk_types}>
          <div className="flex gap-6">
            {TRUNK_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={types.includes(type)}
                  onChange={() => toggleType(type)}
                  className="size-4 accent-primary"
                />
                {t(`tc.callType.${type}`, locale)}
              </label>
            ))}
          </div>
        </Field>
        <Field label={t('tc.common.status', locale)} htmlFor="trunk-status">
          <select
            id="trunk-status"
            value={form.status}
            onChange={(e) => updateField('status', e.target.value)}
            className={FIELD_CLASS}
          >
            <option value="enabled">{t('tc.status.enabled', locale)}</option>
            <option value="disabled">{t('tc.status.disabled', locale)}</option>
          </select>
        </Field>
        <Field label={t('tc.common.remark', locale)} htmlFor="trunk-remark">
          <textarea
            id="trunk-remark"
            value={form.remark}
            maxLength={256}
            rows={3}
            placeholder={t('tc.common.optional', locale)}
            onChange={(e) => updateField('remark', e.target.value)}
            className={`${FIELD_CLASS} h-auto py-2`}
          />
        </Field>
      </FormSection>

      <FormSection title={t('tc.trunk.section.endpoints', locale)}>
        <p className="-mt-2 text-xs text-muted-foreground">{t('tc.trunk.hint.endpoints', locale)}</p>
        <div className="space-y-3">
          {endpoints.map((row, index) => (
            <div key={index} className="space-y-1">
              <div className="flex items-center gap-2">
                <input
                  aria-label={t('tc.trunk.ip', locale)}
                  placeholder={t('tc.trunk.ph.ip', locale)}
                  value={row.ip}
                  aria-invalid={!!errors[`ep${index}`]}
                  onChange={(e) => updateEndpoint(index, 'ip', e.target.value)}
                  className={`${FIELD_CLASS} flex-1 font-mono`}
                />
                <input
                  aria-label={t('tc.trunk.port', locale)}
                  placeholder="5060"
                  inputMode="numeric"
                  value={row.port}
                  aria-invalid={!!errors[`ep${index}`]}
                  onChange={(e) => updateEndpoint(index, 'port', e.target.value.replace(/\D/g, ''))}
                  className={`${FIELD_CLASS} w-28 font-mono`}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={endpoints.length <= 1}
                  title={t('tc.trunk.removeEndpoint', locale)}
                  aria-label={t('tc.trunk.removeEndpoint', locale)}
                  onClick={() => {
                    setEndpoints((prev) => prev.filter((_, i) => i !== index))
                    touch()
                  }}
                >
                  <IconTrash size={16} />
                </Button>
              </div>
              {errors[`ep${index}`] && <p className="text-xs text-destructive">{errors[`ep${index}`]}</p>}
            </div>
          ))}
          {errors.endpoints && <p className="text-xs text-destructive">{errors.endpoints}</p>}
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setEndpoints((prev) => [...prev, { ip: '', port: '5060' }])
              touch()
            }}
          >
            <IconPlus size={16} />
            {t('tc.trunk.addEndpoint', locale)}
          </Button>
        </div>
      </FormSection>
    </form>
  )
}
