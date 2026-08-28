'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconChevronLeft, IconChevronRight, IconPlus, IconSearch, IconWebhook } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  useDeleteEventSubscription,
  useDisableEventSubscription,
  useEnableEventSubscription,
  useEventSubscriptions,
} from '@/service/use-event-subscriptions'
import type { EventSubscription } from '@/models/event-subscription'
import { SubscriptionTable } from '@/app/components/features/event-subscriptions/subscription-table'
import {
  SubscriptionConfirmDialog,
  type SubscriptionConfirmTarget,
} from '@/app/components/features/event-subscriptions/dialogs'

type StatusFilter = '' | 'active' | 'disabled'

export function SubscriptionList() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('')
  const [applied, setApplied] = useState<{ q: string; status: StatusFilter }>({ q: '', status: '' })
  const [page, setPage] = useState(1)
  const [target, setTarget] = useState<SubscriptionConfirmTarget | null>(null)
  const query = useEventSubscriptions({
    page,
    per_page: 20,
    ...(applied.q ? { q: applied.q } : {}),
    ...(applied.status ? { status: applied.status } : {}),
  })
  const enable = useEnableEventSubscription()
  const disable = useDisableEventSubscription()
  const remove = useDeleteEventSubscription()
  const pending = enable.isPending || disable.isPending || remove.isPending
  const busyId = pending ? target?.item.public_id ?? null : null

  const applyFilters = () => {
    setApplied({ q: search.trim(), status })
    setPage(1)
  }
  const resetFilters = () => {
    setSearch('')
    setStatus('')
    setApplied({ q: '', status: '' })
    setPage(1)
  }
  const toggle = (item: EventSubscription) => setTarget({ action: item.is_active ? 'disable' : 'enable', item })
  const confirm = async () => {
    if (!target) return
    try {
      if (target.action === 'enable') await enable.mutateAsync(target.item.public_id)
      if (target.action === 'disable') await disable.mutateAsync(target.item.public_id)
      if (target.action === 'delete') await remove.mutateAsync(target.item.public_id)
      toast.success(t(`eventSubs.${target.action}.success`, locale))
      setTarget(null)
    } catch {
      toast.error(t('eventSubs.operation.failed', locale))
    }
  }

  const items = query.data?.items ?? []
  const filtered = Boolean(applied.q || applied.status)
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-xl font-semibold">{t('eventSubs.title', locale)}</h1>
        <button
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
          disabled={(query.data?.total ?? 0) >= 20}
          onClick={() => router.push('/event-subscriptions/new')}
        >
          <IconPlus size={18} />{t('eventSubs.new', locale)}
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex h-9 w-[280px] items-center gap-2 rounded-lg border border-border px-3">
          <IconSearch size={16} className="text-muted-foreground" />
          <input className="min-w-0 flex-1 bg-transparent text-sm outline-none" maxLength={80} placeholder={t('eventSubs.search', locale)} value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} />
        </label>
        <span className="text-sm font-medium">{t('eventSubs.status.label', locale)}</span>
        <select className="h-9 w-[140px] rounded-lg border border-border bg-background px-3 text-sm" value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
          <option value="">{t('eventSubs.status.all', locale)}</option>
          <option value="active">{t('eventSubs.status.active', locale)}</option>
          <option value="disabled">{t('eventSubs.status.disabled', locale)}</option>
        </select>
        <button className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground" onClick={applyFilters}>{t('eventSubs.query', locale)}</button>
        <button className="h-9 rounded-lg border border-border px-4 text-sm font-medium" onClick={resetFilters}>{t('eventSubs.reset', locale)}</button>
      </div>
      {query.isLoading ? (
        <div className="h-56 animate-pulse rounded-lg bg-muted" />
      ) : query.isError ? (
        <div className="rounded-lg border border-destructive/30 p-6 text-sm text-destructive">{t('eventSubs.load.failed', locale)}</div>
      ) : items.length ? (
        <>
          <SubscriptionTable items={items} locale={locale} busyId={busyId} onToggle={toggle} onEdit={(item) => router.push(`/event-subscriptions/${item.public_id}`)} onDelete={(item) => setTarget({ action: 'delete', item })} />
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>{t('eventSubs.total', locale, { count: query.data?.total ?? 0 })}</span>
            <div className="flex items-center gap-2">
              <button className="grid h-8 w-8 place-items-center rounded-lg border border-border disabled:opacity-40" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><IconChevronLeft size={16} /></button>
              <span>{page} / {Math.max(query.data?.pages ?? 1, 1)}</span>
              <button className="grid h-8 w-8 place-items-center rounded-lg border border-border disabled:opacity-40" disabled={page >= (query.data?.pages ?? 1)} onClick={() => setPage((value) => value + 1)}><IconChevronRight size={16} /></button>
            </div>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-muted"><IconWebhook size={22} /></div>
          <p className="text-sm text-muted-foreground">{t(filtered ? 'eventSubs.empty.filtered' : 'eventSubs.empty', locale)}</p>
          <button className="h-9 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground" onClick={filtered ? resetFilters : () => router.push('/event-subscriptions/new')}>
            {t(filtered ? 'eventSubs.reset' : 'eventSubs.new', locale)}
          </button>
        </div>
      )}
      <SubscriptionConfirmDialog target={target} pending={pending} onCancel={() => setTarget(null)} onConfirm={() => void confirm()} />
    </div>
  )
}
