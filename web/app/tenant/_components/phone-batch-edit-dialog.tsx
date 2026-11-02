'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { readConsoleError } from '@/service/tenant-console-client'
import {
  useBatchUpdatePhoneNumbers,
  useConsoleTenantOptions,
  useSipTrunkOptions,
} from '@/service/use-tenant-console'
import type { PhoneCallType, PhoneNumberBatchPayload, PhoneStatus } from '@/models/tenant-console'
import { FIELD_CLASS, Field } from '@/app/tenant/_components/console-ui'

const KEEP = '__keep__'
const UNBIND = '__unbind__'

const CALL_TYPE_CHOICES: Record<string, PhoneCallType[]> = {
  inbound: ['inbound'],
  outbound: ['outbound'],
  both: ['inbound', 'outbound'],
}

export function PhoneBatchEditDialog({
  ids,
  onClose,
  onDone,
}: {
  ids: string[]
  onClose: () => void
  onDone: () => void
}) {
  const { locale } = useLocaleStore()
  const { data: trunkOptions = [] } = useSipTrunkOptions()
  const { data: tenantOptions = [] } = useConsoleTenantOptions()
  const batchMutation = useBatchUpdatePhoneNumbers()
  const [callTypes, setCallTypes] = useState(KEEP)
  const [trunkId, setTrunkId] = useState(KEEP)
  const [tenantId, setTenantId] = useState(KEEP)
  const [status, setStatus] = useState(KEEP)

  const hasChange = [callTypes, trunkId, tenantId, status].some((v) => v !== KEEP)

  const handleSubmit = async () => {
    const payload: PhoneNumberBatchPayload = { ids }
    if (callTypes !== KEEP) payload.call_types = CALL_TYPE_CHOICES[callTypes]
    if (trunkId !== KEEP) payload.trunk_id = trunkId === UNBIND ? null : trunkId
    if (tenantId !== KEEP) payload.tenant_id = tenantId === UNBIND ? null : tenantId
    if (status !== KEEP) payload.status = status as PhoneStatus
    try {
      const result = await batchMutation.mutateAsync(payload)
      if (result.fail_count > 0) {
        const first = result.failures[0]
        toast.warning(
          t('tc.phone.batch.partial', locale, {
            success: result.success_count,
            fail: result.fail_count,
            reason: first ? `${first.phone_number ?? first.id}: ${first.reason}` : '',
          }),
        )
      } else {
        toast.success(t('tc.phone.batch.done', locale, { count: result.success_count }))
      }
      onDone()
    } catch (err) {
      toast.error(await readConsoleError(err, t('tc.common.saveFailed', locale)))
    }
  }

  const keepOption = <option value={KEEP}>{t('tc.phone.batch.keep', locale)}</option>

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="w-[480px] max-w-[90vw] space-y-4 rounded-xl bg-background p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div>
          <h3 className="text-base font-semibold text-foreground">{t('tc.phone.batch.title', locale)}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('tc.phone.batch.selected', locale, { count: ids.length })}
          </p>
        </div>
        <Field label={t('tc.phone.col.callTypes', locale)}>
          <select value={callTypes} onChange={(e) => setCallTypes(e.target.value)} className={FIELD_CLASS}>
            {keepOption}
            <option value="inbound">{t('tc.callType.inbound', locale)}</option>
            <option value="outbound">{t('tc.callType.outbound', locale)}</option>
            <option value="both">{t('tc.callType.both', locale)}</option>
          </select>
        </Field>
        <Field label={t('tc.phone.col.trunk', locale)}>
          <select value={trunkId} onChange={(e) => setTrunkId(e.target.value)} className={FIELD_CLASS}>
            {keepOption}
            <option value={UNBIND}>{t('tc.phone.unbind', locale)}</option>
            {trunkOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.trunk_name} ({o.supplier_name})
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('tc.phone.col.tenant', locale)}>
          <select value={tenantId} onChange={(e) => setTenantId(e.target.value)} className={FIELD_CLASS}>
            {keepOption}
            <option value={UNBIND}>{t('tc.phone.unbind', locale)}</option>
            {tenantOptions
              .filter((o) => o.status === 'enabled')
              .map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
          </select>
        </Field>
        <Field label={t('tc.common.status', locale)}>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={FIELD_CLASS}>
            {keepOption}
            <option value="available">{t('tc.phone.status.inUse', locale)}</option>
            <option value="disabled">{t('tc.status.disabled', locale)}</option>
          </select>
        </Field>
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="outline" size="lg" onClick={onClose} disabled={batchMutation.isPending}>
            {t('tc.common.cancel', locale)}
          </Button>
          <Button size="lg" onClick={handleSubmit} disabled={!hasChange || batchMutation.isPending}>
            {batchMutation.isPending ? t('tc.common.saving', locale) : t('tc.common.save', locale)}
          </Button>
        </div>
      </div>
    </div>
  )
}
