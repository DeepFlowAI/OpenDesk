'use client'

import { useEffect, useState } from 'react'
import { IconAlertTriangle, IconCopy, IconKey, IconShieldLock } from '@tabler/icons-react'
import type { EventSubscription, EventSubscriptionSecretResponse } from '@/models/event-subscription'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

export type SubscriptionConfirmAction = 'enable' | 'disable' | 'delete' | 'rotate'
export type SubscriptionConfirmTarget = {
  action: SubscriptionConfirmAction
  item: EventSubscription
}

export function SubscriptionConfirmDialog({
  target,
  pending,
  onCancel,
  onConfirm,
}: {
  target: SubscriptionConfirmTarget | null
  pending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const { locale } = useLocaleStore()
  if (!target) return null
  const destructive = target.action === 'delete'
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <section className="w-[480px] max-w-full rounded-xl bg-background p-6 shadow-2xl">
        <h2 className="text-lg font-semibold">{t(`eventSubs.confirm.${target.action}.title`, locale)}</h2>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {t(`eventSubs.confirm.${target.action}.message`, locale)}
        </p>
        <div className="mt-4 rounded-lg border border-border p-3">
          <p className="truncate text-sm font-medium">{target.item.name}</p>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{target.item.endpoint_url}</p>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button className="h-9 rounded-lg border border-border px-4 text-sm font-medium" disabled={pending} onClick={onCancel}>
            {t('eventSubs.cancel', locale)}
          </button>
          <button
            className={cn(
              'h-9 rounded-lg px-4 text-sm font-medium text-primary-foreground disabled:opacity-50',
              destructive ? 'bg-destructive' : 'bg-primary',
            )}
            disabled={pending}
            onClick={onConfirm}
          >
            {pending ? t('eventSubs.pending', locale) : t(`eventSubs.confirm.${target.action}.ok`, locale)}
          </button>
        </div>
      </section>
    </div>
  )
}

export function SubscriptionSecretDialog({
  value,
  onClose,
}: {
  value: EventSubscriptionSecretResponse | null
  onClose: () => void
}) {
  const { locale } = useLocaleStore()
  const [confirmed, setConfirmed] = useState(false)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (value) {
      setConfirmed(false)
      setCopied(false)
    }
  }, [value])
  if (!value) return null
  const copy = async () => {
    await navigator.clipboard.writeText(value.secret)
    setCopied(true)
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <section className="w-[560px] max-w-full rounded-xl bg-background p-6 shadow-2xl">
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-muted"><IconShieldLock size={20} /></div>
        <h2 className="mt-4 text-lg font-semibold">{t('eventSubs.secret.title', locale)}</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{t('eventSubs.secret.description', locale)}</p>
        <div className="mt-5 rounded-lg border border-border bg-muted/50 p-4">
          <p className="flex items-center gap-2 text-sm font-medium"><IconKey size={16} />Webhook Secret</p>
          <div className="mt-3 flex min-h-11 items-center gap-3 rounded-lg border border-border bg-background px-3">
            <code className="min-w-0 flex-1 break-all font-mono text-xs">{value.secret}</code>
            <button title={t('eventSubs.copy', locale)} onClick={() => void copy()}><IconCopy size={16} /></button>
          </div>
        </div>
        <div className="mt-4 flex gap-2 rounded-lg bg-warning/10 px-3 py-3 text-sm leading-6 text-foreground">
          <IconAlertTriangle size={18} className="mt-0.5 shrink-0" />{t('eventSubs.secret.warning', locale)}
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
          {t('eventSubs.secret.saved', locale)}
        </label>
        <div className="mt-6 flex justify-end gap-3">
          <button className="h-9 rounded-lg border border-border px-4 text-sm font-medium" disabled={!confirmed} onClick={onClose}>
            {t('eventSubs.done', locale)}
          </button>
          <button className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground" onClick={() => void copy()}>
            <IconCopy size={16} />{copied ? t('eventSubs.copied', locale) : t('eventSubs.copy', locale)}
          </button>
        </div>
      </section>
    </div>
  )
}
