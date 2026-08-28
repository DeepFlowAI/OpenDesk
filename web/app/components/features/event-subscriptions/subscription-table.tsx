'use client'

import { IconPencil, IconTrash } from '@tabler/icons-react'
import type { EventSubscription } from '@/models/event-subscription'
import type { Locale } from '@/lib/languages'
import { t } from '@/utils/i18n'

function formatDate(value: string | null, locale: Locale) {
  if (!value) return '—'
  return new Date(value).toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function DeliveryCell({ item, locale }: { item: EventSubscription; locale: Locale }) {
  const delivery = item.recent_delivery
  if (!delivery) return <span>{t('eventSubs.delivery.none', locale)}</span>
  const label = delivery.status === 'succeeded'
    ? t('eventSubs.delivery.succeeded', locale)
    : delivery.status === 'failed'
      ? t('eventSubs.delivery.failed', locale)
      : t('eventSubs.delivery.pending', locale)
  return <span>{label} · {formatDate(delivery.attempted_at, locale)}</span>
}

function SubscriptionSwitch({ checked, disabled, label, onChange }: {
  checked: boolean
  disabled: boolean
  label: string
  onChange: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-label={label}
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${checked ? 'bg-primary' : 'bg-input'}`}
    >
      <span className={`h-3.5 w-3.5 rounded-full bg-background transition-transform ${checked ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
    </button>
  )
}

export function SubscriptionTable({ items, locale, busyId, onToggle, onEdit, onDelete }: {
  items: EventSubscription[]
  locale: Locale
  busyId: string | null
  onToggle: (item: EventSubscription) => void
  onEdit: (item: EventSubscription) => void
  onDelete: (item: EventSubscription) => void
}) {
  const headers = ['name', 'status', 'delivery', 'updatedAt', 'actions'] as const
  const widths = ['min-w-[160px] flex-1', 'w-[72px]', 'w-[190px]', 'w-[130px]', 'w-[64px]']
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <div className="flex h-14 min-w-[760px] items-center gap-6 rounded-t-lg bg-muted px-6">
        {headers.map((header, index) => (
          <div key={header} className={`shrink-0 text-sm font-semibold text-foreground/80 ${widths[index]} ${header === 'actions' ? 'text-right' : ''}`}>
            {t(`eventSubs.col.${header}`, locale)}
          </div>
        ))}
      </div>
      {items.map((item) => (
        <div key={item.public_id} className="flex h-14 min-w-[760px] items-center gap-6 border-t border-border px-6">
          <div className="min-w-[160px] flex-1 truncate text-sm">{item.name}</div>
          <div className="w-[72px]">
            <SubscriptionSwitch checked={item.is_active} disabled={busyId === item.public_id} label={item.name} onChange={() => onToggle(item)} />
          </div>
          <div className="w-[190px] truncate text-sm text-muted-foreground"><DeliveryCell item={item} locale={locale} /></div>
          <div className="w-[130px] text-sm text-muted-foreground">{formatDate(item.updated_at, locale)}</div>
          <div className="flex w-[64px] justify-end gap-3">
            <button title={t('eventSubs.action.edit', locale)} onClick={() => onEdit(item)}><IconPencil size={18} /></button>
            <button title={t('eventSubs.action.delete', locale)} disabled={item.is_active || busyId === item.public_id} onClick={() => onDelete(item)} className="text-destructive disabled:cursor-not-allowed disabled:opacity-30"><IconTrash size={18} /></button>
          </div>
        </div>
      ))}
    </div>
  )
}
